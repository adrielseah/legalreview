import { z } from "zod";

// ─── Enums ─────────────────────────────────────────────────────────────────────

export const ConfidenceSchema = z.enum(["high", "medium", "low"]);
export const FileTypeSchema = z.enum(["pdf", "docx"]);
export const ExpansionMethodSchema = z.enum([
  "numbered_subclause",
  "paragraph",
  "pdf_paragraph",
  "boundary_merge",
]);
export const JobStatusSchema = z.enum(["pending", "running", "done", "failed", "partial"]);
export const SentimentSchema = z.enum(["accepted", "rejected"]);
export const SimilarSourceSchema = z.enum(["precedent", "same_vendor"]);

// ─── Vendor Cases ──────────────────────────────────────────────────────────────

export const VendorCaseSchema = z.object({
  id: z.string().uuid(),
  vendor_name: z.string().min(1),
  procurement_ref: z.string().nullable(),
  created_at: z.string(),
  is_deleted: z.boolean(),
});

export const CreateVendorCaseInputSchema = z.object({
  vendor_name: z.string().min(1, "Vendor name is required"),
  procurement_ref: z.string().nullable().optional(),
});

// ─── Documents ─────────────────────────────────────────────────────────────────

export const DocumentSchema = z.object({
  id: z.string().uuid(),
  vendor_case_id: z.string().uuid(),
  original_filename: z.string(),
  doc_kind: z.string().nullable(),
  file_type: FileTypeSchema,
  sha256: z.string().nullable(),
  storage_bucket: z.string().nullable(),
  storage_path: z.string().nullable(),
  uploaded_at: z.string(),
  latest_run_id: z.string().nullable(),
});

export const DocumentWithStatusSchema = DocumentSchema.extend({
  job_status: JobStatusSchema.nullable(),
  job_stage: z.string().nullable(),
  job_progress_detail: z.string().nullable(),
  run_count: z.number().int(),
});

export const UploadInitInputSchema = z.object({
  filename: z.string().min(1),
  doc_kind: z.string().nullable().optional(),
});

export const UploadInitResultSchema = z.object({
  document_id: z.string().uuid(),
  upload_url: z.string().url(),
  storage_bucket: z.string(),
  storage_path: z.string(),
});

export const UploadCompleteInputSchema = z.object({
  document_id: z.string().uuid(),
});

export const UploadCompleteResultSchema = z.object({
  job_id: z.string(),
  run_id: z.string(),
});

// ─── Jobs ──────────────────────────────────────────────────────────────────────

export const JobProgressSchema = z.object({
  job_id: z.string(),
  document_id: z.string().uuid(),
  status: JobStatusSchema,
  stage: z.string().nullable(),
  progress_detail: z.string().nullable(),
  error: z.string().nullable(),
});

export const RunHistorySchema = z.object({
  run_id: z.string(),
  job_id: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  status: JobStatusSchema,
  clause_count: z.number().int(),
  comment_count: z.number().int(),
});

// ─── Clauses & Comments ────────────────────────────────────────────────────────

export const BboxEntrySchema = z.object({
  page: z.number().int(),
  rect: z.tuple([z.number(), z.number(), z.number(), z.number()]),
});

export const ExplanationJsonSchema = z.object({
  clause_plain: z.string(),
  comment_plain: z.string(),
  risk_plain: z.string(),
});

export const CommentSchema = z.object({
  id: z.string().uuid(),
  clause_id: z.string().uuid(),
  comment_text: z.string(),
  author: z.string().nullable(),
  source_timestamp: z.string().nullable(),
  created_at: z.string(),
});

export const ClauseCardCommentSchema = z.object({
  id: z.string().uuid(),
  comment_text: z.string(),
  author: z.string().nullable(),
  source_timestamp: z.string().nullable(),
});

export const ClauseCardSchema = z.object({
  clause_id: z.string().uuid(),
  run_id: z.string().nullable(),
  clause_number: z.string().nullable(),
  confidence: ConfidenceSchema,
  expansion_method: ExpansionMethodSchema,
  clause_text: z.string(),
  anchor_texts: z.array(z.string()),
  ocr_used: z.boolean(),
  comments: z.array(ClauseCardCommentSchema),
  page_number: z.number().int().nullable(),
  bbox: z.array(BboxEntrySchema).nullable(),
  explanation: ExplanationJsonSchema.nullable(),
});

export const SimilarResultSchema = z.object({
  id: z.string().uuid(),
  clause_text: z.string(),
  similarity: z.number().min(0).max(1),
  source: SimilarSourceSchema,
  sentiment: SentimentSchema.nullable(),
  source_document: z.string().nullable(),
  vendor: z.string().nullable(),
  notes: z.string().nullable(),
  requestor: z.string().nullable(),
});

export const AcceptInputSchema = z.object({
  source_document: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});

export const RejectInputSchema = z.object({
  source_document: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});

// ─── Precedent Clauses ─────────────────────────────────────────────────────────

export const PrecedentClauseSchema = z.object({
  id: z.string().uuid(),
  clause_text: z.string(),
  sentiment: SentimentSchema,
  accepted: z.boolean(),
  is_active: z.boolean(),
  source_document: z.string().nullable(),
  vendor: z.string().nullable(),
  notes: z.string().nullable(),
  requestor: z.string().nullable(),
  created_at: z.string(),
});

export const PrecedentListResultSchema = z.object({
  items: z.array(PrecedentClauseSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});

export const PrecedentUpdateInputSchema = z.object({
  is_active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
  source_document: z.string().nullable().optional(),
  vendor: z.string().nullable().optional(),
  requestor: z.string().nullable().optional(),
  sentiment: SentimentSchema.optional(),
});

export const PrecedentStatsSchema = z.object({
  total: z.number().int(),
  active: z.number().int(),
  rejected: z.number().int(),
});

// ─── CSV Import ────────────────────────────────────────────────────────────────

export const CsvImportPreviewSchema = z.object({
  total_rows: z.number().int(),
  valid_rows: z.number().int(),
  invalid_rows: z.number().int(),
  duplicate_rows: z.number().int(),
  sample_rows: z.array(
    z.object({
      clause_text: z.string(),
      source_document: z.string().nullable(),
      notes: z.string().nullable(),
      sentiment: SentimentSchema,
    })
  ),
});

export const CsvImportResultSchema = z.object({
  job_id: z.string(),
});

// ─── Search ────────────────────────────────────────────────────────────────────

export const SearchResultSchema = z.object({
  clause_id: z.string().uuid(),
  clause_text: z.string(),
  clause_number: z.string().nullable(),
  similarity: z.number(),
  document_id: z.string().uuid(),
  document_filename: z.string(),
  vendor_case_id: z.string().uuid(),
  vendor_name: z.string(),
});
