"""
Lektes API Security
-----------------------
API key authentication via X-API-Key header.

How it works:
- If LK_API_KEY is set in Render environment → all protected endpoints
  require the header: X-API-Key: <your key>
- If LK_API_KEY is NOT set (local dev) → all endpoints are open,
  no header required. Safe for development, locked for production.

Usage in endpoints:
    from app.core.security import require_api_key
    @router.post("/")
    async def create(..., _: None = Depends(require_api_key)):
        ...

The frontend (index.html) reads LK_API_KEY from the
/api/v1/health/config endpoint and sets it automatically on
every fetch request — HR users never see or type the key.
"""

from fastapi import Header, HTTPException, status
from app.core.config import settings


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """
    Dependency that enforces API key when LK_API_KEY is configured.
    Attach to any endpoint that should be protected.
    """
    if not settings.LK_API_KEY:
        # No key configured — open access (local dev mode)
        return
    if x_api_key != settings.LK_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Set X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def optional_api_key(x_api_key: str = Header(default="")) -> bool:
    """
    Soft check — returns True if valid key provided, False if not.
    Use for endpoints that work both authenticated and anonymously
    but may return different data.
    """
    if not settings.LK_API_KEY:
        return True
    return x_api_key == settings.LK_API_KEY
