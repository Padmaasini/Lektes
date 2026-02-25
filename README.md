# 🎯 TalentMesh API

> AI-powered recruitment screening agent. Upload CVs, verify profiles across LinkedIn and GitHub, and receive a ranked candidate report — all via API.

---

## Quick Start (Local)

### 1. Clone and setup
```bash
git clone https://github.com/yourusername/talentmesh
cd talentmesh
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Run
```bash
python run.py
```

API is live at: `http://localhost:8000`
Swagger docs at: `http://localhost:8000/docs`

---

## API Keys You Need (All Free)

| Service | Purpose | Get It |
|---|---|---|
| Groq | LLM for CV parsing & scoring | console.groq.com |
| LinkedIn | Profile verification | Secondary LinkedIn account |
| GitHub | Developer profile check | github.com/settings/tokens |
| Gmail | Send reports to HR | Gmail App Password |

---

## Core API Flow

```
1. POST /api/v1/jobs              → Create job with description
2. POST /api/v1/candidates/upload/{job_id} → Upload CVs
3. POST /api/v1/screen/{job_id}   → Trigger screening
4. GET  /api/v1/screen/status/{id}→ Check progress
5. GET  /api/v1/reports/{job_id}  → Get ranked report
6. POST /api/v1/reports/{job_id}/send → Email report to HR
```

---

## Deploy to Render (Free)

1. Push this repo to GitHub
2. Go to render.com → New Web Service
3. Connect your GitHub repo
4. Add environment variables from `.env.example`
5. Deploy — your API will be live at `https://talentmesh.onrender.com`

---

## Powered By (100% Free Stack)

- **FastAPI** — API framework
- **LangGraph** — Agent pipeline
- **Groq + Llama 3.1** — Free LLM
- **linkedin-api** — LinkedIn data
- **GitHub REST API** — Developer profiles
- **Gmail SMTP** — Report delivery
- **SQLite** — Database
- **Render.com** — Hosting
