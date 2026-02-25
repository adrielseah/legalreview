from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobStage
from app.db.session import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Returns current job status, active stage, and progress detail.
    Reads from job_stages table (checkpoints written by Celery worker).
    """
    result = await db.execute(
        select(JobStage)
        .where(JobStage.job_id == job_id)
        .order_by(JobStage.started_at.asc())
    )
    stages = result.scalars().all()

    if not stages:
        raise HTTPException(status_code=404, detail="Job not found")

    document_id = str(stages[0].document_id) if stages[0].document_id else None
    stage_statuses = {s.stage: s.status for s in stages}
    stage_details = {s.stage: s.progress_detail for s in stages}
    stage_errors = {s.stage: s.error for s in stages}

    # Pipeline stages in order — all must be "done" for the job to be complete
    stage_order = ["downloading", "detecting", "parsing", "expanding", "embedding", "storing"]

    # Determine overall status
    if "duplicate" in stage_statuses.values():
        overall_status = "duplicate"
        dup_stages = [s for s in stages if s.status == "duplicate"]
        error = None
        active_stage = dup_stages[-1].stage if dup_stages else None
        progress_detail = dup_stages[-1].progress_detail if dup_stages else None
    elif "failed" in stage_statuses.values():
        overall_status = "failed"
        failed_stages = [s for s in stages if s.status == "failed"]
        error = failed_stages[-1].error if failed_stages else None
        active_stage = failed_stages[-1].stage if failed_stages else None
        progress_detail = None
    elif all(stage_statuses.get(s) == "done" for s in stage_order):
        overall_status = "done"
        error = None
        active_stage = "storing"
        progress_detail = "complete"
    elif "running" in stage_statuses.values():
        overall_status = "running"
        error = None
        running = next(s for s in stages if s.status == "running")
        active_stage = running.stage
        progress_detail = running.progress_detail
    else:
        overall_status = "pending"
        error = None
        active_stage = None
        progress_detail = None

    # Calculate 0-100 progress
    done_count = sum(1 for s in stage_order if stage_statuses.get(s) == "done")
    progress = int((done_count / len(stage_order)) * 100)

    return {
        "job_id": job_id,
        "document_id": document_id,
        "status": overall_status,
        "stage": active_stage,
        "progress": progress,
        "progress_detail": progress_detail,
        "error": error,
        "stages": [
            {
                "stage": s.stage,
                "status": s.status,
                "progress_detail": s.progress_detail,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in stages
        ],
    }
