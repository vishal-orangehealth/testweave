# HuggingFace Fallback - Quick Deployment Guide

## ✅ What Was Updated

### 1. `render.yaml`
✅ Added `HUGGINGFACE_API_TOKEN` environment variable

```yaml
envVars:
  - key: ANTHROPIC_API_KEY
    sync: false
  - key: HUGGINGFACE_API_TOKEN    # ← NEW
    sync: false
```

### 2. `backend/requirements.txt`
✅ Added `huggingface-hub>=0.16.0` dependency

### 3. `backend/main.py`
✅ Updated imports to include HuggingFace support
✅ Added fallback logic in `call_claude()` function
✅ Updated health endpoint to show both providers

---

## 🚀 Deploy on Render

### Step 1: Get HuggingFace Token
1. Go to https://huggingface.co/settings/tokens
2. Click "New token"
3. Name: `testweave-api`
4. Role: **read**
5. Copy the token: `hf_xxxxxxxxxxxxxxx...`

### Step 2: Add to Render
1. Go to https://dashboard.render.com
2. Select **testweave-api** service
3. Click **Environment**
4. Add new variable:
   ```
   HUGGINGFACE_API_TOKEN = hf_xxxxxxxxxxxxxxx...
   ```
5. Click **Save Changes**
6. Wait for automatic redeploy (~2-3 min)

### Step 3: Verify
```bash
curl https://testweave-api.onrender.com/health
```

Expected response:
```json
{
  "status": "ok",
  "anthropic": true,
  "huggingface": true,
  "ai_available": true
}
```

---

## 🔄 How It Works

When a request comes in:

```
1. Try Anthropic Claude
   ✅ Success? Return result
   ❌ Error? Continue to step 2

2. Try HuggingFace
   ✅ Success? Return result
   ❌ Error? Return 500 error
```

---

## 📊 Files Changed

| File | Change |
|------|--------|
| `render.yaml` | Added HUGGINGFACE_API_TOKEN |
| `requirements.txt` | Added huggingface-hub |
| `main.py` | Dual provider logic + health endpoint |

---

## 💡 Benefits

✅ **Redundancy** - Service continues if one provider fails
✅ **Cost Control** - Can switch providers or use cheaper one
✅ **Reliability** - Automatic fallback mechanism
✅ **Scalability** - Easier to add more providers in future

---

## 🧪 Local Testing

### Test with Claude only
```bash
export ANTHROPIC_API_KEY=sk-ant-v0-xxxxx...
export HUGGINGFACE_API_TOKEN=
cd backend && uvicorn main:app --reload
```

### Test with HuggingFace only
```bash
export ANTHROPIC_API_KEY=
export HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx...
cd backend && uvicorn main:app --reload
```

### Test fallback
```bash
export ANTHROPIC_API_KEY=invalid_key  # Force failure
export HUGGINGFACE_API_TOKEN=hf_xxxxxxxxxxxxx...
cd backend && uvicorn main:app --reload

# Make a request - will use HuggingFace
curl -X POST http://localhost:8000/generate/prd \
  -H "Content-Type: application/json" \
  -d '{"prd_text": "Login page...", "project_name": "Test"}'
```

---

## ⚠️ Important Notes

1. **Both tokens are optional** - You need at least ONE
2. **Claude is tried first** - Faster and more accurate
3. **HuggingFace is automatic fallback** - You don't need to do anything
4. **Health endpoint shows status** - Use `/health` to check both

---

## 🎯 Next Steps

1. ✅ Get HuggingFace token
2. ✅ Add to Render environment
3. ✅ Wait for redeploy
4. ✅ Test health endpoint
5. ✅ Use your app as usual

**You're all set!** 🚀

---

## FAQ

**Q: Do I have to use HuggingFace?**
A: No, it's optional. Claude works fine alone.

**Q: Will it switch automatically?**
A: Yes, if Claude fails for any reason.

**Q: What if both fail?**
A: Returns a 500 error with clear message.

**Q: Does it cost more?**
A: No, you only pay what you use.

**Q: Can I add more providers?**
A: Yes! The code is structured to support more easily.

---

**Status:** Ready for deployment ✅
