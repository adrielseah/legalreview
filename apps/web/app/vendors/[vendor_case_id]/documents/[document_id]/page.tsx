"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  AlertTriangle,
  Search,
  ChevronLeft,
  ChevronRight,
  Clock,
  CheckCircle,
  History,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ClauseDetail } from "@/components/ClauseDetail";
import { getDocumentResults, getDocumentRuns, reprocessDocument, deleteRun } from "@/lib/api";
import { JobStatusBadge } from "@/components/JobStatusBadge";
import { formatDate, cn } from "@/lib/utils";
import type { ClauseCard, RunHistory } from "@clauselens/shared";

const PAGE_SIZE = 20;

export default function ReviewPage() {
  const params = useParams();
  const vendorCaseId = params.vendor_case_id as string;
  const documentId = params.document_id as string;
  const router = useRouter();

  const [results, setResults] = useState<{
    clauses: ClauseCard[];
    run_id: string | null;
    ocr_page_count: number;
  } | null>(null);
  const [runs, setRuns] = useState<RunHistory[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedClauseId, setSelectedClauseId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterHasComments, setFilterHasComments] = useState(false);
  const [filterHideLow, setFilterHideLow] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [showRunHistory, setShowRunHistory] = useState(false);
  const [reparseJobId, setReparseJobId] = useState<string | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);

  const loadResults = useCallback(
    async (runId?: string | null) => {
      setLoading(true);
      try {
        const data = await getDocumentResults(documentId, runId);
        setResults(data);
        if (data.clauses.length > 0 && !selectedClauseId) {
          setSelectedClauseId(data.clauses[0].clause_id);
        }
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    },
    [documentId, selectedClauseId]
  );

  const loadRuns = useCallback(async (): Promise<RunHistory[]> => {
    try {
      const data = await getDocumentRuns(documentId);
      setRuns(data);
      return data;
    } catch {
      return [];
    }
  }, [documentId]);

  const handleReparse = async () => {
    try {
      const result = await reprocessDocument(documentId);
      setReparseJobId(result.job_id);
    } catch (e: any) {
      alert(`Failed to start reparse: ${e.message}`);
    }
  };

  const handleReparseDone = () => {
    setReparseJobId(null);
    setSelectedClauseId(null);
    loadRuns().then((runsData) => {
      const latestRunId = runsData[0]?.run_id ?? null;
      setSelectedRunId(latestRunId);
    });
  };

  const handleDeleteRun = async (runId: string) => {
    if (!confirm("Delete this run and all its extracted clauses?")) return;
    setDeletingRunId(runId);
    try {
      await deleteRun(documentId, runId);
      setSelectedClauseId(null);
      const runsData = await loadRuns();
      // Pick the new latest (skip the deleted one)
      const nextRunId = runsData.find((r) => r.run_id !== runId)?.run_id ?? null;
      setSelectedRunId(nextRunId);
    } catch (e: any) {
      alert(`Failed to delete run: ${e.message}`);
    } finally {
      setDeletingRunId(null);
    }
  };

  // On mount: load runs, pin selectedRunId to the latest.
  useEffect(() => {
    loadRuns().then((runsData) => {
      setSelectedRunId(runsData[0]?.run_id ?? null);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Whenever selectedRunId is set/changed, load that run's clauses.
  useEffect(() => {
    if (selectedRunId !== undefined) {
      loadResults(selectedRunId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId]);

  const filteredClauses = useMemo(() => {
    if (!results) return [];
    return results.clauses.filter((c) => {
      if (filterHasComments && c.comments.length === 0) return false;
      if (filterHideLow && c.confidence === "low") return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          (c.clause_number?.toLowerCase().includes(q) ?? false) ||
          c.clause_text.toLowerCase().includes(q) ||
          c.comments.some((cm) => cm.comment_text.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [results, filterHasComments, filterHideLow, searchQuery]);

  const totalPages = Math.ceil(filteredClauses.length / PAGE_SIZE);
  const pageClauses = filteredClauses.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const selectedClause = results?.clauses.find((c) => c.clause_id === selectedClauseId);

  const handleSelectClause = (id: string) => {
    setSelectedClauseId(id);
  };

  if (loading && !results) {
    return (
      <div className="h-[calc(100vh-8rem)] flex items-center justify-center text-muted-foreground text-sm">
        Loading review…
      </div>
    );
  }

  if (error) {
    return <div className="text-destructive text-sm">{error}</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header bar */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push(`/vendors/${vendorCaseId}`)}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-semibold truncate">Document Review</h1>
          <p className="text-xs text-muted-foreground">
            {filteredClauses.length} clause{filteredClauses.length !== 1 ? "s" : ""} shown
            {results?.run_id && (
              <span className="ml-2 text-muted-foreground/50">
                run: {results.run_id.slice(-8)}
              </span>
            )}
          </p>
        </div>

        {/* Reparse button / progress */}
        {reparseJobId ? (
          <JobStatusBadge
            jobId={reparseJobId}
            filename="document"
            onDone={handleReparseDone}
          />
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-xs"
            onClick={handleReparse}
            title="Re-run the parsing pipeline on this document"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reparse
          </Button>
        )}

        {/* Run history toggle */}
        {runs.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-xs"
            onClick={() => setShowRunHistory(!showRunHistory)}
          >
            <History className="h-3.5 w-3.5" />
            Runs ({runs.length})
          </Button>
        )}
      </div>

      {/* OCR banner */}
      {results && results.ocr_page_count > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-amber-900/30 border border-amber-700/40 px-3 py-2">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
          <p className="text-xs text-amber-200">
            {results.ocr_page_count} clause{results.ocr_page_count !== 1 ? "s" : ""} used OCR for text extraction — review carefully.
          </p>
        </div>
      )}

      {/* Run history panel */}
      {showRunHistory && runs.length > 0 && (
        <div className="rounded-md border border-border bg-card p-3 space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Run History
          </h3>
          <div className="space-y-1.5">
            {runs.map((run) => (
              <div
                key={run.run_id}
                className={cn(
                  "flex items-center gap-2 rounded px-3 py-2 text-xs transition-colors",
                  selectedRunId === run.run_id ? "bg-accent" : "hover:bg-accent/50"
                )}
              >
                <button
                  onClick={() => {
                    setSelectedClauseId(null);
                    setSelectedRunId(run.run_id);
                    setShowRunHistory(false);
                  }}
                  className="flex-1 flex items-center gap-3 text-left min-w-0"
                >
                  <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {run.run_id.slice(-12)}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {run.clause_count} clauses · {run.comment_count} comments
                      </span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground/60">
                      <Clock className="h-2.5 w-2.5" />
                      {formatDate(run.started_at)}
                    </div>
                  </div>
                </button>
                <button
                  onClick={() => handleDeleteRun(run.run_id)}
                  disabled={deletingRunId === run.run_id}
                  className="shrink-0 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40"
                  title="Delete this run"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main split layout */}
      <div className="flex gap-4 h-[calc(100vh-220px)]">
        {/* Left: clause list */}
        <div className="w-72 shrink-0 flex flex-col gap-2">
          {/* Filters */}
          <div className="space-y-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search clauses…"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                className="pl-8 h-8 text-xs"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setFilterHasComments(!filterHasComments);
                  setCurrentPage(1);
                }}
                className={cn(
                  "text-[10px] px-2 py-1 rounded-md border transition-colors",
                  filterHasComments
                    ? "bg-amber-900/30 border-amber-700/40 text-amber-300"
                    : "border-border text-muted-foreground hover:bg-accent"
                )}
              >
                Has comments
              </button>
              <button
                onClick={() => {
                  setFilterHideLow(!filterHideLow);
                  setCurrentPage(1);
                }}
                className={cn(
                  "text-[10px] px-2 py-1 rounded-md border transition-colors",
                  filterHideLow
                    ? "bg-secondary border-secondary text-foreground"
                    : "border-border text-muted-foreground hover:bg-accent"
                )}
              >
                Hide low confidence
              </button>
            </div>
          </div>

          {/* Clause items */}
          <div className="flex-1 overflow-y-auto space-y-1 pr-1">
            {pageClauses.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">
                No clauses match filters.
              </p>
            ) : (
              pageClauses.map((clause) => (
                <ClauseListItem
                  key={clause.clause_id}
                  clause={clause}
                  isSelected={selectedClauseId === clause.clause_id}
                  onClick={() => handleSelectClause(clause.clause_id)}
                />
              ))
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-1 shrink-0">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => p - 1)}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-[10px] text-muted-foreground">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage((p) => p + 1)}
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>

        {/* Right: clause detail */}
        <div className="flex-1 overflow-y-auto border border-border rounded-lg p-4">
          {selectedClause ? (
            <ClauseDetail
              clause={selectedClause}
              documentId={documentId}
              runId={results?.run_id}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a clause to review
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ClauseListItem({
  clause,
  isSelected,
  onClick,
}: {
  clause: ClauseCard;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-md border px-3 py-2 text-left text-xs transition-colors",
        isSelected
          ? "border-blue-600/50 bg-blue-950/30 text-foreground"
          : "border-border hover:bg-accent hover:border-accent"
      )}
    >
      <div className="flex items-center gap-2 mb-1">
        {clause.clause_number && (
          <span className="font-mono font-semibold text-blue-400 shrink-0">
            §{clause.clause_number}
          </span>
        )}
        <ConfidenceBadge confidence={clause.confidence} />
        {clause.comments.length > 0 && (
          <Badge variant="warning" className="text-[9px] px-1.5 py-0">
            {clause.comments.length} comment{clause.comments.length !== 1 ? "s" : ""}
          </Badge>
        )}
      </div>
      <p className="text-muted-foreground line-clamp-2 leading-relaxed">
        {clause.anchor_texts[0] || clause.clause_text.slice(0, 80)}
      </p>
    </button>
  );
}
