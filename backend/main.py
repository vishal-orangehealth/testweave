from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx
import anthropic
import json
import os
import re
import io

# ── Load .env file (fixes ANTHROPIC_API_KEY not set) ─────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── doc parsers (graceful fallback if not installed) ──────────────────────────
try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from huggingface_hub import InferenceClient
    HAS_HUGGINGFACE = True
except ImportError:
    HAS_HUGGINGFACE = False

app = FastAPI(title="TestWeave API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Configuration ───────────────────────────────────────────────────────

ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
HUGGINGFACE_API_TOKEN = os.environ.get("HUGGINGFACE_API_TOKEN", "")

# Initialize Anthropic client if key is available
if ANTHROPIC_API_KEY:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
else:
    client = None
    print("WARNING: ANTHROPIC_API_KEY not set — Claude will not be available")

# Initialize HuggingFace client if token is available
hf_client = None
if HAS_HUGGINGFACE and HUGGINGFACE_API_TOKEN:
    hf_client = InferenceClient(token=HUGGINGFACE_API_TOKEN)  # FIX: use 'token=' not 'api_key='
elif not HUGGINGFACE_API_TOKEN:
    print("WARNING: HUGGINGFACE_API_TOKEN not set — HuggingFace fallback will not be available")

# ─── Models ──────────────────────────────────────────────────────────────────

class PRDRequest(BaseModel):
    prd_text: str
    project_name: Optional[str] = "Untitled Project"

class FigmaRequest(BaseModel):
    figma_url: str
    figma_token: str
    project_name: Optional[str] = "Untitled Project"

# ─── Prompts ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior QA engineer with 10+ years of experience writing test cases.
Given a structured description of UI screens or product requirements, generate comprehensive test cases.

Output ONLY valid JSON — no prose, no markdown fences, no explanation.

Schema:
{
  "project": string,
  "source": "PRD" | "Figma",
  "screens": [
    {
      "screen_name": string,
      "test_cases": [
        {
          "id": string,
          "title": string,
          "type": "happy_path" | "edge_case" | "negative" | "accessibility" | "performance",
          "priority": "P0" | "P1" | "P2",
          "preconditions": [string],
          "steps": [string],
          "expected_result": string,
          "component": string
        }
      ]
    }
  ],
  "summary": {
    "total": number,
    "p0": number,
    "p1": number,
    "p2": number,
    "happy_path": number,
    "negative": number,
    "edge_case": number,
    "accessibility": number
  }
}

Rules:
- P0: blocks core user journey (auth, payment, core CRUD)
- P1: important functionality with a workaround
- P2: edge case, cosmetic, nice-to-have
- Always include at least 1 accessibility test per screen
- Always include at least 1 negative/error test per input field found
- IDs format: TC-001, TC-002, ...
- Steps must be user-perspective actions ("Click", "Enter", "Navigate")
- Expected results must be specific and observable
"""

# ─── Figma Extractor ─────────────────────────────────────────────────────────

def parse_figma_file_key(url: str) -> str:
    patterns = [
        r"figma\.com/file/([a-zA-Z0-9]+)",
        r"figma\.com/design/([a-zA-Z0-9]+)",
        r"figma\.com/proto/([a-zA-Z0-9]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    raise ValueError("Could not parse Figma file key from URL")

async def extract_figma_context(file_key: str, token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(
            f"https://api.figma.com/v1/files/{file_key}",
            headers={"X-Figma-Token": token},
            params={"depth": "3"},
        )
        if resp.status_code == 403:
            raise HTTPException(403, "Invalid Figma token or no access to file")
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Figma API error: {resp.text[:200]}")
        data = resp.json()

    screens = []

    def walk(node, depth=0, screen=None):
        t = node.get("type", "")
        name = node.get("name", "")

        if t == "FRAME" and depth == 1:
            screen = {
                "name": name,
                "components": [],
                "texts": [],
                "flows": [],
            }
            screens.append(screen)

        if screen is None:
            for child in node.get("children", []):
                walk(child, depth + 1, screen)
            return

        if t == "INSTANCE":
            props = node.get("componentProperties", {})
            variants = {k: v.get("value") for k, v in props.items()} if props else {}
            screen["components"].append({"name": name, "variants": variants})

        if t == "TEXT":
            content = node.get("characters", "")
            if content.strip():
                screen["texts"].append({"label": name, "content": content[:100]})

        for reaction in node.get("reactions", []):
            action = reaction.get("action", {})
            trigger = reaction.get("trigger", {})
            screen["flows"].append({
                "from": name,
                "trigger": trigger.get("type", ""),
                "action": action.get("type", ""),
            })

        for child in node.get("children", []):
            walk(child, depth + 1, screen)

    doc = data.get("document", {})
    for page in doc.get("children", []):
        for child in page.get("children", []):
            walk(child, depth=1)

    return {
        "file_name": data.get("name", "Figma File"),
        "screens": screens[:10],
    }

# ─── Claude/HuggingFace Generators ───────────────────────────────────────────

def call_claude(user_message: str) -> dict:
    """Call Claude via Anthropic API, with HuggingFace fallback"""
    anthropic_error = None
    hf_error = None

    # Try Anthropic Claude first
    if client and ANTHROPIC_API_KEY:
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except Exception as e:
            anthropic_error = str(e)
            print(f"Anthropic API error: {e}")

    # Fallback to HuggingFace LLaMA 3 8B
    if hf_client and HUGGINGFACE_API_TOKEN:
        try:
            # FIX: correct method is chat_completion (not chat.completions)
            # and provider arg selects the right inference endpoint
            response = hf_client.chat_completion(
                model="meta-llama/Meta-Llama-3-8B-Instruct",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                max_tokens=8000,
                 # FIX: let HF pick the available provider
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except Exception as e:
            hf_error = str(e)
            print(f"HuggingFace error: {e}")

    # Surface the real errors
    if not ANTHROPIC_API_KEY and not HUGGINGFACE_API_TOKEN:
        raise HTTPException(
            500,
            "No AI API keys configured. Set ANTHROPIC_API_KEY or HUGGINGFACE_API_TOKEN in your .env file."
        )

    parts = []
    if anthropic_error:
        parts.append(f"Anthropic: {anthropic_error}")
    elif not ANTHROPIC_API_KEY:
        parts.append("Anthropic: ANTHROPIC_API_KEY not set")

    if hf_error:
        parts.append(f"HuggingFace: {hf_error}")
    elif not HUGGINGFACE_API_TOKEN:
        parts.append("HuggingFace: HUGGINGFACE_API_TOKEN not set")

    raise HTTPException(500, " | ".join(parts))

# ─── Document text extractors ────────────────────────────────────────────────

def extract_txt(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

def extract_docx(data: bytes) -> str:
    if not HAS_DOCX:
        raise HTTPException(500, "python-docx not installed on server")
    doc = DocxDocument(io.BytesIO(data))
    parts = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if "Heading 1" in style:
            parts.append(f"\n# {text}")
        elif "Heading 2" in style:
            parts.append(f"\n## {text}")
        elif "Heading 3" in style:
            parts.append(f"\n### {text}")
        else:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)

def extract_pdf(data: bytes) -> str:
    if not HAS_PDF:
        raise HTTPException(500, "PyPDF2 not installed on server")
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n\n".join(pages)

def extract_text_from_file(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "docx":
        return extract_docx(data)
    elif ext == "pdf":
        return extract_pdf(data)
    elif ext in ("txt", "md"):
        return extract_txt(data)
    else:
        raise HTTPException(400, f"Unsupported file type: .{ext}. Supported: .docx, .pdf, .txt, .md")

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "docx": HAS_DOCX,
        "pdf": HAS_PDF,
        "anthropic": bool(ANTHROPIC_API_KEY),
        "huggingface": bool(HUGGINGFACE_API_TOKEN),
        "ai_available": bool(ANTHROPIC_API_KEY or HUGGINGFACE_API_TOKEN),
    }

@app.post("/upload/prd")
async def upload_prd(
    file: UploadFile = File(...),
    project_name: str = Form("Untitled Project"),
):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10 MB)")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        text = extract_text_from_file(file.filename or "file.txt", data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f"Could not parse file: {e}")

    if len(text.strip()) < 50:
        raise HTTPException(400, "Extracted text is too short — is the file empty or scanned?")

    user_msg = f"""Project: {project_name}
Source: PRD document (uploaded file: {file.filename})

--- PRD CONTENT START ---
{text[:14000]}
--- PRD CONTENT END ---

Instructions:
1. Identify all distinct screens/features in this PRD
2. For each screen extract: user stories, acceptance criteria, input fields, error conditions
3. Generate test cases covering happy path, edge cases, negative cases, and accessibility
4. Group test cases by screen/feature
5. Use actual text from the PRD in expected results where possible
"""
    result = call_claude(user_msg)
    result["source"] = "PRD"
    result["project"] = project_name
    result["filename"] = file.filename
    return result

@app.post("/generate/prd")
def generate_from_prd(req: PRDRequest):
    if len(req.prd_text.strip()) < 50:
        raise HTTPException(400, "PRD text is too short")

    user_msg = f"""Project: {req.project_name}
Source: PRD document

--- PRD CONTENT START ---
{req.prd_text[:12000]}
--- PRD CONTENT END ---

Instructions:
1. First identify all distinct screens/features in this PRD
2. For each screen, extract: user stories, acceptance criteria, input fields, error conditions
3. Generate test cases covering happy path, edge cases, negative cases, and accessibility
4. Group test cases by screen/feature
5. Be specific — use actual text from the PRD in expected results where possible
"""
    result = call_claude(user_msg)
    result["source"] = "PRD"
    result["project"] = req.project_name
    return result

@app.post("/generate/figma")
async def generate_from_figma(req: FigmaRequest):
    try:
        file_key = parse_figma_file_key(req.figma_url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    context = await extract_figma_context(file_key, req.figma_token)

    screens_summary = []
    for s in context["screens"]:
        screens_summary.append({
            "screen": s["name"],
            "components": s["components"][:15],
            "text_content": s["texts"][:20],
            "user_flows": s["flows"][:10],
        })

    user_msg = f"""Project: {req.project_name}
Source: Figma design file "{context['file_name']}"

Screens found in design:
{json.dumps(screens_summary, indent=2)}

Instructions:
1. For each screen, analyse the components (buttons, inputs, dropdowns) and their variants
2. Use text content (labels, placeholders, error messages) to understand validation rules
3. Use user flows (prototype links) to understand navigation paths
4. Generate test cases: happy path per screen, all component variants, all visible error states,
   navigation flows, and accessibility checks
5. Component variant names (e.g. "Disabled", "Error", "Loading") = separate test cases
"""
    result = call_claude(user_msg)
    result["source"] = "Figma"
    result["project"] = req.project_name
    return result