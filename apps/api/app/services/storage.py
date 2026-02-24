"""
Storage abstraction layer.

Production: Supabase Storage (via supabase-py client)
Local dev:  MinIO (via boto3 S3-compatible API)

Both paths implement the same interface:
  - generate_upload_url(bucket, key, expires_in) -> str
  - download_bytes(bucket, key) -> bytes
  - upload_bytes(bucket, key, data, content_type) -> None
  - move_object(bucket, src_key, dst_key) -> None
  - ensure_bucket_exists(bucket) -> None
"""

from __future__ import annotations

import logging
from io import BytesIO

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config as BotoConfig

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── MinIO / S3-compatible client ─────────────────────────────────────────────

def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.minio_secure else ''}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _get_supabase_storage():
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return client.storage


# ─── Public interface ──────────────────────────────────────────────────────────

def generate_upload_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Return a presigned PUT URL for direct browser upload."""
    if settings.storage_backend == "supabase":
        storage = _get_supabase_storage()
        res = storage.from_(bucket).create_signed_upload_url(key)
        # supabase-py v1 uses "signedURL", v2 uses "signedUrl" or nested "data"
        if isinstance(res, dict):
            url = (
                res.get("signedURL")
                or res.get("signedUrl")
                or res.get("signed_url")
            )
            if not url and "data" in res:
                data = res["data"] or {}
                url = (
                    data.get("signedURL")
                    or data.get("signedUrl")
                    or data.get("signed_url")
                )
            if url:
                return url
        raise ValueError(f"Could not extract signed URL from Supabase response: {res}")
    else:
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url


def download_bytes(bucket: str, key: str) -> bytes:
    """Download an object and return its bytes."""
    if settings.storage_backend == "supabase":
        storage = _get_supabase_storage()
        res = storage.from_(bucket).download(key)
        return res
    else:
        s3 = _get_s3_client()
        buf = BytesIO()
        s3.download_fileobj(bucket, key, buf)
        return buf.getvalue()


def upload_bytes(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload bytes to storage."""
    if settings.storage_backend == "supabase":
        storage = _get_supabase_storage()
        storage.from_(bucket).upload(
            path=key,
            file=data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    else:
        s3 = _get_s3_client()
        s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def move_object(bucket: str, src_key: str, dst_key: str) -> None:
    """Move (copy + delete) an object within the same bucket."""
    if settings.storage_backend == "supabase":
        storage = _get_supabase_storage()
        storage.from_(bucket).move(src_key, dst_key)
    else:
        s3 = _get_s3_client()
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": src_key},
            Key=dst_key,
        )
        s3.delete_object(Bucket=bucket, Key=src_key)


def delete_object(bucket: str, key: str) -> None:
    """Delete a single object from storage (best-effort)."""
    if settings.storage_backend == "supabase":
        storage = _get_supabase_storage()
        storage.from_(bucket).remove([key])
    else:
        s3 = _get_s3_client()
        s3.delete_object(Bucket=bucket, Key=key)


def ensure_bucket_exists(bucket: str) -> None:
    """Create bucket if it doesn't already exist."""
    if settings.storage_backend == "supabase":
        storage = _get_supabase_storage()
        try:
            storage.get_bucket(bucket)
        except Exception:
            storage.create_bucket(bucket, options={"public": False})
            logger.info("Created Supabase storage bucket: %s", bucket)
    else:
        s3 = _get_s3_client()
        try:
            s3.head_bucket(Bucket=bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                s3.create_bucket(Bucket=bucket)
                logger.info("Created MinIO bucket: %s", bucket)
            else:
                raise


def startup_ensure_buckets() -> None:
    """Called at FastAPI startup to ensure both storage buckets exist."""
    for bucket in [settings.bucket_raw, settings.bucket_derived]:
        try:
            ensure_bucket_exists(bucket)
        except Exception as exc:
            logger.warning("Could not ensure bucket %s exists: %s", bucket, exc)
