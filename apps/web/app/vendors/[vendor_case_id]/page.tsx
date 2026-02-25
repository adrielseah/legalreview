"use client";

import { useCallback, useEffect, useState } from "react";
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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UploadDropzone } from "@/components/UploadDropzone";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { deleteDocument, getVendor, reprocessDocument, updateDocumentKind } from "@/lib/api";
import { formatDate, requestBrowserNotificationPermission } from "@/lib/utils";

const DOC_KINDS = ["T&Cs", "DPA", "AUP", "SLA", "Order Form", "NDA", "Others"];

export default function VendorDashboardPage() {
  const params = useParams();
  const vendorCaseId = params.vendor_case_id as string;
  const router = useRouter();

  const [vendor, setVendor] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJobs, setActiveJobs] = useState<Record<string, string>>({}); // documentId -> jobId

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
    requestBrowserNotificationPermission();
  }, [loadVendor]);

  const handleUploadComplete = (jobId: string, documentId: string) => {
    setActiveJobs((prev) => ({ ...prev, [documentId]: jobId }));
    loadVendor(); // Refresh to show the new document
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

      {/* Documents list */}
      <div>
        <h2 className="text-sm font-semibold mb-3">
          Documents{" "}
          <span className="text-muted-foreground font-normal">
            ({vendor.documents.length})
          </span>
        </h2>

        {vendor.documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No documents yet. Upload a contract to begin.
          </p>
        ) : (
          <div className="space-y-2">
            {vendor.documents.map((doc: any) => {
              const activeJobId = activeJobs[doc.id] || null;
              const showJobBadge =
                activeJobId ||
                doc.job_status === "running" ||
                doc.job_status === "pending";

              return (
                <div
                  key={doc.id}
                  className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
                >
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0" />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">
                        {doc.original_filename}
                      </span>
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {doc.file_type.toUpperCase()}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                        <Calendar className="h-2.5 w-2.5" />
                        {formatDate(doc.uploaded_at)}
                      </span>
                      {doc.run_count > 0 && (
                        <span className="text-[11px] text-muted-foreground">
                          {doc.run_count} run{doc.run_count !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Doc kind selector */}
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

                  {/* Status */}
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

                  {/* Actions */}
                  <div className="shrink-0 flex items-center gap-1">
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
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
