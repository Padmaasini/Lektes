import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import jobs, candidates, screen, reports, health
from app.core.config import settings
from fastapi.responses import FileResponse, HTMLResponse


app = FastAPI(
    title="TalentMesh API",
    description="AI-powered recruitment screening agent. Upload CVs, verify profiles, and get ranked candidate reports.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["Health"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Jobs"])
app.include_router(candidates.router, prefix="/api/v1/candidates", tags=["Candidates"])
app.include_router(screen.router, prefix="/api/v1/screen", tags=["Screening"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])

@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "TalentMesh API",
        "version": "0.1.0",
        "status": "running",
        "message": "AI-powered recruitment screening agent",
        "docs": "/docs"
        }

@app.get("/")
async def frontend():
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>TalentMesh API is running</h1><p>Visit <a href='/docs'>/docs</a></p>")
