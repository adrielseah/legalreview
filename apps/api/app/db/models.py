import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class VendorCase(Base):
    __tablename__ = "vendor_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_name = Column(Text, nullable=False, index=True)
    procurement_ref = Column(Text, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    is_deleted = Column(Boolean, nullable=False, default=False)

    documents = relationship("Document", back_populates="vendor_case", lazy="select")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_case_id = Column(
        UUID(as_uuid=True), ForeignKey("vendor_cases.id", ondelete="CASCADE"), nullable=False
    )
    original_filename = Column(Text, nullable=False)
    doc_kind = Column(Text, nullable=True)
    file_type = Column(String(10), nullable=False)  # pdf | docx
    sha256 = Column(Text, nullable=True, unique=True)
    storage_bucket = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    latest_run_id = Column(Text, nullable=True)

    vendor_case = relationship("VendorCase", back_populates="documents")
    clauses = relationship("Clause", back_populates="document", lazy="select")

    __table_args__ = (Index("ix_documents_vendor_case_id", "vendor_case_id"),)


class Clause(Base):
    __tablename__ = "clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(Text, nullable=True)
    clause_number = Column(Text, nullable=True)
    anchor_text = Column(Text, nullable=False)
    clause_text = Column(Text, nullable=False)
    expansion_method = Column(
        String(30), nullable=False
    )  # numbered_subclause|paragraph|pdf_paragraph|boundary_merge
    confidence = Column(String(10), nullable=False)  # high|medium|low
    ocr_used = Column(Boolean, nullable=False, default=False)
    page_number = Column(Integer, nullable=True)
    bbox = Column(JSONB, nullable=True)  # [{page: N, rect: [x0,y0,x1,y1]}, ...]
    anchor_para_idx = Column(Integer, nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    explanation = Column(JSONB, nullable=True)  # {clause_plain, comment_plain, risk_plain}
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    document = relationship("Document", back_populates="clauses")
    comments = relationship("Comment", back_populates="clause", lazy="select")

    __table_args__ = (
        Index("ix_clauses_document_id", "document_id"),
        Index("ix_clauses_clause_number", "clause_number"),
        Index("ix_clauses_run_id", "run_id"),
    )


class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_id = Column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(Text, nullable=True)
    comment_text = Column(Text, nullable=False)
    author = Column(Text, nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    clause = relationship("Clause", back_populates="comments")

    __table_args__ = (Index("ix_comments_clause_id", "clause_id"),)


class PrecedentClause(Base):
    __tablename__ = "precedent_clauses"
    __table_args__ = (
        Index("ix_precedent_clauses_is_active", "is_active"),
        Index("ix_precedent_clauses_sentiment", "sentiment"),
        {"schema": "public"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_text = Column(Text, nullable=False)
    text_sha256 = Column(Text, nullable=False, unique=True)  # sha256(clause_text) for dedup
    sentiment = Column(String(10), nullable=False, default="accepted")  # accepted|rejected
    accepted = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source_document = Column(Text, nullable=True)
    vendor = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    source_clause_id = Column(UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="SET NULL"), nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class JobStage(Base):
    """Tracks per-stage progress for Celery jobs. Serves as both checkpoint and progress API."""

    __tablename__ = "job_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(Text, nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), nullable=True)
    stage = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")  # pending|running|done|failed
    progress_detail = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_job_stages_job_id_stage", "job_id", "stage"),
        UniqueConstraint("job_id", "stage", name="uq_job_stages_job_id_stage"),
    )


class EmbeddingCache(Base):
    """Caches embeddings by sha256(text) to avoid redundant OpenAI calls."""

    __tablename__ = "embedding_cache"

    text_sha256 = Column(Text, primary_key=True)
    embedding = Column(Vector(1536), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
