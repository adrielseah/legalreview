from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/search", tags=["search"])
settings = get_settings()


@router.get("")
async def semantic_search(
    q: Annotated[str, Query(min_length=1, description="Search query")],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[dict]:
    """
    Semantic search across all clauses using pgvector cosine similarity.
    Embeds the query and finds the most similar clause cards.
    """
    if settings.disable_embeddings:
        return []

    from app.services.embeddings import get_embeddings_batch_sync
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Compute embedding for query (sync)
    sync_url = settings.database_url.replace("+asyncpg", "")
    sync_engine = create_engine(sync_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    SyncSession = sessionmaker(sync_engine)

    with SyncSession() as sync_db:
        embeddings = get_embeddings_batch_sync([q], sync_db)

    if not embeddings or embeddings[0] is None:
        return []

    emb_str = "[" + ",".join(str(v) for v in embeddings[0]) + "]"

    sql = text(
        f"""
        SELECT c.id AS clause_id,
               c.clause_text,
               c.clause_number,
               1 - (c.embedding <=> '{emb_str}'::vector) AS similarity,
               d.id AS document_id,
               d.original_filename AS document_filename,
               v.id AS vendor_case_id,
               v.vendor_name
        FROM clauses c
        JOIN documents d ON c.document_id = d.id
        JOIN vendor_cases v ON d.vendor_case_id = v.id
        WHERE c.embedding IS NOT NULL
          AND v.is_deleted = false
        ORDER BY c.embedding <=> '{emb_str}'::vector
        LIMIT {limit}
        """
    )

    rows = (await db.execute(sql)).fetchall()
    return [
        {
            "clause_id": str(row.clause_id),
            "clause_text": row.clause_text,
            "clause_number": row.clause_number,
            "similarity": float(row.similarity),
            "document_id": str(row.document_id),
            "document_filename": row.document_filename,
            "vendor_case_id": str(row.vendor_case_id),
            "vendor_name": row.vendor_name,
        }
        for row in rows
    ]
