from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Clause, Comment, Document, JobStage
from app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()


@router.get("/{document_id}/results")
async def get_document_results(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = Query(None, description="Specific run ID; defaults to latest"),
) -> dict:
    """
    Returns merged clause cards for a document.
    Each card has clause_text, anchor_texts, comments, and explanation.
    """
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    target_run_id = run_id or doc.latest_run_id
    if not target_run_id:
        return {"document_id": document_id, "run_id": None, "clauses": [], "ocr_page_count": 0}

    # Get all clauses for this run
    clauses_result = await db.execute(
        select(Clause)
        .where(
            Clause.document_id == uuid.UUID(document_id),
            Clause.run_id == target_run_id,
        )
        .order_by(
            Clause.anchor_para_idx.asc().nullslast(),
            Clause.created_at.asc(),
        )
    )
    clauses = clauses_result.scalars().all()

    # Get all comments for these clause IDs
    clause_ids = [c.id for c in clauses]
    if clause_ids:
        comments_result = await db.execute(
            select(Comment).where(Comment.clause_id.in_(clause_ids))
        )
        all_comments = comments_result.scalars().all()
        comments_by_clause: dict[uuid.UUID, list] = {}
        for c in all_comments:
            comments_by_clause.setdefault(c.clause_id, []).append(c)
    else:
        comments_by_clause = {}

    # Count OCR pages
    ocr_page_count = sum(1 for c in clauses if c.ocr_used)

    clause_cards = []
    for clause in clauses:
        clause_comments = comments_by_clause.get(clause.id, [])
        card = {
            "clause_id": str(clause.id),
            "run_id": clause.run_id,
            "clause_number": clause.clause_number,
            "confidence": clause.confidence,
            "expansion_method": clause.expansion_method,
            "clause_text": clause.clause_text,
            "anchor_texts": [clause.anchor_text],
            "ocr_used": clause.ocr_used,
            "comments": [
                {
                    "id": str(c.id),
                    "comment_text": c.comment_text,
                    "author": c.author,
                    "source_timestamp": c.source_timestamp.isoformat() if c.source_timestamp else None,
                }
                for c in clause_comments
            ],
            "page_number": clause.page_number,
            "bbox": clause.bbox,
            "explanation": clause.explanation,
        }
        clause_cards.append(card)

    return {
        "document_id": document_id,
        "run_id": target_run_id,
        "ocr_page_count": ocr_page_count,
        "clauses": clause_cards,
    }


