"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Database, AlertTriangle, Loader2 } from "lucide-react";
import Link from "next/link";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getSimilarClauses } from "@/lib/api";
import { truncate } from "@/lib/utils";
import type { SimilarResult } from "@clauselens/shared";

const BOUNDARY_RE = /\n*\[Clause boundary\s*[—–-]\s*annotation spans both clauses\]\n*/gi;
function stripBoundary(text: string) {
  return text.replace(BOUNDARY_RE, "\n\n");
}

interface Props {
  clauseId: string;
  refreshKey?: number;
}

export function SimilarityPanel({ clauseId, refreshKey = 0 }: Props) {
  const [results, setResults] = useState<SimilarResult[]>([]);
  const [reason, setReason] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SimilarResult | null>(null);

  useEffect(() => {
    setLoading(true);
    getSimilarClauses(clauseId)
      .then((res) => {
        // Support both { results, reason } and legacy array response
        const list = Array.isArray(res) ? res : (res?.results ?? []);
        setResults(Array.isArray(list) ? list : []);
        setReason(typeof res === "object" && res !== null && "reason" in res ? (res.reason ?? null) : null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [clauseId, refreshKey]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-xs py-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Loading similar clauses…
      </div>
    );
  }

  if (error) {
    return <p className="text-xs text-destructive">{error}</p>;
  }

  if (!Array.isArray(results) || results.length === 0) {
    if (reason === "clause_has_no_embedding") {
      return (
        <p className="text-xs text-muted-foreground">
          This clause has no embedding yet (e.g. processing skipped embeddings). Re-run the document job or re-upload to generate embeddings.
        </p>
      );
    }
    if (reason === "no_precedents_with_embedding") {
      return (
        <p className="text-xs text-muted-foreground">
          No similar precedents: precedent rows in the database have no embeddings yet. Run{" "}
          <Link href="/admin/precedents" className="underline text-foreground">Backfill embeddings</Link> on the Admin → Precedents page.
        </p>
      );
    }
    return (
      <p className="text-xs text-muted-foreground">
        No similar precedents found. If this clause or the precedent database have no embeddings yet, re-run the document job or run{" "}
        <Link href="/admin/precedents" className="underline text-foreground">Backfill embeddings</Link> on Admin → Precedents.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {results.map((r) => (
        <button
          key={r.id}
          type="button"
          onClick={() => setSelected(r)}
          className={`w-full text-left rounded-md border p-3 space-y-2 transition-colors hover:ring-1 hover:ring-ring cursor-pointer ${
            r.sentiment === "rejected"
              ? "border-red-700/40 bg-red-950/20"
              : r.similarity >= 0.85
              ? "border-emerald-700/40 bg-emerald-950/20"
              : "border-border bg-card"
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <Database className="h-3 w-3 shrink-0" />
              <span>{r.vendor || "Unknown vendor"}</span>
              {r.requestor && (
                <span className="text-muted-foreground/60">· {r.requestor}</span>
              )}
              {r.source_document && (
                <span className="text-muted-foreground/60">· {r.source_document}</span>
              )}
            </div>
            {r.sentiment === "rejected" && (
              <div className="flex items-center gap-1 text-[10px] text-red-400 shrink-0">
                <AlertTriangle className="h-3 w-3" />
                Rejected
              </div>
            )}
            {r.sentiment === "accepted" && (
              <div className="flex items-center gap-1 text-[10px] text-emerald-400 shrink-0">
                <CheckCircle2 className="h-3 w-3" />
                Accepted
              </div>
            )}
          </div>

          {/* Similarity bar */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  r.similarity >= 0.85
                    ? "bg-emerald-500"
                    : r.similarity >= 0.7
                    ? "bg-amber-500"
                    : "bg-muted-foreground/40"
                }`}
                style={{ width: `${Math.round(r.similarity * 100)}%` }}
              />
            </div>
            <span className="text-[10px] font-medium shrink-0 text-muted-foreground">
              {Math.round(r.similarity * 100)}%
            </span>
          </div>

          <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
            {truncate(stripBoundary(r.clause_text), 150)}
          </p>
        </button>
      ))}

      {/* Detail pop-up */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-sm">
                  <Database className="h-4 w-4 shrink-0" />
                  {selected.vendor || "Unknown vendor"}
                  {selected.requestor && (
                    <span className="text-muted-foreground font-normal">· {selected.requestor}</span>
                  )}
                  {selected.source_document && (
                    <span className="text-muted-foreground font-normal">· {selected.source_document}</span>
                  )}
                  {selected.sentiment === "accepted" && (
                    <span className="ml-auto flex items-center gap-1 text-xs text-emerald-400 font-normal">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Accepted
                    </span>
                  )}
                  {selected.sentiment === "rejected" && (
                    <span className="ml-auto flex items-center gap-1 text-xs text-red-400 font-normal">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      Rejected
                    </span>
                  )}
                </DialogTitle>
              </DialogHeader>

              {/* Similarity */}
              <div className="flex items-center gap-2 mt-2">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      selected.similarity >= 0.85
                        ? "bg-emerald-500"
                        : selected.similarity >= 0.7
                        ? "bg-amber-500"
                        : "bg-muted-foreground/40"
                    }`}
                    style={{ width: `${Math.round(selected.similarity * 100)}%` }}
                  />
                </div>
                <span className="text-[11px] text-muted-foreground">
                  {Math.round(selected.similarity * 100)}% similarity
                </span>
              </div>

              {/* Full clause text */}
              <div className="space-y-1.5 mt-4">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Clause Text
                </h4>
                <div className="rounded-md border border-border bg-muted/20 p-3">
                  <p className="text-xs leading-relaxed whitespace-pre-wrap">
                    {stripBoundary(selected.clause_text)}
                  </p>
                </div>
              </div>

              {/* Notes (Legal's review) */}
              {selected.notes && (
                <div className="space-y-1.5 mt-4">
                  <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    Legal&apos;s Review
                  </h4>
                  <div className="rounded-md border border-amber-700/30 bg-amber-950/20 p-3">
                    <p className="text-xs leading-relaxed">{selected.notes}</p>
                  </div>
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
