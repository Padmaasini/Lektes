from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "TalentMesh"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./talentmesh.db"

    # LLM - Gemini (Free)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Email - Gmail SMTP (Free)
    GMAIL_USER: Optional[str] = None
    GMAIL_APP_PASSWORD: Optional[str] = None

    # LinkedIn (linkedin-api library - Free)
    LINKEDIN_USERNAME: Optional[str] = None
    LINKEDIN_PASSWORD: Optional[str] = None

    # GitHub (Free)
    GITHUB_TOKEN: Optional[str] = None

    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
