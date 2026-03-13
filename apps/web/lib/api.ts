/**
 * Typed API client for ClauseLens backend.
 * All functions throw on non-2xx responses with an error message from the API.
 */

import type {
  ClauseCard,
  CsvImportPreview,
  CsvImportResult,
  JobProgress,
  PrecedentClause,
  PrecedentListResult,
  PrecedentStats,
  PrecedentUpdateInput,
  RunHistory,
  SearchResult,
  SimilarResponse,
  SimilarResult,
  UploadCompleteResult,
  UploadInitResult,
  VendorCase,
} from "@clauselens/shared";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ADMIN_API_KEY =
  typeof process.env.NEXT_PUBLIC_ADMIN_API_KEY === "string"
    ? process.env.NEXT_PUBLIC_ADMIN_API_KEY
    : "";

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (path.startsWith("/admin") && ADMIN_API_KEY) {
    headers["X-Admin-Key"] = ADMIN_API_KEY;
  }
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Vendors ──────────────────────────────────────────────────────────────────

export async function listVendors(q?: string): Promise<VendorCase[]> {
  const params = q ? `?q=${encodeURIComponent(q)}` : "";
  return apiFetch<VendorCase[]>(`/vendors${params}`);
}

export async function createVendor(
  vendor_name: string,
  procurement_ref?: string | null
): Promise<{ vendor_case_id: string }> {
  return apiFetch<{ vendor_case_id: string }>("/vendors", {
    method: "POST",
    body: JSON.stringify({ vendor_name, procurement_ref }),
  });
}

export async function suggestVendorNames(q: string): Promise<string[]> {
  return apiFetch<string[]>(`/vendors/suggest-names?q=${encodeURIComponent(q)}`);
}

export async function getVendor(vendorCaseId: string): Promise<
  VendorCase & {
    documents: Array<{
      id: string;
      original_filename: string;
      doc_kind: string | null;
      file_type: string;
      uploaded_at: string;
      latest_run_id: string | null;
      job_status: string | null;
      job_stage: string | null;
      job_progress_detail: string | null;
      run_count: number;
    }>;
  }
> {
  return apiFetch(`/vendors/${vendorCaseId}`);
}

export async function deleteVendor(vendorCaseId: string): Promise<void> {
  return apiFetch(`/vendors/${vendorCaseId}`, { method: "DELETE" });
}

// ─── Uploads ──────────────────────────────────────────────────────────────────

export async function uploadInit(
  vendorCaseId: string,
  filename: string,
  doc_kind?: string | null
): Promise<UploadInitResult> {
  return apiFetch<UploadInitResult>(`/vendors/${vendorCaseId}/uploads/init`, {
    method: "POST",
    body: JSON.stringify({ filename, doc_kind }),
  });
}

export async function uploadFileDirect(
  uploadUrl: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed: ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("Upload network error"));
    xhr.send(file);
  });
}

export async function uploadComplete(
  documentId: string
): Promise<UploadCompleteResult> {
  return apiFetch<UploadCompleteResult>("/uploads/complete", {
    method: "POST",
    body: JSON.stringify({ document_id: documentId }),
  });
}

// ─── Jobs ──────────────────────────────────────────────────────────────────────

export async function getJob(jobId: string): Promise<
  JobProgress & {
    progress: number;
    stages: Array<{
      stage: string;
      status: string;
      progress_detail: string | null;
      started_at: string | null;
      finished_at: string | null;
    }>;
  }
> {
  return apiFetch(`/jobs/${jobId}`);
}

// ─── Documents ────────────────────────────────────────────────────────────────

export async function getDocumentResults(
  documentId: string,
  runId?: string | null
): Promise<{
  document_id: string;
  run_id: string | null;
  ocr_page_count: number;
  clauses: ClauseCard[];
}> {
  const params = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return apiFetch(`/documents/${documentId}/results${params}`);
}

export async function getDocumentRuns(
  documentId: string
): Promise<RunHistory[]> {
  return apiFetch(`/documents/${documentId}/runs`);
}

export async function deleteDocument(documentId: string): Promise<void> {
  return apiFetch(`/documents/${documentId}`, { method: "DELETE" });
}

