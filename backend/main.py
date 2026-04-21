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

def _call_llm(system: str, user: str, max_tokens: int) -> str:
    """Low-level LLM call — returns raw text. Raises HTTPException on total failure."""
    anthropic_error = None
    hf_error = None

    if client and ANTHROPIC_API_KEY:
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if msg.stop_reason == "max_tokens":
                raise ValueError("Response truncated — output too large for token budget")
            return msg.content[0].text.strip()
        except Exception as e:
            anthropic_error = str(e)
            print(f"Anthropic error: {e}")

    if hf_client and HUGGINGFACE_API_TOKEN:
        try:
            response = hf_client.chat_completion(
                model="meta-llama/Llama-2-7b-chat-hf",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            hf_error = str(e)
            print(f"HuggingFace error: {e}")

    if not ANTHROPIC_API_KEY and not HUGGINGFACE_API_TOKEN:
        raise HTTPException(500, "No AI API keys configured.")

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


def _parse_json(raw: str) -> dict:
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


SUMMARIZE_PROMPT = """You are a senior product analyst. Given a PRD document, extract a structured summary.

Output ONLY valid JSON — no prose, no markdown fences.

Schema:
[
  {
    "screen_name": string,
    "description": string,
    "user_stories": [string],
    "input_fields": [string],
    "validations": [string],
    "error_conditions": [string],
    "acceptance_criteria": [string]
  }
]

Rules:
- Extract every distinct screen or feature section
- Keep each string short (under 20 words)
- input_fields: every form field, search box, dropdown, toggle
- error_conditions: every failure state, validation error, edge case mentioned
- acceptance_criteria: the must-pass conditions from the PRD
"""

TESTCASE_PROMPT = """You are a senior QA engineer. Given a screen summary and a specific test type, generate ONLY that type of test cases.

Output ONLY valid JSON array — no prose, no markdown fences.

Schema:
[
  {
    "id": string,
    "title": string,
    "type": string,
    "priority": "P0" | "P1" | "P2",
    "preconditions": [string],
    "steps": [string],
    "expected_result": string,
    "component": string
  }
]

Rules:
- P0: blocks core user journey (auth, payment, core CRUD)
- P1: important functionality with a workaround
- P2: edge case, cosmetic, nice-to-have
- IDs format: TC-001, TC-002, ... (continue from offset given)
- Steps: user-perspective actions ("Click", "Enter", "Navigate")
- Expected results: specific and observable

For each test type, generate exhaustively:
- happy_path: every successful user journey and valid workflow
- negative: every input field × (empty, invalid format, wrong type, boundary exceeded, special chars, SQL injection attempt, XSS attempt)
- edge_case: boundary values, max/min limits, simultaneous actions, race conditions, large data, empty states
- accessibility: keyboard navigation, screen reader labels, focus order, color contrast, ARIA roles, zoom to 200%
- error_states: network failure, timeout, server error, session expiry, permission denied, concurrent edit conflicts
"""

TEST_TYPES = ["happy_path", "negative", "edge_case", "accessibility", "error_states"]


def _chunk_text(text: str, chunk_size: int = 4000, overlap: int = 200) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _merge_screens(all_screens: list[list[dict]]) -> list[dict]:
    """Merge screen summaries extracted from multiple chunks, deduplicating by name."""
    merged: dict[str, dict] = {}
    for chunk_screens in all_screens:
        for screen in chunk_screens:
            name = screen.get("screen_name", "").strip()
            if not name:
                continue
            if name not in merged:
                merged[name] = screen
            else:
                existing = merged[name]
                for field in ("user_stories", "input_fields", "validations", "error_conditions", "acceptance_criteria"):
                    existing_vals = existing.get(field, [])
                    new_vals = screen.get(field, [])
                    combined = list(dict.fromkeys(existing_vals + new_vals))
                    existing[field] = combined
    return list(merged.values())


def generate_tests_two_pass(prd_text: str, project_name: str, filename: str = "") -> dict:
    """
    Pass 1: Chunk PRD → extract screen summaries from each chunk → merge.
    Pass 2: For each screen × each test type, generate focused test cases.
    Result: 300-500 test cases with full coverage, no token truncation.
    """

    # Pass 1 — chunk PRD and extract screens from each chunk
    chunks = _chunk_text(prd_text, chunk_size=4000, overlap=200)
    print(f"PRD split into {len(chunks)} chunks")

    chunk_screens = []
    for i, chunk in enumerate(chunks):
        try:
            raw = _call_llm(
                system=SUMMARIZE_PROMPT,
                user=f"Project: {project_name}\nChunk {i+1}/{len(chunks)}:\n\n{chunk}",
                max_tokens=1500,
            )
            screens = _parse_json(raw)
            if isinstance(screens, list):
                chunk_screens.append(screens)
        except Exception as e:
            print(f"Chunk {i+1} extraction failed: {e}")
            continue

    screens_summary = _merge_screens(chunk_screens)

    if not screens_summary:
        raise HTTPException(500, "Could not extract screens from PRD")

    # Pass 2 — per screen × per test type
    all_screens = []
    tc_offset = 1

    for screen in screens_summary:
        screen_name = screen.get("screen_name", "Unknown Screen")
        combined_test_cases = []

        for test_type in TEST_TYPES:
            user_msg = (
                f"Screen: {screen_name}\n"
                f"Test type to generate: {test_type}\n\n"
                f"Screen summary:\n{json.dumps(screen, indent=2)}\n\n"
                f"Start IDs from TC-{tc_offset:03d}. Generate ONLY {test_type} test cases. Be exhaustive."
            )
            try:
                raw = _call_llm(system=TESTCASE_PROMPT, user=user_msg, max_tokens=2000)
                test_cases = _parse_json(raw)
                if isinstance(test_cases, list):
                    combined_test_cases.extend(test_cases)
                    tc_offset += len(test_cases)
            except Exception as e:
                print(f"Skipping {test_type} for '{screen_name}': {e}")
                continue

        if combined_test_cases:
            all_screens.append({
                "screen_name": screen_name,
                "test_cases": combined_test_cases,
            })

    if not all_screens:
        raise HTTPException(500, "Failed to generate test cases for any screen")

    all_tcs = [tc for s in all_screens for tc in s.get("test_cases", [])]
    summary = {
        "total": len(all_tcs),
        "p0": sum(1 for t in all_tcs if t.get("priority") == "P0"),
        "p1": sum(1 for t in all_tcs if t.get("priority") == "P1"),
        "p2": sum(1 for t in all_tcs if t.get("priority") == "P2"),
        "happy_path": sum(1 for t in all_tcs if t.get("type") == "happy_path"),
        "negative": sum(1 for t in all_tcs if t.get("type") == "negative"),
        "edge_case": sum(1 for t in all_tcs if t.get("type") == "edge_case"),
        "accessibility": sum(1 for t in all_tcs if t.get("type") == "accessibility"),
        "error_states": sum(1 for t in all_tcs if t.get("type") == "error_states"),
    }

    return {
        "project": project_name,
        "source": "PRD",
        "filename": filename,
        "screens": all_screens,
        "summary": summary,
    }


def call_claude(user_message: str) -> dict:
    """Single-pass generation (used by Figma and /generate/prd)."""
    raw = _call_llm(system=SYSTEM_PROMPT, user=user_message, max_tokens=8000)
    return _parse_json(raw)

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

    return generate_tests_two_pass(text, project_name, filename=file.filename or "")

@app.post("/generate/prd")
def generate_from_prd(req: PRDRequest):
    if len(req.prd_text.strip()) < 50:
        raise HTTPException(400, "PRD text is too short")

    return generate_tests_two_pass(req.prd_text, req.project_name)

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