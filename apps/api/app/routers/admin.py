from __future__ import annotations

import csv
import hashlib
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PrecedentClause
from app.db.session import get_db
from app.dependencies.auth import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


class PrecedentUpdateInput(BaseModel):
    is_active: bool | None = None
    notes: str | None = None
    source_document: str | None = None
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
            | PrecedentClause.notes.ilike(f"%{query}%")
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
