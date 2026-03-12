from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Clause, Comment, Document, PrecedentClause, VendorCase
from app.db.session import get_db

router = APIRouter(prefix="/clauses", tags=["clauses"])
settings = get_settings()  # used by _add_precedent


class AcceptInput(BaseModel):
    source_document: str | None = None
    vendor: str | None = None
    notes: str | None = None


class RejectInput(BaseModel):
    source_document: str | None = None
    vendor: str | None = None
    notes: str | None = None


class SimilarResultItem(BaseModel):
    id: str
    clause_text: str
    similarity: float
    source: str
    sentiment: str | None
    source_document: str | None
    vendor: str | None
    notes: str | None
    requestor: str | None


class SimilarResponse(BaseModel):
    results: list[SimilarResultItem]
    reason: str | None = None


@router.get("/{clause_id}/similar", response_model=SimilarResponse)
async def get_similar(
    clause_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return top similar results from precedent_clauses (active only),
    ranked by cosine similarity, top 5 returned.
    When empty, reason explains why (e.g. clause or precedents have no embedding).
    """
    clause = await db.get(Clause, uuid.UUID(clause_id))
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")

    if clause.embedding is None:
        return {"results": [], "reason": "clause_has_no_embedding"}

    emb_str = "[" + ",".join(str(v) for v in clause.embedding) + "]"

    precedent_sql = text(
        f"""
        SELECT id, clause_text, source_document, vendor, notes, sentiment, requestor,
               1 - (embedding <=> '{emb_str}'::vector) AS similarity
        FROM public.precedent_clauses
        WHERE is_active = true AND embedding IS NOT NULL
          AND 1 - (embedding <=> '{emb_str}'::vector) >= 0.30
        ORDER BY embedding <=> '{emb_str}'::vector
        LIMIT 5
        """
    )
    precedent_rows = (await db.execute(precedent_sql)).fetchall()

    results = [
        {
            "id": str(row.id),
            "clause_text": row.clause_text,
            "similarity": float(row.similarity),
            "source": "precedent",
            "sentiment": row.sentiment,
            "source_document": row.source_document,
            "vendor": row.vendor,
            "notes": row.notes,
            "requestor": row.requestor,
        }
        for row in precedent_rows
    ]

    reason = None
    if not results:
        count_row = (await db.execute(
            text("SELECT COUNT(*) AS n FROM public.precedent_clauses WHERE is_active = true AND embedding IS NOT NULL")
        )).fetchone()
        precedent_with_emb = (count_row and count_row[0]) or 0
        if precedent_with_emb == 0:
            reason = "no_precedents_with_embedding"
    return {"results": results, "reason": reason}


@router.post("/{clause_id}/explain")
async def explain_clause(
    clause_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    force: bool = False,
) -> dict:
    """
    Generate plain-English explanation for a clause + its comments.
    Stores result in clause.explanation. Returns cached if already exists (unless force=True).
    """
    clause = await db.get(Clause, uuid.UUID(clause_id))
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")

    if clause.explanation and not force:
        return clause.explanation

    # Get associated comments
    comments_result = await db.execute(
        select(Comment).where(Comment.clause_id == clause.id)
    )
    comment_texts = [c.comment_text for c in comments_result.scalars().all()]

    from app.services.llm import explain_clause as llm_explain

    try:
        explanation = llm_explain(clause.clause_text, comment_texts, anchor_text=clause.anchor_text or "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM explanation failed: {exc}")

    clause.explanation = explanation
    await db.commit()
    return explanation


@router.get("/{clause_id}/precedent-status")
async def precedent_status(
    clause_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Check if this clause already exists in the precedent table."""
    existing = (
        await db.execute(
            select(PrecedentClause).where(
                PrecedentClause.source_clause_id == uuid.UUID(clause_id),
                PrecedentClause.is_active == True,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return {"sentiment": existing.sentiment}
    return {"sentiment": None}


@router.post("/batch-precedent-status")
async def batch_precedent_status(
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return precedent sentiment for a list of clause IDs."""
    clause_ids = body.get("clause_ids", [])
    if not clause_ids:
        return {"statuses": {}}

    uuids = [uuid.UUID(cid) for cid in clause_ids]
    rows = (
        await db.execute(
            select(PrecedentClause.source_clause_id, PrecedentClause.sentiment).where(
                PrecedentClause.source_clause_id.in_(uuids),
                PrecedentClause.is_active == True,
            )
        )
    ).fetchall()

    statuses = {str(row.source_clause_id): row.sentiment for row in rows}
    return {"statuses": statuses}


@router.post("/{clause_id}/accept", status_code=201)
async def accept_clause(
    clause_id: str,
    body: AcceptInput,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Accept a clause as a positive precedent."""
    return await _add_precedent(clause_id, body, "accepted", db)


@router.post("/{clause_id}/reject", status_code=201)
async def reject_clause(
    clause_id: str,
    body: RejectInput,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mark a clause as a negative precedent (rejected/problematic)."""
    return await _add_precedent(clause_id, body, "rejected", db)


async def _add_precedent(
    clause_id: str,
    body: AcceptInput | RejectInput,
    sentiment: str,
    db: AsyncSession,
) -> dict:
    import hashlib

    clause = await db.get(Clause, uuid.UUID(clause_id))
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")

    # Resolve vendor name from clause → document → vendor_case
    vendor_name = body.vendor
    if not vendor_name:
        doc = await db.get(Document, clause.document_id)
        if doc:
            vc = await db.get(VendorCase, doc.vendor_case_id)
            if vc:
                vendor_name = vc.vendor_name

    sha = hashlib.sha256(clause.clause_text.encode("utf-8")).hexdigest()

    # Upsert: if same sha256 exists, update sentiment; otherwise insert
    existing = (
        await db.execute(
            select(PrecedentClause).where(PrecedentClause.text_sha256 == sha)
        )
    ).scalar_one_or_none()

    if existing:
        existing.sentiment = sentiment
        existing.accepted = sentiment == "accepted"
        existing.is_active = True
        existing.source_clause_id = uuid.UUID(clause_id)
        if body.notes:
            existing.notes = body.notes
        if body.source_document:
            existing.source_document = body.source_document
        if vendor_name:
            existing.vendor = vendor_name
        await db.commit()
        return {"id": str(existing.id), "created": False, "sentiment": sentiment}

    # Compute embedding for the new precedent
    embedding = None
    if clause.embedding is not None:
        embedding = list(clause.embedding)
    else:
        from app.services.embeddings import get_embeddings_batch_sync
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        sync_url = settings.database_url.replace("+asyncpg", "")
        sync_engine = create_engine(sync_url, pool_size=1, max_overflow=0)
        SyncSession = sessionmaker(sync_engine)
        with SyncSession() as sync_db:
            embeddings = get_embeddings_batch_sync([clause.clause_text], sync_db)
            embedding = embeddings[0] if embeddings else None

    precedent = PrecedentClause(
        clause_text=clause.clause_text,
        text_sha256=sha,
        sentiment=sentiment,
        accepted=(sentiment == "accepted"),
        is_active=True,
        source_document=body.source_document,
        vendor=vendor_name,
        notes=body.notes,
        source_clause_id=uuid.UUID(clause_id),
        embedding=embedding,
    )
    db.add(precedent)
    await db.commit()
    await db.refresh(precedent)
    return {"id": str(precedent.id), "created": True, "sentiment": sentiment}
