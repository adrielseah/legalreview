"use client";

import { useEffect, useState } from "react";
import { Building2, Database, AlertTriangle, Loader2 } from "lucide-react";
import Link from "next/link";
import { getSimilarClauses } from "@/lib/api";
import { truncate } from "@/lib/utils";
import type { SimilarResult } from "@clauselens/shared";

interface Props {
  clauseId: string;
  refreshKey?: number;
}

export function SimilarityPanel({ clauseId, refreshKey = 0 }: Props) {
  const [results, setResults] = useState<SimilarResult[]>([]);
  const [reason, setReason] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <div
          key={r.id}
          className={`rounded-md border p-3 space-y-2 ${
            r.sentiment === "rejected"
              ? "border-red-700/40 bg-red-950/20"
              : r.above_threshold
              ? "border-emerald-700/40 bg-emerald-950/20"
              : "border-border bg-card"
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              {r.source === "precedent" ? (
                <Database className="h-3 w-3 shrink-0" />
              ) : (
                <Building2 className="h-3 w-3 shrink-0" />
              )}
              <span>
                {r.source === "precedent" ? "Precedent DB" : "Same Vendor"}
              </span>
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
            <span
              className={`text-[10px] font-medium shrink-0 ${
                r.above_threshold ? "text-emerald-400" : "text-muted-foreground"
              }`}
            >
              {r.above_threshold ? "Strong match" : "Partial match"}
            </span>
          </div>

          <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-3">
            {truncate(r.clause_text, 200)}
          </p>

          {r.notes && (
            <p className="text-[10px] text-muted-foreground/70 italic">{r.notes}</p>
          )}
        </div>
      ))}
    </div>
  );
}
