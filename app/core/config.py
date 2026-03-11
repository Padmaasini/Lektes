from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Lektes"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./lektes.db"

    # LLM - Groq
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Email - Resend (replaces Gmail SMTP — works on Render free tier)
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: str = "Lektes <hr@nimbus-24.com>"

    # Email - Gmail SMTP (legacy fallback)
    GMAIL_USER: Optional[str] = None
    GMAIL_APP_PASSWORD: Optional[str] = None

    # LinkedIn
    LINKEDIN_USERNAME: Optional[str] = None
    LINKEDIN_PASSWORD: Optional[str] = None

    # GitHub
    GITHUB_TOKEN: Optional[str] = None

    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"

    # ── SECURITY ──────────────────────────────────────────────
    # Set LK_API_KEY on Render to protect all API endpoints.
    # Frontend passes this in X-API-Key header automatically.
    # Leave blank during local dev — all endpoints stay open.
    LK_API_KEY: Optional[str] = None

    # ── GDPR DATA RETENTION ───────────────────────────────────
    # Candidate CV data is auto-deleted after this many days.
    # Default 30 days — configurable per deployment.
    DATA_RETENTION_DAYS: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
