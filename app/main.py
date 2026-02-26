import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import jobs, candidates, screen, reports, health
from app.core.config import settings

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

@app.get("/", tags=["Frontend"])
async def frontend():
    # Try multiple possible locations for index.html
    possible_paths = [
        "index.html",                                          # root of project
        os.path.join(os.getcwd(), "index.html"),              # absolute cwd
        os.path.join(os.path.dirname(__file__), "..", "index.html"),  # relative to app/
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")

    # Fallback if file not found — redirect to docs
    return HTMLResponse("""
    <html>
    <body style="font-family:sans-serif;text-align:center;padding:80px;background:#faf7f2">
        <h1 style="color:#2d7a4f">TalentMesh API is Running</h1>
        <p>Frontend file not found. <a href="/docs">Open API Docs →</a></p>
        <p style="color:#999;font-size:12px">index.html not found in: """ + str(possible_paths) + """</p>
    </body>
    </html>
    """, status_code=200)
