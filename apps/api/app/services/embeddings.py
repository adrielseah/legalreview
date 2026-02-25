"""
Embedding service.
Uses Gemini text-embedding-004 (768 dims, free tier) via the native SDK,
or OpenAI text-embedding-3-small (1536 dims) as fallback.

Set GEMINI_API_KEY in .env to use Gemini.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import EmbeddingCache

logger = logging.getLogger(__name__)
settings = get_settings()

BATCH_SIZE = 100


def _sha256(text_: str) -> str:
    return hashlib.sha256(text_.encode("utf-8")).hexdigest()


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Call the embedding API and return a list of vectors.
    Uses Gemini native SDK when GEMINI_API_KEY is set, otherwise OpenAI.
    """
    if settings.gemini_api_key:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        result = genai.embed_content(
            model=f"models/{settings.embedding_model}",
            content=texts,
            task_type="SEMANTIC_SIMILARITY",
        )
        # embed_content returns a dict with 'embedding' (single) or list when content is a list
        emb = result["embedding"]
        if isinstance(emb[0], float):
            # Single text was passed — wrap in list
            return [emb]
        return emb
    else:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(model=settings.embedding_model, input=texts)
        return [obj.embedding for obj in response.data]


def get_embedding_sync(text_: str, db: Session) -> list[float] | None:
    """Get embedding for a single text, using cache. Returns None if DISABLE_EMBEDDINGS."""
    if settings.disable_embeddings:
        return None

    sha = _sha256(text_)
    cached = db.execute(
        select(EmbeddingCache).where(EmbeddingCache.text_sha256 == sha)
    ).scalar_one_or_none()
    if cached is not None:
        return list(cached.embedding)

    vectors = _embed_texts([text_])
    vector = vectors[0]

    db.add(EmbeddingCache(text_sha256=sha, embedding=vector))
    db.commit()
    return vector


def get_embeddings_batch_sync(
    texts: list[str], db: Session, progress_callback: Any = None
) -> list[list[float] | None]:
    """Get embeddings for a batch of texts, using cache and batching API calls."""
    if settings.disable_embeddings:
        return [None] * len(texts)

    shas = [_sha256(t) for t in texts]
    results: list[list[float] | None] = [None] * len(texts)

    cached_rows = db.execute(
        select(EmbeddingCache).where(EmbeddingCache.text_sha256.in_(shas))
    ).scalars().all()
    cache_map = {row.text_sha256: list(row.embedding) for row in cached_rows}

    uncached_indices = [i for i, sha in enumerate(shas) if sha not in cache_map]
    uncached_texts = [texts[i] for i in uncached_indices]

    for i, sha in enumerate(shas):
        if sha in cache_map:
            results[i] = cache_map[sha]

    if not uncached_texts:
        return results

    new_cache_entries = []
    processed = 0

    for batch_start in range(0, len(uncached_texts), BATCH_SIZE):
        batch_texts = uncached_texts[batch_start : batch_start + BATCH_SIZE]
        batch_indices = uncached_indices[batch_start : batch_start + BATCH_SIZE]

        vectors = _embed_texts(batch_texts)

        for j, vector in enumerate(vectors):
            orig_idx = batch_indices[j]
            results[orig_idx] = vector
            new_cache_entries.append(
                EmbeddingCache(text_sha256=shas[orig_idx], embedding=vector)
            )

        processed += len(batch_texts)
        if progress_callback:
            progress_callback(processed, len(uncached_texts))

    for entry in new_cache_entries:
        try:
            db.merge(entry)
        except Exception:
            pass
    db.commit()

    return results


def cosine_similarity_query(
    db: Session,
    query_embedding: list[float],
    table: str,
    id_col: str = "id",
    extra_where: str = "",
    limit: int = 5,
) -> list[dict]:
    """
    Run a pgvector cosine similarity query against a table.
    Returns list of {id, similarity} dicts.
    """
    from sqlalchemy import text
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    where_clause = f"WHERE embedding IS NOT NULL {extra_where}"
    sql = text(
        f"""
        SELECT {id_col} as id,
               1 - (embedding <=> '{embedding_str}'::vector) AS similarity
        FROM {table}
        {where_clause}
        ORDER BY embedding <=> '{embedding_str}'::vector
        LIMIT {limit}
        """
    )
    rows = db.execute(sql).fetchall()
    return [{"id": str(row.id), "similarity": float(row.similarity)} for row in rows]
