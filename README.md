# TestWeave — AI QA Test Case Generator

Generate structured, prioritised test cases from a PRD document or Figma design file — powered by Claude.

**Live stack:**
- Frontend → Vercel (free)
- Backend → Render (free)
- AI → Anthropic Claude (pay-per-use, ~$0.001 per generation)

---

## Project structure

```
testweave/
├── backend/
│   ├── main.py           ← FastAPI app (all logic here)
│   └── requirements.txt
├── frontend/
│   ├── public/index.html
│   └── src/
│       ├── App.js        ← Full React app
│       ├── App.css       ← All styles
│       └── index.js
├── render.yaml           ← Render deploy config
├── vercel.json           ← Vercel deploy config
└── README.md
```

---

## Local development

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000
```

Backend runs at: http://localhost:8000
API docs at: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install

# Create .env.local
echo "REACT_APP_API_URL=http://localhost:8000" > .env.local

npm start
```

Frontend runs at: http://localhost:3000

---

## Deploy — Backend on Render (free)

1. Push this repo to GitHub
2. Go to https://render.com → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Plan: **Free**
5. Environment Variables:
   - `ANTHROPIC_API_KEY` → your key from https://console.anthropic.com
6. Click Deploy

Note your backend URL: `https://testweave-api.onrender.com`

> Free Render instances spin down after 15 min of inactivity. First request after sleep takes ~30s.
> Upgrade to Starter ($7/mo) to keep it always-on.

---

## Deploy — Frontend on Vercel (free)

1. Go to https://vercel.com → New Project
2. Import your GitHub repo
3. Framework: **Other** (or Create React App)
4. Build settings (auto-detected from vercel.json):
   - Build Command: `cd frontend && npm install && npm run build`
   - Output Directory: `frontend/build`
5. Environment Variables:
   - `REACT_APP_API_URL` → your Render backend URL (e.g. `https://testweave-api.onrender.com`)
6. Deploy

---

## How to get a Figma access token

1. Open Figma → Account Settings (top-left avatar)
2. Scroll to "Personal access tokens"
3. Click "Generate new token"
4. Name it "TestWeave", copy the token (starts with `figd_`)
5. The token is sent directly to the Figma API — never stored anywhere

---

## API reference

### POST /generate/prd
```json
{
  "prd_text": "## Login screen\nUsers must be able to...",
  "project_name": "My App v2"
}
```

### POST /generate/figma
```json
{
  "figma_url": "https://www.figma.com/file/ABC123/My-Design",
  "figma_token": "figd_...",
  "project_name": "My App v2"
}
```

### Response shape
```json
{
  "project": "My App v2",
  "source": "PRD",
  "screens": [
    {
      "screen_name": "Login screen",
      "test_cases": [
        {
          "id": "TC-001",
          "title": "Login with valid credentials",
          "type": "happy_path",
          "priority": "P0",
          "preconditions": ["User account exists"],
          "steps": ["Enter valid email", "Enter password", "Click Sign in"],
          "expected_result": "User is redirected to dashboard",
          "component": "Button/Primary"
        }
      ]
    }
  ],
  "summary": {
    "total": 24,
    "p0": 6,
    "p1": 12,
    "p2": 6,
    "happy_path": 8,
    "negative": 10,
    "edge_case": 4,
    "accessibility": 2
  }
}
```

---

## Extending this project

| Feature | How |
|---|---|
| Export to Jira | POST to Jira REST API with each test case as an issue |
| Playwright skeleton | Third Claude pass: convert test cases to `test('...', async ({ page }) => {...})` stubs |
| Notion output | Use Notion API to create a database with test cases as rows |
| Auth | Add API key validation middleware in FastAPI |
| History | SQLite + `/sessions` endpoint to store past generations |
| Slack bot | Slash command `/testweave [figma-url]` triggers generation |
