"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  ChevronRight,
  RefreshCw,
  Calendar,
  Tag,
  Trash2,
  RotateCcw,
  Copy,
  Search,
  Pencil,
  Check,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UploadDropzone } from "@/components/UploadDropzone";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { deleteDocument, getVendor, reprocessDocument, renameDocument, updateDocumentKind } from "@/lib/api";
import { formatDate } from "@/lib/utils";

const DOC_KINDS = ["T&Cs", "DPA", "AUP", "SLA", "Order Form", "NDA", "Privacy Policy", "Others"];
const STATUS_OPTIONS = ["all", "done", "running", "failed", "not_started", "duplicate"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

export default function VendorDashboardPage() {
  const params = useParams();
  const vendorCaseId = params.vendor_case_id as string;
  const router = useRouter();

  const [vendor, setVendor] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJobs, setActiveJobs] = useState<Record<string, string>>({});

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const loadVendor = useCallback(async () => {
    try {
      const data = await getVendor(vendorCaseId);
      setVendor(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [vendorCaseId]);

  useEffect(() => {
    loadVendor();
  }, [loadVendor]);

  const handleUploadComplete = (jobId: string, documentId: string) => {
    setActiveJobs((prev) => ({ ...prev, [documentId]: jobId }));
    loadVendor();
  };

  const handleJobDone = (documentId: string) => {
    setActiveJobs((prev) => {
      const next = { ...prev };
      delete next[documentId];
      return next;
    });
    loadVendor();
  };

  const handleDocKindChange = async (documentId: string, kind: string) => {
    try {
      await updateDocumentKind(documentId, kind);
      loadVendor();
    } catch {}
  };

  const handleReprocess = async (documentId: string) => {
    try {
      const result = await reprocessDocument(documentId);
      setActiveJobs((prev) => ({ ...prev, [documentId]: result.job_id }));
      loadVendor();
    } catch (e: any) {
      alert(`Failed to reprocess: ${e.message}`);
    }
  };

  const handleDelete = async (documentId: string, filename: string) => {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
    try {
      await deleteDocument(documentId);
      loadVendor();
    } catch (e: any) {
      alert(`Failed to delete: ${e.message}`);
    }
  };

  const startRename = (docId: string, currentName: string) => {
    setRenamingId(docId);
    setRenameValue(currentName);
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
  };

  const confirmRename = async (docId: string) => {
    const trimmed = renameValue.trim();
    if (!trimmed) return;
    try {
      await renameDocument(docId, trimmed);
      setRenamingId(null);
      setRenameValue("");
      loadVendor();
    } catch (e: any) {
      alert(`Failed to rename: ${e.message}`);
    }
  };

  // Filtered documents
  const filteredDocs = useMemo(() => {
    if (!vendor) return [];
    return vendor.documents.filter((doc: any) => {
      // Search filter
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        if (!doc.original_filename.toLowerCase().includes(q) &&
            !(doc.doc_kind || "").toLowerCase().includes(q)) {
          return false;
        }
      }
      // Doc kind filter
      if (kindFilter !== "all" && doc.doc_kind !== kindFilter) return false;
      // Status filter
      if (statusFilter !== "all") {
        const status = doc.job_status || "not_started";
        if (statusFilter === "not_started") {
          if (status !== "not_started" && status !== null) return false;
        } else if (status !== statusFilter) {
          return false;
        }
      }
      return true;
    });
  }, [vendor, searchQuery, kindFilter, statusFilter]);

  // Status counts for summary
  const statusCounts = useMemo(() => {
    if (!vendor) return { done: 0, running: 0, failed: 0, pending: 0, total: 0 };
    const docs = vendor.documents;
    return {
      done: docs.filter((d: any) => d.job_status === "done").length,
      running: docs.filter((d: any) => d.job_status === "running" || d.job_status === "pending").length,
      failed: docs.filter((d: any) => d.job_status === "failed").length,
      pending: docs.filter((d: any) => !d.job_status || d.job_status === "not_started" || d.job_status === "duplicate").length,
      total: docs.length,
    };
  }, [vendor]);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 bg-muted rounded w-64" />
        <div className="h-40 bg-muted rounded" />
      </div>
    );
  }

  if (error || !vendor) {
    return (
      <div className="text-destructive">
        {error || "Vendor case not found."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => router.push("/vendors")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-xl font-bold">{vendor.vendor_name}</h1>
          {vendor.procurement_ref && (
            <p className="text-sm text-muted-foreground">{vendor.procurement_ref}</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto"
          onClick={loadVendor}
          title="Refresh"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Upload section */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold mb-3">Upload Documents</h2>
        <UploadDropzone
          vendorCaseId={vendorCaseId}
          onUploadComplete={handleUploadComplete}
        />
      </div>

      {/* Documents section */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold">
            Documents{" "}
            <span className="text-muted-foreground font-normal">
              ({vendor.documents.length})
            </span>
          </h2>
          {/* Status summary */}
          {vendor.documents.length > 0 && (
            <div className="flex items-center gap-2 text-[10px]">
              {statusCounts.done > 0 && (
                <span className="text-emerald-400">{statusCounts.done} done</span>
              )}
              {statusCounts.running > 0 && (
                <span className="text-blue-400">{statusCounts.running} processing</span>
              )}
              {statusCounts.failed > 0 && (
                <span className="text-red-400">{statusCounts.failed} failed</span>
              )}
              {statusCounts.pending > 0 && (
                <span className="text-muted-foreground">{statusCounts.pending} pending</span>
              )}
            </div>
          )}
        </div>

        {/* Filters */}
        {vendor.documents.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <div className="relative flex-1 min-w-[180px] max-w-xs">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search documents…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-8 text-xs"
              />
            </div>
            <Select value={kindFilter} onValueChange={setKindFilter}>
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs">All types</SelectItem>
                {DOC_KINDS.map((k) => (
                  <SelectItem key={k} value={k} className="text-xs">{k}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as StatusFilter)}>
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs">All statuses</SelectItem>
                <SelectItem value="done" className="text-xs">Done</SelectItem>
                <SelectItem value="running" className="text-xs">Processing</SelectItem>
                <SelectItem value="failed" className="text-xs">Failed</SelectItem>
                <SelectItem value="not_started" className="text-xs">Not started</SelectItem>
                <SelectItem value="duplicate" className="text-xs">Duplicate</SelectItem>
              </SelectContent>
            </Select>
            {(searchQuery || kindFilter !== "all" || statusFilter !== "all") && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs text-muted-foreground"
                onClick={() => {
                  setSearchQuery("");
                  setKindFilter("all");
                  setStatusFilter("all");
                }}
              >
                Clear filters
              </Button>
            )}
          </div>
        )}

        {vendor.documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No documents yet. Upload a contract to begin.
          </p>
        ) : filteredDocs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            No documents match the current filters.
          </p>
        ) : (
          <div className="space-y-2">
            {filteredDocs.map((doc: any) => {
              const activeJobId = activeJobs[doc.id] || null;
              const showJobBadge =
                activeJobId ||
                doc.job_status === "running" ||
                doc.job_status === "pending";
              const isRenaming = renamingId === doc.id;

              return (
                <div
                  key={doc.id}
                  className="rounded-lg border border-border bg-card px-4 py-3"
                >
                  {/* Row 1: icon, filename, DOCX, T&Cs, status */}
                  <div className="flex flex-wrap items-center gap-3">
                    <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      {isRenaming ? (
                        <div className="flex items-center gap-1.5">
                          <Input
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") confirmRename(doc.id);
                              if (e.key === "Escape") cancelRename();
                            }}
                            className="h-7 text-sm"
                            autoFocus
                          />
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-emerald-400 hover:text-emerald-300"
                            onClick={() => confirmRename(doc.id)}
                            title="Save"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-foreground"
                            onClick={cancelRename}
                            title="Cancel"
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate" title={doc.original_filename}>
                            {doc.original_filename}
                          </span>
                          <Badge variant="outline" className="text-[10px] shrink-0">
                            {doc.file_type.toUpperCase()}
                          </Badge>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 text-muted-foreground hover:text-foreground shrink-0"
                            onClick={() => startRename(doc.id, doc.original_filename)}
                            title="Rename document"
                          >
                            <Pencil className="h-3 w-3" />
                          </Button>
                        </div>
                      )}
                    </div>
                    <div className="shrink-0 w-32">
                      <Select
                        value={doc.doc_kind || ""}
                        onValueChange={(v) => handleDocKindChange(doc.id, v)}
                      >
                        <SelectTrigger className="h-7 text-xs">
                          <div className="flex items-center gap-1">
                            <Tag className="h-3 w-3" />
                            <SelectValue placeholder="Doc kind" />
                          </div>
                        </SelectTrigger>
                        <SelectContent>
                          {DOC_KINDS.map((k) => (
                            <SelectItem key={k} value={k} className="text-xs">
                              {k}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="shrink-0">
                      {showJobBadge ? (
                        <JobStatusBadge
                          jobId={activeJobId || doc.latest_run_id || ""}
                          filename={doc.original_filename}
                          onDone={() => handleJobDone(doc.id)}
                        />
                      ) : doc.job_status === "done" ? (
                        <Badge variant="success" className="text-[10px]">
                          Done
                        </Badge>
                      ) : doc.job_status === "failed" ? (
                        <Badge variant="danger" className="text-[10px]">
                          Failed
                        </Badge>
                      ) : doc.job_status === "duplicate" ? (
                        <Badge variant="secondary" className="gap-1 text-[10px]">
                          <Copy className="h-3 w-3" />
                          Duplicate — not processed
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-[10px]">
                          Not started
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Row 2: date, run count, Review, Trash — same row */}
                  <div className="mt-2 flex items-center justify-between gap-3 border-t border-border/60 pt-2">
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground min-w-0">
                      <span className="flex items-center gap-1.5 shrink-0">
                        <Calendar className="h-2.5 w-2.5" />
                        {formatDate(doc.uploaded_at)}
                      </span>
                      {doc.run_count > 0 && (
                        <>
                          <span className="text-muted-foreground/60 shrink-0" aria-hidden>·</span>
                          <span className="shrink-0">
                            {doc.run_count} run{doc.run_count !== 1 ? "s" : ""}
                          </span>
                        </>
                      )}
                    </div>
                    <div className="shrink-0 flex items-center gap-1.5">
                      {doc.job_status === "done" && (
                        <Link href={`/vendors/${vendorCaseId}/documents/${doc.id}`}>
                          <Button variant="outline" size="sm" className="gap-1 text-xs">
                            Review
                            <ChevronRight className="h-3 w-3" />
                          </Button>
                        </Link>
                      )}
                      {(doc.job_status === null || doc.job_status === "not_started" || doc.job_status === "failed") && !activeJobs[doc.id] && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1 text-xs"
                          onClick={() => handleReprocess(doc.id)}
                          title="Reprocess document"
                        >
                          <RotateCcw className="h-3 w-3" />
                          Process
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => handleDelete(doc.id, doc.original_filename)}
                        title="Delete document"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
