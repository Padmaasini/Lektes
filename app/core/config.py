from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME:    str = "TalentMesh"
    APP_VERSION: str = "1.0.0"
    DEBUG:       bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./talentmesh.db"

    # LLM — Groq (required)
    GROQ_API_KEY: Optional[str] = None

    # Email reporting — Gmail SMTP (required for email)
    GMAIL_USER:         Optional[str] = None
    GMAIL_APP_PASSWORD: Optional[str] = None

    # Profile verification — GitHub (optional, raises rate limit 60→5000/hr)
    GITHUB_TOKEN: Optional[str] = None

    # Email — Resend API (replaces Gmail SMTP, works on Render free tier)
    RESEND_API_KEY: Optional[str] = None

    # Profile verification — Kaggle (required for Kaggle verification)
    KAGGLE_USERNAME: Optional[str] = None
    KAGGLE_KEY:      Optional[str] = None

    # File upload
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR:       str = "./uploads"

    class Config:
        env_file      = ".env"
        case_sensitive = True


settings = Settings()
