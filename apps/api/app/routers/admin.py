from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobStage, PrecedentClause
from app.db.session import get_db
from app.dependencies.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


class PrecedentUpdateInput(BaseModel):
    is_active: bool | None = None
    notes: str | None = None
    source_document: str | None = None
    vendor: str | None = None
    requestor: str | None = None
    sentiment: str | None = None


@router.get("/precedents")
async def list_precedents(
    db: Annotated[AsyncSession, Depends(get_db)],
    query: str | None = Query(None),
    active_only: bool = Query(False),
    sentiment: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(PrecedentClause)
    if active_only:
        stmt = stmt.where(PrecedentClause.is_active == True)
    if sentiment:
        stmt = stmt.where(PrecedentClause.sentiment == sentiment)
    if query:
        stmt = stmt.where(
            PrecedentClause.clause_text.ilike(f"%{query}%")
            | PrecedentClause.source_document.ilike(f"%{query}%")
            | PrecedentClause.vendor.ilike(f"%{query}%")
            | PrecedentClause.notes.ilike(f"%{query}%")
            | PrecedentClause.requestor.ilike(f"%{query}%")
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(PrecedentClause.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": str(p.id),
                "clause_text": p.clause_text,
                "sentiment": p.sentiment,
                "accepted": p.accepted,
                "is_active": p.is_active,
                "source_document": p.source_document,
                "notes": p.notes,
                "requestor": p.requestor,
                "created_at": p.created_at.isoformat(),
            }
            for p in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/precedents/stats")
async def get_precedent_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    total_result = await db.execute(select(func.count()).select_from(PrecedentClause))
    total = total_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).select_from(PrecedentClause).where(PrecedentClause.is_active == True)
    )
    active = active_result.scalar() or 0

    rejected_result = await db.execute(
        select(func.count())
        .select_from(PrecedentClause)
        .where(PrecedentClause.sentiment == "rejected")
    )
    rejected = rejected_result.scalar() or 0

    return {"total": total, "active": active, "rejected": rejected}


def _run_backfill_safe(job_id: str) -> None:
    """Run backfill and log any exception so it appears in server logs."""
    from app.workers.tasks import backfill_precedent_embeddings as run_backfill

    try:
        logger.info("Backfill thread started (job_id=%s)", job_id)
        run_backfill(job_id)
        logger.info("Backfill thread finished (job_id=%s)", job_id)
    except Exception as exc:
        logger.exception("Backfill thread failed (job_id=%s): %s", job_id, exc)
        raise


@router.post("/precedents/backfill/embeddings")
async def backfill_precedent_embeddings(
    db: Annotated[AsyncSession, Depends(get_db)],
    sync: bool = Query(False, description="Run backfill in request (blocking); use for debugging."),
) -> dict:
    """
    Start a background job to compute embeddings for all precedent_clauses
    rows that currently have NULL embedding. Use GET /jobs/{job_id} to poll.
    With ?sync=1, run in the request (blocking) and return the job result.
    """
    from app.workers.tasks import backfill_precedent_embeddings as run_backfill

    job_id = f"backfill-emb-{uuid.uuid4().hex[:12]}"
    logger.info("Backfill embeddings requested (job_id=%s, sync=%s)", job_id, sync)
    # Create initial stage so GET /jobs/{job_id} returns 200 immediately (avoids 404 on first poll)
    now = datetime.now(timezone.utc)
    db.add(
        JobStage(
            job_id=job_id,
            document_id=None,
            stage="backfill_embeddings",
            status="pending",
            progress_detail="Queued",
            started_at=now,
        )
    )
    await db.commit()

    if sync:
        # Run in request so it always executes and errors are visible
        logger.info("Running backfill synchronously (job_id=%s)", job_id)
        await asyncio.to_thread(run_backfill, job_id)
        # Read final job state from DB
        result = await db.execute(
            select(JobStage)
            .where(JobStage.job_id == job_id)
            .order_by(JobStage.started_at.asc())
        )
        stages = result.scalars().all()
        stage = next((s for s in stages if s.stage == "backfill_embeddings"), None)
        status = stage.status if stage else "unknown"
        progress_detail = stage.progress_detail if stage else None
        error = stage.error if stage else None
        return {
            "job_id": job_id,
            "status": status,
            "progress_detail": progress_detail,
            "error": error,
            "message": "Backfill completed (sync mode)." if status == "done" else (error or "Backfill failed."),
        }

    # Async: run in thread
    thread = threading.Thread(target=_run_backfill_safe, args=(job_id,), daemon=True)
    thread.start()
    logger.info("Backfill thread started for job_id=%s", job_id)
    return {"job_id": job_id, "message": "Backfill started. Poll GET /jobs/{job_id} for status."}