export async function deleteRun(documentId: string, runId: string): Promise<void> {
  return apiFetch(`/documents/${documentId}/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}

export async function reprocessDocument(
  documentId: string
): Promise<{ job_id: string; run_id: string }> {
  return apiFetch(`/documents/${documentId}/reprocess`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function updateDocumentKind(
  documentId: string,
  doc_kind: string
): Promise<{ id: string; doc_kind: string | null }> {
  return apiFetch(`/documents/${documentId}?doc_kind=${encodeURIComponent(doc_kind)}`, {
    method: "PATCH",
    body: JSON.stringify({}),
  });
}

export async function renameDocument(
  documentId: string,
  original_filename: string
): Promise<{ id: string; original_filename: string }> {
  return apiFetch(`/documents/${documentId}?original_filename=${encodeURIComponent(original_filename)}`, {
    method: "PATCH",
    body: JSON.stringify({}),
  });
}

export function getExportUrl(documentId: string, runId?: string | null): string {
  const params = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return `${API_BASE}/documents/${documentId}/export.json${params}`;
}

// ─── Clauses ──────────────────────────────────────────────────────────────────

export async function getSimilarClauses(clauseId: string): Promise<SimilarResponse> {
  return apiFetch<SimilarResponse>(`/clauses/${clauseId}/similar`);
}

export async function explainClause(
  clauseId: string,
  force = false
): Promise<{
  clause_plain: string;
  comment_plain: string;
  risk_plain: string;
}> {
  return apiFetch(`/clauses/${clauseId}/explain?force=${force}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getPrecedentStatus(
  clauseId: string
): Promise<{ sentiment: string | null }> {
  return apiFetch(`/clauses/${clauseId}/precedent-status`);
}

export async function batchPrecedentStatus(
  clauseIds: string[]
): Promise<Record<string, string>> {
  const res = await apiFetch<{ statuses: Record<string, string> }>("/clauses/batch-precedent-status", {
    method: "POST",
    body: JSON.stringify({ clause_ids: clauseIds }),
  });
  return res.statuses;
}

export async function acceptClause(
  clauseId: string,
  opts?: { source_document?: string | null; notes?: string | null }
): Promise<{ id: string; created: boolean }> {
  return apiFetch(`/clauses/${clauseId}/accept`, {
    method: "POST",
    body: JSON.stringify(opts || {}),
  });
}

export async function rejectClause(
  clauseId: string,
  opts?: { source_document?: string | null; notes?: string | null }
): Promise<{ id: string; created: boolean }> {
  return apiFetch(`/clauses/${clauseId}/reject`, {
    method: "POST",
    body: JSON.stringify(opts || {}),
  });
}

// ─── Search ────────────────────────────────────────────────────────────────────

export async function semanticSearch(
  q: string,
  limit = 10
): Promise<SearchResult[]> {
  return apiFetch<SearchResult[]>(
    `/search?q=${encodeURIComponent(q)}&limit=${limit}`
  );
}

// ─── Admin ────────────────────────────────────────────────────────────────────

export async function listPrecedents(opts?: {
  query?: string;
  active_only?: boolean;
  sentiment?: string;
  limit?: number;
  offset?: number;
}): Promise<PrecedentListResult> {
  const params = new URLSearchParams();
  if (opts?.query) params.set("query", opts.query);
  if (opts?.active_only) params.set("active_only", "true");
  if (opts?.sentiment) params.set("sentiment", opts.sentiment);
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return apiFetch<PrecedentListResult>(`/admin/precedents${qs ? `?${qs}` : ""}`);
}

export async function getPrecedentStats(): Promise<PrecedentStats> {
  return apiFetch<PrecedentStats>("/admin/precedents/stats");
}

export async function updatePrecedent(
  id: string,
  update: PrecedentUpdateInput
): Promise<{ id: string; updated: boolean }> {
  return apiFetch(`/admin/precedents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}

export async function deletePrecedent(id: string): Promise<void> {
  return apiFetch(`/admin/precedents/${id}`, { method: "DELETE" });
}

export async function previewCsvImport(file: File): Promise<CsvImportPreview> {
  const form = new FormData();
  form.append("file", file);
  const headers: Record<string, string> = {};
  if (ADMIN_API_KEY) headers["X-Admin-Key"] = ADMIN_API_KEY;
  const res = await fetch(`${API_BASE}/admin/precedents/import/preview`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function importCsvPrecedents(file: File): Promise<CsvImportResult> {
  const form = new FormData();
  form.append("file", file);
  const headers: Record<string, string> = {};
  if (ADMIN_API_KEY) headers["X-Admin-Key"] = ADMIN_API_KEY;
  const res = await fetch(`${API_BASE}/admin/precedents/import`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

/** Start backfill of embeddings for precedent_clauses with NULL embedding. Returns job_id to poll via getJob. */
export async function backfillPrecedentEmbeddings(options?: {
  /** If true, run in request (blocking). Use when async backfill does not run (e.g. localhost). */
  sync?: boolean;
}): Promise<{
  job_id: string;
  message: string;
  status?: string;
  progress_detail?: string | null;
  error?: string | null;
}> {
  const sync = options?.sync ?? true; // default sync so backfill runs on localhost
  const url = `/admin/precedents/backfill/embeddings${sync ? "?sync=1" : ""}`;
  const controller = new AbortController();
  const timeout = sync ? 300000 : 10000; // 5 min for sync, 10s for async
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const out = await apiFetch<{
      job_id: string;
      message: string;
      status?: string;
      progress_detail?: string | null;
      error?: string | null;
    }>(url, {
      method: "POST",
      body: "{}",
      signal: controller.signal,
    });
    clearTimeout(id);
    return out;
  } catch (e) {
    clearTimeout(id);
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error("Backfill timed out. Check API server logs for progress.");
    }
    throw e;
  }
}
