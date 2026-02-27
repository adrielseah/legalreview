"""
Embedding service.
Uses only Isaacus Kanon 2 Embedder for clause/precedent embeddings. ISAACUS_API_KEY is required.
Uses the official isaacus Python SDK: https://docs.isaacus.com/quickstart
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


def _normalize_embedding_result(emb: Any, num_expected: int) -> list[list[float]]:
    """Turn API response into list of vectors. Handles single vector or list of vectors."""
    if emb is None:
        return []
    if isinstance(emb, list) and len(emb) > 0:
        if isinstance(emb[0], (int, float)):
            return [emb]
        if isinstance(emb[0], list):
            return [list(v) for v in emb]
    return []


def _embed_texts_isaacus(texts: list[str]) -> list[list[float]]:
    """Call Isaacus via official SDK (kanon-2-embedder). Returns list of vectors."""
    from isaacus import Isaacus

    api_key = get_settings().isaacus_api_key
    if not api_key or not api_key.strip():
        raise ValueError(
            "Embeddings require ISAACUS_API_KEY. Set it in apps/api/.env to use Isaacus Kanon 2 Embedder. "
            "See https://docs.isaacus.com/quickstart"
        )
    client = Isaacus(api_key=api_key.strip())
    model = get_settings().isaacus_embedding_model
    dimensions = get_settings().isaacus_embedding_dim
    # Single text or list of texts; task retrieval/document for clause storage
    response = client.embeddings.create(
        model=model,
        texts=texts[0] if len(texts) == 1 else texts,
        task="retrieval/document",
        dimensions=dimensions,
    )
    # response.embeddings is list of objects with .embedding
    out = []
    for i, item in enumerate(response.embeddings):
        emb = getattr(item, "embedding", None)
        if emb is not None:
            out.append(list(emb))
    dim = get_settings().isaacus_embedding_dim
    while len(out) < len(texts):
        out.append(out[-1][:dim] if out else [0.0] * dim)
    return out[: len(texts)]


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Call the embedding API and return a list of vectors.
    Uses only Isaacus Kanon 2 Embedder (ISAACUS_API_KEY required).
    """
    if not texts:
        return []
    if not (get_settings().isaacus_api_key or "").strip():
        raise ValueError(
            "Embeddings require ISAACUS_API_KEY. Set it in apps/api/.env to use Isaacus Kanon 2 Embedder. "
            "See https://docs.isaacus.com/quickstart"
        )
    try:
        return _embed_texts_isaacus(texts)
    except Exception as e:
        logger.exception("Isaacus embedding failed: %s", e)
        raise


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
    # Normalize to schema dimension so DB (vector(1536)) accepts even if API returns 768
    schema_dim = get_settings().embedding_schema_dim
    vector = list(vectors[0])[:schema_dim]
    if len(vector) < schema_dim:
        vector.extend([0.0] * (schema_dim - len(vector)))

    db.add(EmbeddingCache(text_sha256=sha, embedding=vector))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return vector


def get_embeddings_batch_sync(
    texts: list[str], db: Session, progress_callback: Any = None
) -> list[list[float] | None]:
    """Get embeddings for a batch of texts, using cache and batching API calls."""
    if settings.disable_embeddings:
        logger.warning(
            "Embeddings disabled (DISABLE_EMBEDDINGS=true); returning None for %d texts",
            len(texts),
        )
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

        # Normalize to schema dimension so DB (vector(1536)) accepts even if API returns 768
        schema_dim = get_settings().embedding_schema_dim
        for j, vector in enumerate(vectors):
            orig_idx = batch_indices[j]
            vec = (list(vector)[:schema_dim] if len(vector) > schema_dim else list(vector))
            if len(vec) < schema_dim:
                vec.extend([0.0] * (schema_dim - len(vec)))
            results[orig_idx] = vec
            new_cache_entries.append(
                EmbeddingCache(text_sha256=shas[orig_idx], embedding=vec)
            )

        processed += len(batch_texts)
        if progress_callback:
            progress_callback(processed, len(uncached_texts))

    for entry in new_cache_entries:
        try:
            db.merge(entry)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

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
