from __future__ import annotations

import jwt
from fastapi import HTTPException, Request, Security
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


async def require_user(request: Request) -> dict:
    """FastAPI dependency that verifies a JWT from cookie or Authorization header.

    Returns the decoded user payload: {userId, email, name, role}.
    """
    settings = get_settings()
    token = request.cookies.get("auth_token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return {
            "userId": decoded["userId"],
            "email": decoded["email"],
            "name": decoded["name"],
            "role": decoded["role"],
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
