"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Search, FileText, Building2, Loader2 } from "lucide-react";
import { semanticSearch } from "@/lib/api";
import { truncate } from "@/lib/utils";
import type { SearchResult } from "@clauselens/shared";

function SearchResults() {
  const params = useSearchParams();
  const q = params.get("q") || "";
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q) return;
    setLoading(true);
    semanticSearch(q)
      .then(setResults)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [q]);

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h1 className="text-xl font-bold">Semantic Search</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Results for: <span className="text-foreground font-medium">{q}</span>
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Searching…
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && results.length === 0 && q && (
        <p className="text-sm text-muted-foreground">No results found.</p>
      )}

      <div className="space-y-3">
        {results.map((r) => (
          <Link
            key={r.clause_id}
            href={`/vendors/${r.vendor_case_id}/documents/${r.document_id}`}
            className="block rounded-lg border border-border bg-card hover:bg-accent/30 p-4 transition-colors"
          >
            <div className="flex items-center gap-2 mb-2">
              {r.clause_number && (
                <span className="font-mono text-xs text-blue-400">
                  §{r.clause_number}
                </span>
              )}
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Building2 className="h-3 w-3" />
                {r.vendor_name}
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <FileText className="h-3 w-3" />
                {r.document_filename}
              </div>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {truncate(r.clause_text, 250)}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <div className="h-1.5 w-24 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500"
                  style={{ width: `${Math.round(r.similarity * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-muted-foreground">
                {Math.round(r.similarity * 100)}% match
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="text-muted-foreground text-sm">Loading…</div>}>
      <SearchResults />
    </Suspense>
  );
}
