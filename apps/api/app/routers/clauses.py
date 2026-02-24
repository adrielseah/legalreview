from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Clause, Comment, Document, PrecedentClause
from app.db.session import get_db

router = APIRouter(prefix="/clauses", tags=["clauses"])
settings = get_settings()


class AcceptInput(BaseModel):
    source_document: str | None = None
    notes: str | None = None


class RejectInput(BaseModel):
    source_document: str | None = None
    notes: str | None = None


@router.get("/{clause_id}/similar")
async def get_similar(
    clause_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """
    Return top similar results from:
    1. precedent_clauses (active only)  → tagged source="precedent"
    2. clauses in same vendor case      → tagged source="same_vendor"

    Results merged, re-ranked by cosine similarity, top 5 returned.
    """
    clause = await db.get(Clause, uuid.UUID(clause_id))
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")

    if clause.embedding is None:
        return []

    emb_str = "[" + ",".join(str(v) for v in clause.embedding) + "]"
    threshold = settings.similarity_threshold

    # Query precedent_clauses
    precedent_sql = text(
        f"""
        SELECT id, clause_text, source_document, notes, sentiment,
               1 - (embedding <=> '{emb_str}'::vector) AS similarity
        FROM precedent_clauses
        WHERE is_active = true AND embedding IS NOT NULL
        ORDER BY embedding <=> '{emb_str}'::vector
        LIMIT 3
        """
    )
    precedent_rows = (await db.execute(precedent_sql)).fetchall()

    # Query same vendor's clauses
    doc = await db.get(Document, clause.document_id)
    same_vendor_results = []
    if doc:
        same_vendor_sql = text(
            f"""
            SELECT c.id, c.clause_text, c.clause_number,
                   1 - (c.embedding <=> '{emb_str}'::vector) AS similarity
            FROM clauses c
            JOIN documents d ON c.document_id = d.id
            WHERE d.vendor_case_id = '{doc.vendor_case_id}'
              AND c.id != '{clause_id}'
              AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> '{emb_str}'::vector
            LIMIT 3
            """
        )
        same_vendor_rows = (await db.execute(same_vendor_sql)).fetchall()
        same_vendor_results = [
            {
                "id": str(row.id),
                "clause_text": row.clause_text,
                "similarity": float(row.similarity),
                "above_threshold": float(row.similarity) >= threshold,
                "source": "same_vendor",
                "sentiment": None,
                "source_document": None,
                "notes": None,
            }
            for row in same_vendor_rows
        ]

    precedent_results = [
        {
            "id": str(row.id),
            "clause_text": row.clause_text,
            "similarity": float(row.similarity),
            "above_threshold": float(row.similarity) >= threshold,
            "source": "precedent",
            "sentiment": row.sentiment,
            "source_document": row.source_document,
            "notes": row.notes,
        }
        for row in precedent_rows
    ]

    # Merge and re-rank
    combined = precedent_results + same_vendor_results
    combined.sort(key=lambda x: x["similarity"], reverse=True)
    return combined[:5]


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
        if body.notes:
            existing.notes = body.notes
        if body.source_document:
            existing.source_document = body.source_document
        await db.commit()
        return {"id": str(existing.id), "created": False}

    # Compute embedding for the new precedent
    embedding = None
    if clause.embedding is not None:
        embedding = list(clause.embedding)
    else:
        from app.services.embeddings import get_embeddings_batch_sync
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        sync_url = settings.database_url.replace("+asyncpg", "")
        sync_engine = create_engine(sync_url)
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
        notes=body.notes,
        embedding=embedding,
    )
    db.add(precedent)
    await db.commit()
    await db.refresh(precedent)
    return {"id": str(precedent.id), "created": True}
