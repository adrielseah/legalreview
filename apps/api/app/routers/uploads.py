from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Document, VendorCase
from app.db.session import get_db
from app.services import storage as storage_svc

router = APIRouter(tags=["uploads"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


class UploadInitInput(BaseModel):
    filename: str
    doc_kind: str | None = None


class UploadInitResult(BaseModel):
    document_id: str
    upload_url: str
    storage_bucket: str
    storage_path: str


class UploadCompleteInput(BaseModel):
    document_id: str


class UploadCompleteResult(BaseModel):
    job_id: str
    run_id: str


@router.post("/vendors/{vendor_case_id}/uploads/init", response_model=UploadInitResult)
async def upload_init(
    vendor_case_id: str,
    body: UploadInitInput,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UploadInitResult:
    """
    Create a document record and return a presigned PUT URL for direct browser upload.
    File is uploaded to: vendor/<vendor_case_id>/incoming/<document_id>/<filename>
    """
    # Validate vendor exists
    vendor = await db.get(VendorCase, uuid.UUID(vendor_case_id))
    if not vendor or vendor.is_deleted:
        raise HTTPException(status_code=404, detail="Vendor case not found")

    # Validate file extension
    ext = "." + body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Only .pdf and .docx are allowed.")

    file_type = "pdf" if ext == ".pdf" else "docx"
    document_id = uuid.uuid4()

    # Incoming path (before sha256 is known)
    storage_path = f"vendor/{vendor_case_id}/incoming/{document_id}/{body.filename}"

    # Create document record
    doc = Document(
        id=document_id,
        vendor_case_id=uuid.UUID(vendor_case_id),
        original_filename=body.filename,
        doc_kind=body.doc_kind,
        file_type=file_type,
        storage_bucket=settings.bucket_raw,
        storage_path=storage_path,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(doc)
    await db.commit()

    # Generate presigned PUT URL
    upload_url = storage_svc.generate_upload_url(settings.bucket_raw, storage_path)

    return UploadInitResult(
        document_id=str(document_id),
        upload_url=upload_url,
        storage_bucket=settings.bucket_raw,
        storage_path=storage_path,
    )


@router.post("/uploads/complete", response_model=UploadCompleteResult)
async def upload_complete(
    body: UploadCompleteInput,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UploadCompleteResult:
    """
    Called after the browser finishes uploading to storage.
    - Downloads file to compute sha256
    - Moves to sha256-based path
    - Enqueues Celery parse_document task
    """
    doc = await db.get(Document, uuid.UUID(body.document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Download from incoming path
    file_bytes = storage_svc.download_bytes(doc.storage_bucket, doc.storage_path)

    # Compute sha256
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    doc.sha256 = sha256

    # Move to sha256-based path
    vendor_case_id = str(doc.vendor_case_id)
    new_path = f"vendor/{vendor_case_id}/raw/sha256/{sha256}/{doc.original_filename}"

    try:
        storage_svc.move_object(settings.bucket_raw, doc.storage_path, new_path)
        doc.storage_path = new_path
    except Exception as exc:
        # If move fails (e.g. object already exists at destination), just update path
        doc.storage_path = new_path

    await db.commit()

    # Generate job and run IDs
    run_id = str(uuid.uuid4())
    job_id = f"parse-{doc.id}-{run_id[:8]}"

    # Run parsing as a background task (no Celery/Redis required)
    from app.workers.tasks import parse_document
    background_tasks.add_task(parse_document, str(doc.id), run_id, job_id)

    return UploadCompleteResult(job_id=job_id, run_id=run_id)