@router.patch("/precedents/{precedent_id}")
async def update_precedent(
    precedent_id: str,
    body: PrecedentUpdateInput,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    p = await db.get(PrecedentClause, uuid.UUID(precedent_id))
    if not p:
        raise HTTPException(status_code=404, detail="Precedent not found")

    if body.is_active is not None:
        p.is_active = body.is_active
    if body.notes is not None:
        p.notes = body.notes
    if body.source_document is not None:
        p.source_document = body.source_document
    if body.vendor is not None:
        p.vendor = body.vendor
    if body.requestor is not None:
        p.requestor = body.requestor
    if body.sentiment is not None and body.sentiment in ("accepted", "rejected"):
        p.sentiment = body.sentiment
        p.accepted = body.sentiment == "accepted"

    await db.commit()
    return {"id": str(p.id), "updated": True}


@router.delete("/precedents/{precedent_id}", status_code=204)
async def delete_precedent(
    precedent_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    p = await db.get(PrecedentClause, uuid.UUID(precedent_id))
    if not p:
        raise HTTPException(status_code=404, detail="Precedent not found")
    await db.delete(p)
    await db.commit()


@router.post("/precedents/import/preview")
async def preview_csv_import(
    file: UploadFile = File(...),
) -> dict:
    """
    Parse the CSV and return a preview: row count, sample rows, invalid rows.
    Does NOT import anything.
    """
    content = await file.read()
    rows, invalid, duplicates, sample = _parse_csv(content)
    return {
        "total_rows": len(rows) + len(invalid),
        "valid_rows": len(rows),
        "invalid_rows": len(invalid),
        "duplicate_rows": 0,  # duplication checked at import time
        "sample_rows": sample[:3],
    }


@router.post("/precedents/import")
async def import_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict:
    """
    Kick off a background task to bulk-import precedents from CSV.
    Returns job_id for polling.
    """
    content = await file.read()
    rows, invalid, duplicates, _ = _parse_csv(content)

    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")

    job_id = f"import-{uuid.uuid4().hex[:12]}"

    from app.workers.tasks import import_precedents
    background_tasks.add_task(import_precedents, rows, job_id)

    return {"job_id": job_id, "queued_rows": len(rows), "skipped_rows": len(invalid)}


def _parse_csv(content: bytes) -> tuple[list[dict], list[dict], list[str], list[dict]]:
    """
    Parse CSV bytes.
    Required column: clause_text
    Optional columns: source_document, notes, sentiment (accepted|rejected)

    Returns: (valid_rows, invalid_rows, duplicate_check_list, sample_rows)
    """
    valid = []
    invalid = []
    seen_shas = set()
    sample = []

    text_content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content))

    if not reader.fieldnames or "clause_text" not in reader.fieldnames:
        return [], [{"error": "Missing required column 'clause_text'"}], [], []

    for i, row in enumerate(reader):
        clause_text = (row.get("clause_text") or "").strip()
        if not clause_text:
            invalid.append({"row": i + 2, "error": "Empty clause_text"})
            continue

        # Validate sentiment
        sentiment = (row.get("sentiment") or "accepted").strip().lower()
        if sentiment not in ("accepted", "rejected"):
            sentiment = "accepted"

        sha = hashlib.sha256(clause_text.encode("utf-8")).hexdigest()
        if sha in seen_shas:
            invalid.append({"row": i + 2, "error": "Duplicate clause_text in this CSV"})
            continue
        seen_shas.add(sha)

        parsed = {
            "clause_text": clause_text,
            "source_document": (row.get("source_document") or "").strip() or None,
            "notes": (row.get("notes") or "").strip() or None,
            "sentiment": sentiment,
        }
        valid.append(parsed)
        if len(sample) < 3:
            sample.append(parsed)

    return valid, invalid, list(seen_shas), sample