@router.get("/{document_id}/runs")
async def get_document_runs(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """Return run history for a document, derived from distinct Clause.run_id values."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get distinct run_ids that actually have clauses stored
    distinct_runs_result = await db.execute(
        select(Clause.run_id, func.count(Clause.id).label("clause_count"))
        .where(Clause.document_id == uuid.UUID(document_id))
        .group_by(Clause.run_id)
    )
    run_rows = distinct_runs_result.all()

    if not run_rows:
        return []

    # Get all job_stages for this document to derive timing
    stage_rows_result = await db.execute(
        select(JobStage)
        .where(JobStage.document_id == uuid.UUID(document_id))
        .order_by(JobStage.started_at.asc())
    )
    stage_rows = stage_rows_result.scalars().all()

    # Group stages by job_id
    jobs: dict[str, list] = {}
    for row in stage_rows:
        jobs.setdefault(row.job_id, []).append(row)

    # Build a map from run_id prefix (8 chars) → job timing
    # job_id pattern: parse-{doc_id}-{run_id[:8]}
    prefix_to_timing: dict[str, dict] = {}
    for job_id, stages in jobs.items():
        prefix = job_id.split("-")[-1]  # last segment = run_id[:8]
        started_at = min((s.started_at for s in stages if s.started_at), default=None)
        finished_at = max((s.finished_at for s in stages if s.finished_at), default=None)
        prefix_to_timing[prefix] = {
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": finished_at,
        }

    runs = []
    for run_id, clause_count in run_rows:
        if not run_id:
            continue
        # Match job timing using the first 8 chars of the run_id
        timing = prefix_to_timing.get(run_id[:8], {})

        comment_count_result = await db.execute(
            select(func.count())
            .select_from(Comment)
            .join(Clause, Comment.clause_id == Clause.id)
            .where(
                Clause.document_id == uuid.UUID(document_id),
                Clause.run_id == run_id,
            )
        )
        comment_count = comment_count_result.scalar() or 0

        started_at = timing.get("started_at")
        finished_at = timing.get("finished_at")
        runs.append({
            "run_id": run_id,
            "job_id": timing.get("job_id", run_id),
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
            "status": "done",
            "clause_count": clause_count,
            "comment_count": comment_count,
        })

    return sorted(runs, key=lambda r: r["started_at"] or "", reverse=True)


@router.delete("/{document_id}/runs/{run_id}", status_code=204)
async def delete_run(
    document_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete all clauses (and their comments) for a specific run."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    clause_ids_result = await db.execute(
        select(Clause.id).where(
            Clause.document_id == uuid.UUID(document_id),
            Clause.run_id == run_id,
        )
    )
    clause_ids = [row[0] for row in clause_ids_result.all()]
    if clause_ids:
        await db.execute(sql_delete(Comment).where(Comment.clause_id.in_(clause_ids)))
        await db.execute(
            sql_delete(Clause).where(
                Clause.document_id == uuid.UUID(document_id),
                Clause.run_id == run_id,
            )
        )

    # Also delete the matching job_stages rows
    # job_id matches: parse-{doc_id}-{run_id[:8]}
    job_id_prefix = f"parse-{document_id}-{run_id[:8]}"
    stage_ids_result = await db.execute(
        select(JobStage.id).where(JobStage.job_id == job_id_prefix)
    )
    stage_ids = [row[0] for row in stage_ids_result.all()]
    if stage_ids:
        await db.execute(sql_delete(JobStage).where(JobStage.id.in_(stage_ids)))

    # If deleted run was the latest, update latest_run_id to next most recent
    if doc.latest_run_id == run_id:
        remaining_result = await db.execute(
            select(Clause.run_id)
            .where(Clause.document_id == uuid.UUID(document_id))
            .distinct()
            .limit(1)
        )
        remaining_run = remaining_result.scalar()
        doc.latest_run_id = remaining_run

    await db.commit()


@router.get("/{document_id}/export.json")
async def export_document(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = Query(None),
) -> JSONResponse:
    """
    Export all extracted results + explanations for a document as JSON download.
    """
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    results = await get_document_results(document_id, db, run_id=run_id)

    export_data = {
        "export_version": "1.0",
        "document_id": document_id,
        "original_filename": doc.original_filename,
        "doc_kind": doc.doc_kind,
        "vendor_case_id": str(doc.vendor_case_id),
        **results,
    }

    filename = doc.original_filename.rsplit(".", 1)[0] + "_clauselens_export.json"
    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{document_id}")
async def update_document(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    doc_kind: str | None = None,
    original_filename: str | None = None,
) -> dict:
    """Update document metadata (doc_kind, original_filename)."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc_kind is not None:
        doc.doc_kind = doc_kind
    if original_filename is not None:
        doc.original_filename = original_filename.strip()
    await db.commit()
    return {"id": str(doc.id), "doc_kind": doc.doc_kind, "original_filename": doc.original_filename}


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a document and all its associated data."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Best-effort delete from storage
    try:
        from app.services import storage as storage_svc
        storage_svc.delete_object(doc.storage_bucket, doc.storage_path)
    except Exception:
        pass

    # Cascade-delete clauses → comments, job stages
    clause_ids_result = await db.execute(
        select(Clause.id).where(Clause.document_id == uuid.UUID(document_id))
    )
    clause_ids = [row[0] for row in clause_ids_result.all()]
    if clause_ids:
        await db.execute(sql_delete(Comment).where(Comment.clause_id.in_(clause_ids)))
    await db.execute(sql_delete(Clause).where(Clause.document_id == uuid.UUID(document_id)))
    await db.execute(sql_delete(JobStage).where(JobStage.document_id == uuid.UUID(document_id)))
    await db.delete(doc)
    await db.commit()


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Re-queue a document for parsing (creates a new run)."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    run_id = str(uuid.uuid4())
    job_id = f"parse-{doc.id}-{run_id[:8]}"

    from app.workers.tasks import parse_document
    background_tasks.add_task(parse_document, str(doc.id), run_id, job_id)

    return {"job_id": job_id, "run_id": run_id}
