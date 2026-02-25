"""
Document processing pipeline — runs as FastAPI background tasks.
No Celery or Redis required.

parse_document stages:
  1. downloading  - fetch from storage
  2. detecting    - LLM doc_kind auto-detect
  3. parsing      - DOCX or PDF parser
  4. expanding    - merge/group comments to clause cards
  5. embedding    - batch embed clause_texts
  6. storing      - upsert to DB + write extractions.json

Progress is written to the job_stages table after each stage,
and polled by the frontend via GET /jobs/{job_id}.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_sync_engine = None
_SyncSession = None


def _get_sync_session() -> Session:
    global _sync_engine, _SyncSession
    if _sync_engine is None:
        # Prefer SYNC_DATABASE_URL (plain psycopg2, no asyncpg-specific params).
        # Fall back to stripping +asyncpg and any query params from DATABASE_URL.
        sync_url = settings.sync_database_url or settings.database_url.replace(
            "+asyncpg", ""
        ).split("?")[0]
        _sync_engine = create_engine(sync_url, pool_pre_ping=True, pool_size=3)
        _SyncSession = sessionmaker(_sync_engine, expire_on_commit=False)
    return _SyncSession()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _upsert_stage(
    db: Session,
    job_id: str,
    document_id: str,
    stage: str,
    status: str,
    progress_detail: str | None = None,
    error: str | None = None,
    finish: bool = False,
) -> None:
    from app.db.models import JobStage

    existing = db.execute(
        select(JobStage).where(
            JobStage.job_id == job_id, JobStage.stage == stage
        )
    ).scalar_one_or_none()

    now = _utcnow()
    if existing:
        existing.status = status
        existing.progress_detail = progress_detail
        existing.error = error
        if status == "running" and existing.started_at is None:
            existing.started_at = now
        if finish:
            existing.finished_at = now
    else:
        doc_uuid = None
        try:
            doc_uuid = uuid.UUID(document_id) if document_id else None
        except Exception:
            pass
        row = JobStage(
            job_id=job_id,
            document_id=doc_uuid,
            stage=stage,
            status=status,
            progress_detail=progress_detail,
            error=error,
            started_at=now if status == "running" else None,
            finished_at=now if finish else None,
        )
        db.add(row)
    db.commit()


def parse_document(document_id: str, run_id: str, job_id: str) -> None:
    """
    Full document processing pipeline.
    Runs in a FastAPI background task (separate thread).
    Progress is written to job_stages table.
    """
    db = _get_sync_session()
    try:
        _run_pipeline(db, document_id, run_id, job_id)
    except Exception as exc:
        logger.error("parse_document failed (job=%s): %s", job_id, exc, exc_info=True)
        # Roll back any dirty transaction before writing the error stage
        try:
            db.rollback()
        except Exception:
            pass
        try:
            _upsert_stage(db, job_id, document_id, "failed", "failed", error=str(exc), finish=True)
        except Exception as write_exc:
            logger.error("Could not persist failure stage for job %s: %s", job_id, write_exc)
    finally:
        db.close()


def _run_pipeline(db: Session, document_id: str, run_id: str, job_id: str) -> None:
    from app.db.models import Document, Clause, Comment
    from app.services import storage as storage_svc
    from app.services.embeddings import get_embeddings_batch_sync
    from app.services.llm import detect_doc_kind
    from app.parsers.docx_parser import parse_docx, get_first_page_text_docx
    from app.parsers.pdf_parser import parse_pdf, get_first_page_text_pdf

    # ── Stage 1: downloading ──────────────────────────────────────────────────
    _upsert_stage(db, job_id, document_id, "downloading", "running")
    doc = db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise ValueError(f"Document {document_id} not found")
    file_bytes = storage_svc.download_bytes(doc.storage_bucket, doc.storage_path)

    # Compute sha256 and move to permanent path if not already done
    import hashlib as _hashlib
    sha256 = _hashlib.sha256(file_bytes).hexdigest()
    if not doc.sha256:
        doc.sha256 = sha256
        vendor_case_id = str(doc.vendor_case_id)
        safe_name = doc.storage_path.rsplit("/", 1)[-1]
        new_path = f"vendor/{vendor_case_id}/raw/sha256/{sha256}/{safe_name}"
        if doc.storage_path != new_path:
            try:
                storage_svc.move_object(doc.storage_bucket, doc.storage_path, new_path)
            except Exception:
                pass
            doc.storage_path = new_path
        db.commit()
        file_bytes = storage_svc.download_bytes(doc.storage_bucket, doc.storage_path)

    _upsert_stage(db, job_id, document_id, "downloading", "done", finish=True)

    # ── Stage 2: detecting ────────────────────────────────────────────────────
    _upsert_stage(db, job_id, document_id, "detecting", "running")
    if not doc.doc_kind:
        try:
            first_text = (
                get_first_page_text_docx(file_bytes)
                if doc.file_type == "docx"
                else get_first_page_text_pdf(file_bytes)
            )
            detected = detect_doc_kind(first_text)
            if detected:
                doc.doc_kind = detected
                db.commit()
        except Exception as exc:
            logger.warning("doc_kind detection failed: %s", exc)
    _upsert_stage(
        db, job_id, document_id, "detecting", "done",
        progress_detail=f"doc_kind={doc.doc_kind or 'Unknown'}", finish=True
    )

    # ── Stage 3: parsing ──────────────────────────────────────────────────────
    _upsert_stage(db, job_id, document_id, "parsing", "running")

    def page_progress(current: int, total: int) -> None:
        _upsert_stage(
            db, job_id, document_id, "parsing", "running",
            progress_detail=f"page {current} / {total}"
        )

    try:
        if doc.file_type == "docx":
            extracted_clauses = parse_docx(file_bytes)
        else:
            extracted_clauses = parse_pdf(file_bytes, progress_callback=page_progress)
    except Exception as exc:
        raise RuntimeError(f"Parsing failed: {exc}") from exc

    _upsert_stage(
        db, job_id, document_id, "parsing", "done",
        progress_detail=f"extracted {len(extracted_clauses)} annotations", finish=True
    )

    # ── Stage 4: expanding ────────────────────────────────────────────────────
    _upsert_stage(db, job_id, document_id, "expanding", "running")
    merged_clause_map: dict[str, dict] = {}
    for item in extracted_clauses:
        if item.clause_number:
            # Merge all comments that share the same identified clause (e.g. "(a)")
            key = item.clause_number
        elif item.anchor_para_idx is not None:
            # No clause number detected — keep comments separate by anchor position
            # so comments on different unnumbered paragraphs don't collapse into one card
            key = f"para::{item.anchor_para_idx}"
        else:
            key = _sha256(item.clause_text[:200])
        if key in merged_clause_map:
            existing = merged_clause_map[key]
            existing["anchor_texts"].append(item.anchor_text)
            existing["comment_texts"].extend(item.comment_texts)
            existing["comment_authors"].extend(item.comment_authors)
            existing["comment_timestamps"].extend(item.comment_timestamps)
            if len(item.clause_text) > len(existing["clause_text"]):
                existing["clause_text"] = item.clause_text
        else:
            merged_clause_map[key] = {
                "clause_number": item.clause_number,
                "anchor_texts": [item.anchor_text],
                "clause_text": item.clause_text,
                "expansion_method": item.expansion_method,
                "confidence": item.confidence,
                "page_number": item.page_number,
                "bbox": item.bbox,
                "ocr_used": item.ocr_used,
                "comment_texts": list(item.comment_texts),
                "comment_authors": list(item.comment_authors),
                "comment_timestamps": list(item.comment_timestamps),
            }
    _upsert_stage(
        db, job_id, document_id, "expanding", "done",
        progress_detail=f"merged to {len(merged_clause_map)} clause cards", finish=True
    )

    # ── Stage 5: embedding ────────────────────────────────────────────────────
    _upsert_stage(db, job_id, document_id, "embedding", "running")
    clause_texts = [v["clause_text"] for v in merged_clause_map.values()]

    def emb_progress(current: int, total: int) -> None:
        _upsert_stage(
            db, job_id, document_id, "embedding", "running",
            progress_detail=f"clause {current} / {total}"
        )

    try:
        embeddings = get_embeddings_batch_sync(clause_texts, db, progress_callback=emb_progress)
        emb_detail = f"embedded {len(clause_texts)} clauses"
    except Exception as emb_exc:
        logger.warning("Embedding failed (non-fatal), storing clauses without vectors: %s", emb_exc)
        embeddings = [None] * len(clause_texts)
        emb_detail = f"skipped ({type(emb_exc).__name__})"
    _upsert_stage(
        db, job_id, document_id, "embedding", "done",
        progress_detail=emb_detail, finish=True
    )

    # ── Stage 6: storing ──────────────────────────────────────────────────────
    _upsert_stage(db, job_id, document_id, "storing", "running")

    # Delete old clauses for this run
    from sqlalchemy import delete as sql_delete
    db.execute(
        sql_delete(Clause).where(
            Clause.document_id == uuid.UUID(document_id),
            Clause.run_id == run_id,
        )
    )
    db.flush()

    clause_rows = []
    for i, (key, data) in enumerate(merged_clause_map.items()):
        clause_id = uuid.uuid4()
        embedding = embeddings[i] if i < len(embeddings) else None
        clause = Clause(
            id=clause_id,
            document_id=uuid.UUID(document_id),
            run_id=run_id,
            clause_number=data["clause_number"],
            anchor_text=data["anchor_texts"][0] if data["anchor_texts"] else "",
            clause_text=data["clause_text"],
            expansion_method=data["expansion_method"],
            confidence=data["confidence"],
            ocr_used=data["ocr_used"],
            page_number=data["page_number"],
            bbox=data["bbox"],
            embedding=embedding,
        )
        db.add(clause)
        clause_rows.append((clause_id, data))

    db.flush()

    for clause_id, data in clause_rows:
        for j, comment_text in enumerate(data["comment_texts"]):
            if not comment_text.strip():
                continue
            author = data["comment_authors"][j] if j < len(data["comment_authors"]) else None
            ts_str = data["comment_timestamps"][j] if j < len(data["comment_timestamps"]) else None
            source_ts = None
            if ts_str:
                try:
                    source_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            db.add(Comment(
                clause_id=clause_id,
                run_id=run_id,
                comment_text=comment_text,
                author=author,
                source_timestamp=source_ts,
            ))

    doc.latest_run_id = run_id
    db.commit()

    # Write extractions.json to derived storage
    try:
        extractions = {
            "document_id": document_id,
            "run_id": run_id,
            "clause_count": len(merged_clause_map),
            "clauses": [
                {
                    "clause_number": v["clause_number"],
                    "clause_text": v["clause_text"],
                    "anchor_texts": v["anchor_texts"],
                    "expansion_method": v["expansion_method"],
                    "confidence": v["confidence"],
                    "comments": v["comment_texts"],
                }
                for v in merged_clause_map.values()
            ],
        }
        derived_path = f"vendor/{doc.vendor_case_id}/doc/{document_id}/run/{run_id}/extractions.json"
        storage_svc.upload_bytes(
            settings.bucket_derived,
            derived_path,
            json.dumps(extractions, indent=2).encode("utf-8"),
            content_type="application/json",
        )
    except Exception as exc:
        logger.warning("Failed to write extractions.json: %s", exc)

    _upsert_stage(db, job_id, document_id, "storing", "done", progress_detail="complete", finish=True)


def import_precedents(rows: list[dict], job_id: str) -> None:
    """Bulk import precedent clauses with embeddings."""
    from app.db.models import PrecedentClause
    from app.services.embeddings import get_embeddings_batch_sync
    from sqlalchemy import text

    db = _get_sync_session()
    try:
        _upsert_stage(db, job_id, "", "importing", "running")

        texts = [r["clause_text"] for r in rows]
        shas = [_sha256(t) for t in texts]

        existing_shas_rows = db.execute(
            text("SELECT text_sha256 FROM precedent_clauses WHERE text_sha256 = ANY(:shas)"),
            {"shas": shas},
        ).fetchall()
        existing_shas = {row[0] for row in existing_shas_rows}

        new_rows = [
            (rows[i], texts[i], shas[i])
            for i in range(len(rows))
            if shas[i] not in existing_shas
        ]

        if not new_rows:
            _upsert_stage(db, job_id, "", "importing", "done",
                          progress_detail="0 new rows (all duplicates)", finish=True)
            return

        new_texts = [t for _, t, _ in new_rows]

        def emb_progress(current: int, total: int) -> None:
            _upsert_stage(
                db, job_id, "", "importing", "running",
                progress_detail=f"embedding {current} / {total}"
            )

        embeddings = get_embeddings_batch_sync(new_texts, db, progress_callback=emb_progress)

        for i, (row_data, clause_text, sha) in enumerate(new_rows):
            sentiment = row_data.get("sentiment", "accepted")
            db.add(PrecedentClause(
                clause_text=clause_text,
                text_sha256=sha,
                sentiment=sentiment,
                accepted=(sentiment == "accepted"),
                is_active=True,
                source_document=row_data.get("source_document"),
                notes=row_data.get("notes"),
                embedding=embeddings[i] if i < len(embeddings) else None,
            ))

        db.commit()
        _upsert_stage(
            db, job_id, "", "importing", "done",
            progress_detail=f"imported {len(new_rows)} rows", finish=True
        )
    except Exception as exc:
        logger.error("import_precedents failed: %s", exc, exc_info=True)
        _upsert_stage(db, job_id, "", "importing", "failed", error=str(exc), finish=True)
        raise
    finally:
        db.close()
