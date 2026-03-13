"""OTP generation, hashing, verification, and email delivery."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone

import httpx
from supabase import create_client

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def validate_email(email: str) -> str | None:
    """Return error string if invalid, else None."""
    import re

    normalized = email.lower().strip()
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", normalized):
        return "Invalid email address"
    if not any(normalized.endswith(d) for d in settings.allowed_email_domains):
        return f"Email must end with {' or '.join(settings.allowed_email_domains)}"
    return None


def generate_otp() -> str:
    num = secrets.randbelow(900000) + 100000
    return str(num)


def hash_otp(otp: str, email: str) -> str:
    normalized = email.lower().strip()
    return hmac.new(normalized.encode(), otp.encode(), hashlib.sha256).hexdigest()


def compare_hashes(h1: str, h2: str) -> bool:
    return hmac.compare_digest(h1, h2)


def extract_name_from_email(email: str) -> str:
    local = email.split("@")[0]
    import re

    parts = re.split(r"[._\-]", local)
    return " ".join(p.capitalize() for p in parts)


ADMIN_EMAILS = ["daniellow@open.gov.sg"]


async def send_otp_email(email: str, otp: str) -> None:
    if not settings.postman_api_key:
        logger.info("[DEV] No POSTMAN_API_KEY set. OTP for %s: %s", email, otp)
        return

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #1e40af;">ClauseLens Login</h2>
      <p>Your one-time password (OTP) is:</p>
      <div style="background-color: #f3f4f6; border-radius: 8px; padding: 24px; text-align: center; margin: 24px 0;">
        <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1e40af;">{otp}</span>
      </div>
      <p style="color: #6b7280; font-size: 14px;">
        This code will expire in <strong>{settings.otp_expiry_minutes} minutes</strong>.
      </p>
      <p style="color: #6b7280; font-size: 14px;">
        If you did not request this code, please ignore this email.
      </p>
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
      <p style="color: #9ca3af; font-size: 12px;">
        This is an automated message from ClauseLens.
      </p>
    </div>
    """

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.postman.gov.sg/v1/transactional/email/send",
                headers={
                    "Authorization": f"Bearer {settings.postman_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "subject": f"Your login code: {otp}",
                    "body": html_body,
                    "recipient": email,
                    "from": f"{settings.email_from_name} <info@mail.postman.gov.sg>",
                },
                timeout=15,
            )
            if resp.status_code >= 400:
                logger.error("Postman API error (%s): %s", resp.status_code, resp.text)
            else:
                logger.info("OTP email sent to %s", email)
    except Exception as exc:
        logger.error("Failed to send OTP email: %s", exc)


async def request_otp(email: str) -> dict:
    err = validate_email(email)
    if err:
        raise ValueError(err)

    normalized = email.lower().strip()
    sb = _supabase()

    # Invalidate existing unused OTPs
    now = datetime.now(timezone.utc).isoformat()
    sb.table("otp_records").update({"expires_at": now}).eq("email", normalized).is_("used_at", "null").gt("expires_at", now).execute()

    otp = generate_otp()
    otp_hash = hash_otp(otp, normalized)

    from datetime import timedelta

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)).isoformat()
    sb.table("otp_records").insert({"email": normalized, "otp_hash": otp_hash, "expires_at": expires_at}).execute()

    logger.info("[OTP] Code for %s: %s", normalized, otp)

    # Send email in background (fire-and-forget)
    import asyncio

    asyncio.create_task(send_otp_email(normalized, otp))

    return {"message": "OTP sent to your email address"}


async def verify_otp(email: str, otp: str) -> dict:
    err = validate_email(email)
    if err:
        raise ValueError(err)

    if not otp.isdigit() or len(otp) != 6:
        raise ValueError("OTP must be exactly 6 digits")

    normalized = email.lower().strip()
    sb = _supabase()
    now = datetime.now(timezone.utc).isoformat()

    # Find the most recent valid OTP
    result = (
        sb.table("otp_records")
        .select("*")
        .eq("email", normalized)
        .is_("used_at", "null")
        .gt("expires_at", now)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    records = result.data or []
    if not records:
        raise ValueError("No valid OTP found. Please request a new one.")

    record = records[0]

    if record["attempts"] >= settings.otp_max_attempts:
        sb.table("otp_records").update({"expires_at": now}).eq("id", record["id"]).execute()
        raise ValueError("Maximum attempts exceeded. Please request a new OTP.")

    provided_hash = hash_otp(otp, normalized)
    if not compare_hashes(provided_hash, record["otp_hash"]):
        new_attempts = record["attempts"] + 1
        sb.table("otp_records").update({"attempts": new_attempts}).eq("id", record["id"]).execute()
        remaining = settings.otp_max_attempts - new_attempts
        raise ValueError(f"Invalid OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining.")

    # Mark as used
    sb.table("otp_records").update({"used_at": now}).eq("id", record["id"]).execute()

    # Find or create user
    user_result = sb.table("users").select("*").eq("email", normalized).limit(1).execute()
    users = user_result.data or []

    if users:
        user = users[0]
        return {"userId": user["id"], "email": user["email"], "name": user.get("name") or "", "role": user["role"]}

    name = extract_name_from_email(normalized)
    role = "admin" if normalized in ADMIN_EMAILS else "user"

    sb.table("users").insert({"email": normalized, "name": name, "role": role}).execute()
    new_user_result = sb.table("users").select("*").eq("email", normalized).limit(1).execute()
    new_users = new_user_result.data or []
    if not new_users:
        raise RuntimeError("Failed to create user")
    user = new_users[0]
    return {"userId": user["id"], "email": user["email"], "name": user.get("name") or "", "role": user["role"]}
