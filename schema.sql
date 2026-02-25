-- ClauseLens database schema
-- Paste this entire file into: Supabase → SQL Editor → New query → Run

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- vendor_cases
CREATE TABLE IF NOT EXISTS vendor_cases (
    id          UUID PRIMARY KEY,
    vendor_name TEXT NOT NULL,
    procurement_ref TEXT,
    created_at  TIMESTAMPTZ NOT NULL,
    is_deleted  BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_vendor_cases_vendor_name      ON vendor_cases (vendor_name);
CREATE INDEX IF NOT EXISTS ix_vendor_cases_procurement_ref  ON vendor_cases (procurement_ref);

-- documents
CREATE TABLE IF NOT EXISTS documents (
    id                UUID PRIMARY KEY,
    vendor_case_id    UUID NOT NULL REFERENCES vendor_cases(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    doc_kind          TEXT,
    file_type         VARCHAR(10) NOT NULL,
    sha256            TEXT UNIQUE,
    storage_bucket    TEXT,
    storage_path      TEXT,
    uploaded_at       TIMESTAMPTZ NOT NULL,
    latest_run_id     TEXT
);
CREATE INDEX IF NOT EXISTS ix_documents_vendor_case_id ON documents (vendor_case_id);

-- clauses
CREATE TABLE IF NOT EXISTS clauses (
    id               UUID PRIMARY KEY,
    document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    run_id           TEXT,
    clause_number    TEXT,
    anchor_text      TEXT NOT NULL,
    clause_text      TEXT NOT NULL,
    expansion_method VARCHAR(30) NOT NULL,
    confidence       VARCHAR(10) NOT NULL,
    ocr_used         BOOLEAN NOT NULL DEFAULT false,
    page_number      INTEGER,
    bbox             JSONB,
    explanation      JSONB,
    embedding        vector(768),
    created_at       TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_clauses_document_id   ON clauses (document_id);
CREATE INDEX IF NOT EXISTS ix_clauses_clause_number ON clauses (clause_number);
CREATE INDEX IF NOT EXISTS ix_clauses_run_id        ON clauses (run_id);

-- comments
CREATE TABLE IF NOT EXISTS comments (
    id               UUID PRIMARY KEY,
    clause_id        UUID NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    run_id           TEXT,
    comment_text     TEXT NOT NULL,
    author           TEXT,
    source_timestamp TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_comments_clause_id ON comments (clause_id);

-- precedent_clauses
CREATE TABLE IF NOT EXISTS precedent_clauses (
    id              UUID PRIMARY KEY,
    clause_text     TEXT NOT NULL,
    text_sha256     TEXT NOT NULL UNIQUE,
    sentiment       VARCHAR(10) NOT NULL DEFAULT 'accepted',
    accepted        BOOLEAN NOT NULL DEFAULT true,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    source_document TEXT,
    notes           TEXT,
    embedding       vector(768),
    created_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_precedent_clauses_is_active  ON precedent_clauses (is_active);
CREATE INDEX IF NOT EXISTS ix_precedent_clauses_sentiment  ON precedent_clauses (sentiment);

-- job_stages
CREATE TABLE IF NOT EXISTS job_stages (
    id              UUID PRIMARY KEY,
    job_id          TEXT NOT NULL,
    document_id     UUID,
    stage           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress_detail TEXT,
    error           TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    CONSTRAINT uq_job_stages_job_id_stage UNIQUE (job_id, stage)
);
CREATE INDEX IF NOT EXISTS ix_job_stages_job_id_stage ON job_stages (job_id, stage);

-- embedding_cache
CREATE TABLE IF NOT EXISTS embedding_cache (
    text_sha256 TEXT PRIMARY KEY,
    embedding   vector(768) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL
);

-- HNSW vector indexes for fast similarity search
CREATE INDEX IF NOT EXISTS ix_clauses_embedding_hnsw
    ON clauses USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS ix_precedent_clauses_embedding_hnsw
    ON precedent_clauses USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Alembic version tracking (so setup.sh knows migrations are done)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
INSERT INTO alembic_version (version_num) VALUES ('0001')
    ON CONFLICT DO NOTHING;

-- ─── Supabase Storage RLS ───────────────────────────────────────────────────
-- The API accesses storage exclusively via the service_role_key, which bypasses
-- RLS. These policies block any anonymous/public direct access to bucket objects.
-- Run this block once in the Supabase SQL editor after creating the schema.

ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Block unauthenticated SELECT (download) on contract buckets
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'no_public_select_contracts'
  ) THEN
    CREATE POLICY no_public_select_contracts ON storage.objects
      FOR SELECT USING (
        bucket_id NOT IN ('contracts-raw', 'contracts-derived')
        OR auth.role() = 'service_role'
      );
  END IF;
END $$;

-- Block unauthenticated INSERT (upload) on contract buckets
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'no_public_insert_contracts'
  ) THEN
    CREATE POLICY no_public_insert_contracts ON storage.objects
      FOR INSERT WITH CHECK (
        bucket_id NOT IN ('contracts-raw', 'contracts-derived')
        OR auth.role() = 'service_role'
      );
  END IF;
END $$;

-- Block unauthenticated UPDATE on contract buckets
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'no_public_update_contracts'
  ) THEN
    CREATE POLICY no_public_update_contracts ON storage.objects
      FOR UPDATE USING (
        bucket_id NOT IN ('contracts-raw', 'contracts-derived')
        OR auth.role() = 'service_role'
      );
  END IF;
END $$;

-- Block unauthenticated DELETE on contract buckets
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'no_public_delete_contracts'
  ) THEN
    CREATE POLICY no_public_delete_contracts ON storage.objects
      FOR DELETE USING (
        bucket_id NOT IN ('contracts-raw', 'contracts-derived')
        OR auth.role() = 'service_role'
      );
  END IF;
END $$;
