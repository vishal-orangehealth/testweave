# HuggingFace API Fallback Configuration

## Overview

Your TestWeave application now supports **dual AI providers** with automatic fallback:

1. **Primary:** Anthropic Claude API (preferred)
2. **Fallback:** HuggingFace Inference API (if Claude unavailable)

---

## Why HuggingFace as Fallback?

✅ **Redundancy** - If Anthropic is down, HuggingFace takes over  
✅ **Cost flexibility** - Choose cheaper option based on usage  
✅ **Reliability** - Service continues even if one provider fails  
✅ **Model variety** - Access to different AI models (Llama, Mistral, etc.)

---

## Setup Instructions

### 1. Update `render.yaml` (Already Done ✅)

Your `render.yaml` now includes:

```yaml
envVars:
  - key: ANTHROPIC_API_KEY
    sync: false
  - key: HUGGINGFACE_API_TOKEN
    sync: false
```

### 2. Get HuggingFace API Token

1. Go to https://huggingface.co/settings/tokens
2. Click "New token"
3. Name: `testweave-api`
4. Role: **read** (minimum required)
5. Copy the token

### 3. Add to Render Dashboard

1. Go to your Render service dashboard: https://dashboard.render.com
2. Select **testweave-api** service
3. Go to **Environment** → **Environment Variables**
4. Add:
   ```
   Key: HUGGINGFACE_API_TOKEN
   Value: hf_xxxxxxxxxxxxx...
   ```
5. Click **Save Changes**
6. Service will auto-redeploy

---

## How It Works

### AI Provider Selection Flow

```
Request comes in
    ↓
Try Anthropic Claude
    ├─ ✅ Success? → Return result
    └─ ❌ Failed? → Try HuggingFace
        ├─ ✅ Success? → Return result
        └─ ❌ Failed? → Return error
```

### Example Error Handling

```python
call_claude(user_message)
    ↓
if ANTHROPIC_API_KEY available:
    try:
        response = client.messages.create(...)  # Claude
        return json.loads(response)
    except Exception:
        print("Claude failed, trying HuggingFace...")
        
if HUGGINGFACE_API_TOKEN available:
    try:
        response = hf_client.text_generation(...)  # HuggingFace
        return json.loads(response)
    except Exception:
        raise "Both providers failed"
```

---

## Health Check Endpoint

The `/health` endpoint now shows both providers:

```bash
curl https://testweave-api.onrender.com/health
```

Response:
```json
{
  "status": "ok",
  "docx": true,
  "pdf": true,
  "anthropic": true,
  "huggingface": true,
  "ai_available": true
}
```

Meaning:
- `anthropic`: true = ANTHROPIC_API_KEY is configured
- `huggingface`: true = HUGGINGFACE_API_TOKEN is configured
- `ai_available`: true = At least one provider is available ✅

---

## Configuration Scenarios

### Scenario 1: Both Providers (Recommended)
```
ANTHROPIC_API_KEY = sk-ant-v0-xxx...
HUGGINGFACE_API_TOKEN = hf_xxxxxxxxxxxx

Status: ✅ Optimal
Behavior: Uses Claude, falls back to HuggingFace if needed
```

### Scenario 2: Anthropic Only (Current Setup)
```
ANTHROPIC_API_KEY = sk-ant-v0-xxx...
HUGGINGFACE_API_TOKEN = (empty)

Status: ✅ Works
Behavior: Uses Claude only, no fallback
```

### Scenario 3: HuggingFace Only
```
ANTHROPIC_API_KEY = (empty)
HUGGINGFACE_API_TOKEN = hf_xxxxxxxxxxxx

Status: ✅ Works
Behavior: Uses HuggingFace only
```

### Scenario 4: No Providers (Don't Do This)
```
ANTHROPIC_API_KEY = (empty)
HUGGINGFACE_API_TOKEN = (empty)

Status: ❌ Fails
Behavior: Returns 500 error
Error: "No AI API keys configured"
```

---

## HuggingFace Model Selection

HuggingFace Inference API uses different models. For test case generation, these work well:

| Model | Pros | Cons |
|-------|------|------|
| **Meta-Llama-3-70B** | Fast, accurate | Moderate cost |
| **Mistral-7B-Instruct** | Very fast, cheap | Less accurate |
| **Neural-Chat-7B** | Fast, reliable | Good for Q&A |
| **CodeLlama-34B** | Good logic | Overkill for test cases |

**Default**: HuggingFace auto-selects the best available model.

---

## Cost Comparison

### Anthropic Claude
```
Input: $3 per 1M tokens
Output: $15 per 1M tokens

Estimate per 100 test cases:
~15,000 tokens used = ~$0.05-0.10
```

### HuggingFace (Pay-as-you-go)
```
Inference API: $0.0000006 per request (approx)
Or: Free tier with rate limits

Estimate per 100 test cases:
~0.001 tokens = ~$0.001 or free
```

**HuggingFace is typically cheaper** for high volume, but Claude may be faster/more accurate.

