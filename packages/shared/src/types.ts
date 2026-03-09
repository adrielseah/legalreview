// Core domain types for ClauseLens

export type Confidence = "high" | "medium" | "low";
export type FileType = "pdf" | "docx";
export type ExpansionMethod = "numbered_subclause" | "paragraph" | "pdf_paragraph" | "boundary_merge";
export type JobStatus = "pending" | "running" | "done" | "failed" | "partial" | "duplicate";
export type Sentiment = "accepted" | "rejected";
export type SimilarSource = "precedent" | "same_vendor";

// ─── Vendor Cases ──────────────────────────────────────────────────────────────

export interface VendorCase {
  id: string;
  vendor_name: string;
  procurement_ref: string | null;
  created_at: string;
  is_deleted: boolean;
}

export interface CreateVendorCaseInput {
  vendor_name: string;
  procurement_ref?: string | null;
}

// ─── Documents ─────────────────────────────────────────────────────────────────

export interface Document {
  id: string;
  vendor_case_id: string;
  original_filename: string;
  doc_kind: string | null;
  file_type: FileType;
  sha256: string | null;
  storage_bucket: string | null;
  storage_path: string | null;
  uploaded_at: string;
  latest_run_id: string | null;
}

export interface DocumentWithStatus extends Document {
  job_status: JobStatus | null;
  job_stage: string | null;
  job_progress_detail: string | null;
  run_count: number;
}

export interface UploadInitInput {
  filename: string;
  doc_kind?: string | null;
}

export interface UploadInitResult {
  document_id: string;
  upload_url: string;
  storage_bucket: string;
  storage_path: string;
}

export interface UploadCompleteInput {
  document_id: string;
}

export interface UploadCompleteResult {
  job_id: string;
  run_id: string;
}

// ─── Jobs ──────────────────────────────────────────────────────────────────────

export interface JobProgress {
  job_id: string;
  document_id: string;
  status: JobStatus;
  stage: string | null;
  progress_detail: string | null;
  error: string | null;
}

export interface RunHistory {
  run_id: string;
  job_id: string;
  started_at: string;
  finished_at: string | null;
  status: JobStatus;
  clause_count: number;
  comment_count: number;
}

// ─── Clauses & Comments ────────────────────────────────────────────────────────

export interface BboxEntry {
  page: number;
  rect: [number, number, number, number]; // [x0, y0, x1, y1]
}

export interface ExplanationJson {
  clause_plain: string;
  comment_plain: string;
  risk_plain: string;
}

export interface Comment {
  id: string;
  clause_id: string;
  comment_text: string;
  author: string | null;
  source_timestamp: string | null;
  created_at: string;
}

export interface ClauseCard {
  clause_id: string;
  run_id: string | null;
  clause_number: string | null;
  confidence: Confidence;
  expansion_method: ExpansionMethod;
  clause_text: string;
  anchor_texts: string[];
  ocr_used: boolean;
  comments: Array<{
    id: string;
    comment_text: string;
    author: string | null;
    source_timestamp: string | null;
  }>;
  page_number: number | null;
  bbox: BboxEntry[] | null;
  explanation: ExplanationJson | null;
}

export interface SimilarResult {
  id: string;
  clause_text: string;
  similarity: number; // cosine similarity 0-1
  above_threshold: boolean;
  source: SimilarSource;
  sentiment: Sentiment | null;
  source_document: string | null;
  vendor: string | null;
  notes: string | null;
}

/** Response from GET /clauses/:id/similar. reason explains why results may be empty. */
export interface SimilarResponse {
  results: SimilarResult[];
  /** Set when no results: clause has no embedding, or no precedents have embeddings. */
  reason?: "clause_has_no_embedding" | "no_precedents_with_embedding" | null;
}

export interface AcceptInput {
  source_document?: string | null;
  notes?: string | null;
}

export interface RejectInput {
  source_document?: string | null;
  notes?: string | null;
}

// ─── Precedent Clauses ─────────────────────────────────────────────────────────

export interface PrecedentClause {
  id: string;
  clause_text: string;
  sentiment: Sentiment;
  accepted: boolean;
  is_active: boolean;
  source_document: string | null;
  vendor: string | null;
  notes: string | null;
  created_at: string;
}

export interface PrecedentListResult {
  items: PrecedentClause[];
  total: number;
  limit: number;
  offset: number;
}

export interface PrecedentUpdateInput {
  is_active?: boolean;
  notes?: string | null;
  source_document?: string | null;
  vendor?: string | null;
  sentiment?: Sentiment;
}

export interface PrecedentStats {
  total: number;
  active: number;
  rejected: number;
}

// ─── CSV Import ────────────────────────────────────────────────────────────────

export interface CsvImportPreview {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  sample_rows: Array<{
    clause_text: string;
    source_document: string | null;
    notes: string | null;
    sentiment: Sentiment;
  }>;
}

export interface CsvImportResult {
  job_id: string;
}

// ─── Search ────────────────────────────────────────────────────────────────────

export interface SearchResult {
  clause_id: string;
  clause_text: string;
  clause_number: string | null;
  similarity: number;
  document_id: string;
  document_filename: string;
  vendor_case_id: string;
  vendor_name: string;
}
