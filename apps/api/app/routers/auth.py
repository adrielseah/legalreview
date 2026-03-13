"""Authentication routes: OTP-based login, logout, /me, demo-login."""

from __future__ import annotations

import logging

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "auth_token"


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "max_age": settings.jwt_expiry_hours * 3600,
        "path": "/",
    }


def _sign_token(user: dict) -> str:
    import jwt

    payload = {
        "userId": user["userId"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


# ─── Request OTP ──────────────────────────────────────────────────────────────


class OtpRequestInput(BaseModel):
    email: str


@router.post("/request-otp")
async def handle_request_otp(body: OtpRequestInput) -> dict:
    try:
        from app.services.otp import request_otp
        result = await request_otp(body.email)
        return {"success": True, "data": result}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("request-otp failed")
        return {"success": False, "error": "Failed to send OTP"}


# ─── Verify OTP ───────────────────────────────────────────────────────────────


class OtpVerifyInput(BaseModel):
    email: str
    otp: str


@router.post("/verify-otp")
async def handle_verify_otp(body: OtpVerifyInput, response: Response) -> dict:
    try:
        from app.services.otp import verify_otp
        user = await verify_otp(body.email, body.otp)
        token = _sign_token(user)
        response.set_cookie(COOKIE_NAME, token, **_cookie_options())
        return {"success": True, "data": {"token": token, "user": user}}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("verify-otp failed")
        return {"success": False, "error": "Verification failed"}


# ─── Logout ───────────────────────────────────────────────────────────────────


@router.post("/logout")
async def handle_logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=True, samesite="lax")
    return {"success": True, "message": "Logged out successfully"}


# ─── Demo Login ───────────────────────────────────────────────────────────────


class DemoLoginInput(BaseModel):
    role: str = "user"


@router.post("/demo-login")
async def handle_demo_login(body: DemoLoginInput, response: Response) -> dict:
    from app.services.otp import _supabase

    try:
        demo_email = "demo-admin@open.gov.sg" if body.role == "admin" else "demo-user@open.gov.sg"
        demo_name = "Demo Admin" if body.role == "admin" else "Demo User"
        demo_role = "admin" if body.role == "admin" else "user"

        sb = _supabase()
        result = sb.table("users").select("*").eq("email", demo_email).limit(1).execute()
        users = result.data or []

        if users:
            user = users[0]
        else:
            sb.table("users").insert({"email": demo_email, "name": demo_name, "role": demo_role}).execute()
            new_user_result = sb.table("users").select("*").eq("email", demo_email).limit(1).execute()
            new_users = new_user_result.data or []
            if not new_users:
                raise RuntimeError("Failed to create demo user")
            user = new_users[0]

        user_data = {"userId": user["id"], "email": user["email"], "name": user.get("name") or "", "role": user["role"]}
        token = _sign_token(user_data)
        response.set_cookie(COOKIE_NAME, token, **_cookie_options())
        return {"success": True, "data": {"token": token, "user": user_data}}
    except Exception as e:
        logger.exception("demo-login failed")
        return {"success": False, "error": str(e)}


# ─── Me (verify token) ───────────────────────────────────────────────────────


@router.get("/me")
async def handle_me(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return {"success": False, "error": "Not authenticated"}

    import jwt

    try:
        decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return {
            "success": True,
            "data": {
                "userId": decoded["userId"],
                "email": decoded["email"],
                "name": decoded["name"],
                "role": decoded["role"],
            },
        }
    except jwt.ExpiredSignatureError:
        return {"success": False, "error": "Token expired"}
    except jwt.InvalidTokenError:
        return {"success": False, "error": "Invalid or expired token"}