---

## Environment Variables Reference

Add these to your `.env.local` for local testing:

```bash
# Backend/.env
ANTHROPIC_API_KEY=sk-ant-v0-xxxxx...
HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx...
```

Then in your shell:
```bash
export ANTHROPIC_API_KEY=sk-ant-v0-xxxxx...
export HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx...
```

Or pass directly:
```bash
ANTHROPIC_API_KEY=sk-ant-v0-xxxxx... \
HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx... \
uvicorn main:app --reload
```

---

## Local Testing

### Test Claude Only
```bash
export ANTHROPIC_API_KEY=sk-ant-v0-xxxxx...
export HUGGINGFACE_API_TOKEN=
uvicorn main:app --reload
```

Check health:
```bash
curl http://localhost:8000/health
```

Response should show:
```json
{"anthropic": true, "huggingface": false, "ai_available": true}
```

### Test HuggingFace Only
```bash
export ANTHROPIC_API_KEY=
export HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx...
uvicorn main:app --reload
```

### Test Fallback Behavior
```bash
# Force Claude to fail by using invalid key
export ANTHROPIC_API_KEY=invalid_key
export HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx...
uvicorn main:app --reload

# Now test - will use HuggingFace
curl -X POST http://localhost:8000/generate/prd \
  -H "Content-Type: application/json" \
  -d '{"prd_text": "Login feature...", "project_name": "Test"}'
```

---

## Backend Code Changes

### Files Modified

**1. `render.yaml`**
```yaml
# Added:
- key: HUGGINGFACE_API_TOKEN
  sync: false
```

**2. `backend/main.py`**

Imports:
```python
try:
    from huggingface_hub import InferenceClient
    HAS_HUGGINGFACE = True
except ImportError:
    HAS_HUGGINGFACE = False
```

Initialization:
```python
HUGGINGFACE_API_TOKEN = os.environ.get("HUGGINGFACE_API_TOKEN", "")
hf_client = None
if HAS_HUGGINGFACE and HUGGINGFACE_API_TOKEN:
    hf_client = InferenceClient(api_key=HUGGINGFACE_API_TOKEN)
```

Function:
```python
def call_claude(user_message: str) -> dict:
    # Try Anthropic first
    if client and ANTHROPIC_API_KEY:
        try:
            msg = client.messages.create(...)
            return json.loads(response)
        except Exception:
            pass  # Fall through
    
    # Try HuggingFace
    if hf_client and HUGGINGFACE_API_TOKEN:
        try:
            response = hf_client.text_generation(...)
            return json.loads(response)
        except Exception:
            raise
    
    # Neither available
    raise HTTPException(500, "No AI API keys configured")
```

Health endpoint:
```python
@app.get("/health")
def health():
    return {
        "status": "ok",
        "anthropic": bool(ANTHROPIC_API_KEY),
        "huggingface": bool(HUGGINGFACE_API_TOKEN),
        "ai_available": bool(ANTHROPIC_API_KEY or HUGGINGFACE_API_TOKEN),
    }
```

---

## Troubleshooting

### "HUGGINGFACE_API_TOKEN not found"
**Solution:** Add to Render dashboard environment variables

### "huggingface_hub import failed"
**Solution:** Update `requirements.txt` with:
```bash
pip install huggingface-hub
```

Add to `backend/requirements.txt`:
```
huggingface-hub>=0.16.0
```

Then redeploy on Render.

### "Both AI providers failed"
**Possible Causes:**
- Invalid tokens
- Rate limits exceeded
- Network issues
- Service downtime

**Check:**
```bash
curl https://testweave-api.onrender.com/health
```

If `ai_available` is false, both providers are misconfigured.

### "HuggingFace taking too long"
**Solution:** HuggingFace inference can be slow. Consider:
1. Using Claude for faster responses
2. Requesting smaller outputs
3. Using a faster HF model

---

## Next Steps

1. ✅ Get HuggingFace API token from https://huggingface.co/settings/tokens
2. ✅ Add `HUGGINGFACE_API_TOKEN` to Render environment variables
3. ✅ Verify health endpoint shows both providers
4. ✅ Test generation with both providers available
5. ✅ (Optional) Update `requirements.txt` if needed

---

## Summary

Your TestWeave now has:
- ✅ **Primary:** Anthropic Claude (fast, accurate)
- ✅ **Fallback:** HuggingFace (redundancy, cost savings)
- ✅ **Smart Routing:** Tries Claude first, uses HF if needed
- ✅ **Health Monitoring:** Endpoint shows both provider status

**Benefits:**
- No service interruption if one provider has issues
- Cost optimization based on provider pricing
- Better reliability for production use
- Future-proof for more providers

---

**Configuration Status:**
- `render.yaml` ✅ Updated with HUGGINGFACE_API_TOKEN
- `backend/main.py` ✅ Updated with fallback logic
- Health endpoint ✅ Shows both providers
- Ready for deployment ✅

Just add your HuggingFace token to Render and you're good to go! 🚀
