from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, PrecedentClause, VendorCase
from app.db.session import get_db

router = APIRouter(prefix="/vendors", tags=["vendors"])


class CreateVendorInput(BaseModel):
    vendor_name: str
    procurement_ref: str | None = None


class VendorOut(BaseModel):
    id: str
    vendor_name: str
    procurement_ref: str | None
    created_at: str
    is_deleted: bool

    model_config = {"from_attributes": True}


class VendorDetailOut(VendorOut):
    document_count: int


@router.post("", status_code=201)
async def create_vendor(
    body: CreateVendorInput,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    vendor = VendorCase(
        vendor_name=body.vendor_name.strip(),
        procurement_ref=body.procurement_ref,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return {"vendor_case_id": str(vendor.id)}


@router.get("")
async def list_vendors(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(None, description="Search vendor_name"),
    include_deleted: bool = Query(False),
) -> list[dict]:
    stmt = select(VendorCase).where(VendorCase.is_deleted == False)
    if include_deleted:
        stmt = select(VendorCase)
    if q:
        stmt = stmt.where(VendorCase.vendor_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(VendorCase.created_at.desc())
    result = await db.execute(stmt)
    vendors = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "vendor_name": v.vendor_name,
            "procurement_ref": v.procurement_ref,
            "created_at": v.created_at.isoformat(),
            "is_deleted": v.is_deleted,
        }
        for v in vendors
    ]


@router.get("/suggest-names")
async def suggest_vendor_names(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query("", description="Partial vendor name to match"),
) -> list[str]:
    """Return distinct vendor names from precedent_clauses matching the query."""
    stmt = (
        select(PrecedentClause.vendor)
        .where(PrecedentClause.vendor.isnot(None))
        .distinct()
    )
    if q.strip():
        stmt = stmt.where(PrecedentClause.vendor.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(PrecedentClause.vendor).limit(10)
    result = await db.execute(stmt)
    return [row[0] for row in result.fetchall()]


@router.get("/{vendor_case_id}")
async def get_vendor(
    vendor_case_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    vendor = await db.get(VendorCase, uuid.UUID(vendor_case_id))
    if not vendor or vendor.is_deleted:
        raise HTTPException(status_code=404, detail="Vendor case not found")

    # Load documents with latest job status
    from app.db.models import JobStage
    from sqlalchemy import text as sqlt

    docs_result = await db.execute(
        select(Document)
        .where(Document.vendor_case_id == vendor.id)
        .order_by(Document.uploaded_at.desc())
    )
    docs = docs_result.scalars().all()

    doc_list = []
    for doc in docs:
        # Get latest job stage info — always check regardless of latest_run_id
        job_info = {"status": None, "stage": None, "progress_detail": None}
        stage_rows = await db.execute(
            select(JobStage)
            .where(JobStage.document_id == doc.id)
            .order_by(JobStage.started_at.desc().nullslast())
        )
        all_stages = stage_rows.scalars().all()

        if all_stages:
            # Group by job_id and find the most recent job
            jobs: dict[str, list] = {}
            for s in all_stages:
                jobs.setdefault(s.job_id, []).append(s)

            # Most recent job = the one with the latest started_at across any of its stages
            def _job_latest(stages_list: list) -> Any:
                return max(
                    (s.started_at or s.finished_at or _epoch() for s in stages_list),
                    default=_epoch(),
                )

            latest_job_id = max(jobs, key=lambda jid: _job_latest(jobs[jid]))
            stages = jobs[latest_job_id]

            statuses = [s.status for s in stages]
            if "duplicate" in statuses:
                job_info["status"] = "duplicate"
            elif "running" in statuses:
                job_info["status"] = "running"
            elif "failed" in statuses:
                job_info["status"] = "failed"
            elif all(s == "done" for s in statuses):
                job_info["status"] = "done"
            else:
                job_info["status"] = "pending"

            running_stage = next((s for s in stages if s.status == "running"), None)
            if running_stage:
                job_info["stage"] = running_stage.stage
                job_info["progress_detail"] = running_stage.progress_detail
            else:
                last_stage = max(stages, key=lambda s: s.started_at or s.finished_at or _epoch())
                job_info["stage"] = last_stage.stage
                job_info["progress_detail"] = last_stage.progress_detail

        # Count runs
        run_count_result = await db.execute(
            select(func.count())
            .select_from(JobStage)
            .where(JobStage.document_id == doc.id, JobStage.stage == "storing", JobStage.status == "done")
        )
        run_count = run_count_result.scalar() or 0

        doc_list.append({
            "id": str(doc.id),
            "vendor_case_id": str(doc.vendor_case_id),
            "original_filename": doc.original_filename,
            "doc_kind": doc.doc_kind,
            "file_type": doc.file_type,
            "sha256": doc.sha256,
            "uploaded_at": doc.uploaded_at.isoformat(),
            "latest_run_id": doc.latest_run_id,
            "job_status": job_info["status"],
            "job_stage": job_info["stage"],
            "job_progress_detail": job_info["progress_detail"],
            "run_count": run_count,
        })

    return {
        "id": str(vendor.id),
        "vendor_name": vendor.vendor_name,
        "procurement_ref": vendor.procurement_ref,
        "created_at": vendor.created_at.isoformat(),
        "is_deleted": vendor.is_deleted,
        "documents": doc_list,
    }


@router.delete("/{vendor_case_id}", status_code=204)
async def delete_vendor(
    vendor_case_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Admin-only soft delete."""
    vendor = await db.get(VendorCase, uuid.UUID(vendor_case_id))
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor case not found")
    vendor.is_deleted = True
    await db.commit()


def _epoch():
    from datetime import datetime, timezone
    return datetime.fromtimestamp(0, tz=timezone.utc)
