from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin(key: str | None = Security(_admin_key_header)) -> None:
    """FastAPI dependency that enforces the admin API key on protected routes.

    Set ADMIN_API_KEY in the environment. Any request to a route that depends
    on this function must supply a matching X-Admin-Key header.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="Admin access is not configured on this server.",
        )
    if key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
