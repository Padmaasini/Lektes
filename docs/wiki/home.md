
# HRAssist (TalentMesh) — Project Wiki

## What Is This?
An AI-powered recruitment screening agent that:
- Accepts CV uploads via API
- Verifies profiles on LinkedIn and GitHub
- Ranks candidates by job fit with % match scores
- Sends ranked reports to HR via email
- Generates technical screening questions on request

## Build Started
📅 February 25, 2026

## Presentation Date
📅 March 19, 2026

## Tech Stack
- FastAPI + LangGraph
- Groq (free LLM)
- SQLite database
- linkedin-api (free LinkedIn data)
- GitHub REST API
- Gmail SMTP
- Render.com (hosting)

---

## Sprint Log

### Day 1 — February 25, 2026
✅ Full FastAPI project structure built
✅ All core endpoints scaffolded (jobs, candidates, screen, reports)
✅ Database models created (Job, Candidate, Screening)
✅ All services created (CV parser, LLM, LinkedIn, GitHub, Email, Questions)
✅ GitHub repository set up and code pushed
📁 Total: 34 files, 1499 lines of code
```

Scroll down → click **Commit new file**

---
### Day 2 — February 26, 2026
✅ Python 3.12 installed
✅ All dependencies installed  
✅ Gemini API configured
✅ API running locally at localhost:8000
✅ Swagger UI working with all endpoints
✅ Health check returning 200 OK
✅ Deployed to Render successfully
✅ Live at https://hrassist-dqb3.onrender.com/docs
🔄 BigRock domain connection in progress


```
docs/
├── wiki/
│   ├── home.md              ← Project overview
│   ├── sprint-log.md        ← Daily build diary
│   └── architecture.md      ← How the system works
├── api-reference.md         ← Every endpoint documented
├── local-setup.md           ← How to run locally
└── deployment.md            ← How to deploy to Render
