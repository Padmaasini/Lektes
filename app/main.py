"""
Lektes API — main application entry point.

Security: slowapi rate limiting (60 req/min per IP)
GDPR: startup cleanup of expired candidate records
New: /api/v1/feedback router, /api/v1/health/config endpoint
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.endpoints import jobs, candidates, screen, reports, health, feedback, analytics, notify
from app.core.config import settings
from app.core.database import SessionLocal, init_db

logger = logging.getLogger(__name__)

# ── RATE LIMITER ──────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


# ── GDPR STARTUP CLEANUP ──────────────────────────────────────
def purge_expired_candidates() -> int:
    db = SessionLocal()
    try:
        from app.models.candidate import Candidate
        expired = (
            db.query(Candidate)
            .filter(Candidate.expires_at.isnot(None))
            .filter(Candidate.expires_at < datetime.utcnow())
            .all()
        )
        count = 0
        for c in expired:
            if c.cv_file_path and os.path.exists(c.cv_file_path):
                try:
                    os.remove(c.cv_file_path)
                except OSError:
                    pass
            db.delete(c)
            count += 1
        if count:
            db.commit()
        return count
    except Exception as e:
        logger.error(f"[GDPR] Cleanup error: {e}")
        return 0
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    purged = purge_expired_candidates()
    if purged:
        logger.info(f"[Startup] GDPR cleanup: removed {purged} expired candidate records.")
    yield


# ── APP ────────────────────────────────────────────────────────
app = FastAPI(
    title       = "Lektes API",
    description = "AI-powered recruitment screening — parse CVs, verify profiles, rank candidates.",
    version     = "0.2.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ───────────────────────────────────────────────────────
ALLOWED_ORIGINS = (
    ["https://lektes.nimbus-24.com"]
    if not settings.DEBUG
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
)

# ── ROUTERS ────────────────────────────────────────────────────
app.include_router(health.router,     tags=["Health"])
app.include_router(jobs.router,       prefix="/api/v1/jobs",       tags=["Jobs"])
app.include_router(candidates.router, prefix="/api/v1/candidates", tags=["Candidates"])
app.include_router(screen.router,     prefix="/api/v1/screen",     tags=["Screening"])
app.include_router(reports.router,    prefix="/api/v1/reports",    tags=["Reports"])
app.include_router(feedback.router,   prefix="/api/v1/feedback",   tags=["Feedback"])
app.include_router(analytics.router,  prefix="/api/v1",             tags=["Analytics"])
app.include_router(notify.router,     prefix="/api/v1/notify",     tags=["Notify"])


# ── FRONTEND ────────────────────────────────────────────────────
@app.get("/", tags=["Frontend"])
async def frontend():
    for path in [
        "index.html",
        os.path.join(os.getcwd(), "index.html"),
        os.path.join(os.path.dirname(__file__), "..", "index.html"),
    ]:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return HTMLResponse("""
    <html><body style="font-family:sans-serif;text-align:center;padding:80px;background:#faf7f2">
        <h1 style="color:#2d7a4f">Lektes API is Running</h1>
        <p>Frontend not found. <a href="/docs">Open API Docs →</a></p>
    </body></html>
    """, status_code=200)


# ── CONFIG ENDPOINT (public) ───────────────────────────────────
@app.get("/api/v1/health/config", tags=["Health"])
async def get_config():
    """Tells frontend whether API key auth is active. Never returns the key itself."""
    return {
        "api_key_required":  bool(settings.LK_API_KEY),
        "resend_configured": bool(settings.RESEND_API_KEY),
        "retention_days":    settings.DATA_RETENTION_DAYS,
        "version":           settings.APP_VERSION,
    }
