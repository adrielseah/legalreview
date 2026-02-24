"use client";

import { useState } from "react";
import { CheckCircle2, AlertTriangle, Download, ChevronDown, ChevronUp, User, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ExplainPanel } from "@/components/ExplainPanel";
import { SimilarityPanel } from "@/components/SimilarityPanel";
import { AcceptRejectModal } from "@/components/AcceptRejectModal";
import { getExportUrl } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { ClauseCard } from "@clauselens/shared";

interface Props {
  clause: ClauseCard;
  documentId: string;
  runId?: string | null;
}

export function ClauseDetail({ clause, documentId, runId }: Props) {
  const [showFullText, setShowFullText] = useState(false);
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [similarRefreshKey, setSimilarRefreshKey] = useState(0);

  const clauseLines = clause.clause_text.split("\n");
  const isLong = clauseLines.length > 10 || clause.clause_text.length > 600;
  const displayText = isLong && !showFullText
    ? clause.clause_text.slice(0, 600) + "…"
    : clause.clause_text;

  const handleSuccess = () => {
    setSimilarRefreshKey((k) => k + 1);
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          {clause.clause_number && (
            <h2 className="text-base font-bold">§ {clause.clause_number}</h2>
          )}
          <div className="flex items-center gap-2">
            <ConfidenceBadge confidence={clause.confidence} />
            <span className="text-[10px] text-muted-foreground capitalize">
              {clause.expansion_method.replace(/_/g, " ")}
            </span>
            {clause.ocr_used && (
              <span className="text-[10px] text-amber-400">OCR used</span>
            )}
          </div>
        </div>
        <a
          href={getExportUrl(documentId, runId)}
          download
          className="shrink-0"
        >
          <Button variant="ghost" size="sm" className="gap-1.5 text-xs">
            <Download className="h-3.5 w-3.5" />
            Export
          </Button>
        </a>
      </div>

      {/* Clause text */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Clause Text
        </h3>
        <div className="rounded-md border border-border bg-muted/20 p-3">
          <p className="text-xs leading-relaxed whitespace-pre-wrap">
            <HighlightedText
              text={displayText}
              anchors={clause.anchor_texts}
            />
          </p>
          {isLong && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 h-6 text-[10px] gap-1"
              onClick={() => setShowFullText(!showFullText)}
            >
              {showFullText ? (
                <>
                  <ChevronUp className="h-3 w-3" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" />
                  Show full clause
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      <Separator />

      {/* Raw comments */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Legal Comment{clause.comments.length !== 1 ? "s" : ""}{" "}
          <span className="text-muted-foreground/50">({clause.comments.length})</span>
        </h3>
        {clause.comments.length === 0 ? (
          <p className="text-xs text-muted-foreground">No comments.</p>
        ) : (
          <div className="space-y-2">
            {clause.comments.map((c) => (
              <div
                key={c.id}
                className="rounded-md border border-amber-700/30 bg-amber-950/20 p-3 space-y-1.5"
              >
                <p className="text-xs leading-relaxed">{c.comment_text}</p>
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                  {c.author && (
                    <span className="flex items-center gap-1">
                      <User className="h-2.5 w-2.5" />
                      {c.author}
                    </span>
                  )}
                  {c.source_timestamp && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-2.5 w-2.5" />
                      {formatDate(c.source_timestamp)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Separator />

      {/* Plain English */}
      <div>
        <ExplainPanel
          clauseId={clause.clause_id}
          initialExplanation={clause.explanation}
        />
      </div>

      <Separator />

      {/* Similar precedents */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Similar Precedents
        </h3>
        <SimilarityPanel
          clauseId={clause.clause_id}
          refreshKey={similarRefreshKey}
        />
      </div>

      <Separator />

      {/* Actions */}
      <div className="flex gap-2">
        <Button
          variant="success"
          size="sm"
          className="gap-1.5"
          onClick={() => setAcceptOpen(true)}
        >
          <CheckCircle2 className="h-4 w-4" />
          Accept as Precedent
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-red-400 border-red-700/40 hover:bg-red-950/30"
          onClick={() => setRejectOpen(true)}
        >
          <AlertTriangle className="h-4 w-4" />
          Mark as Problematic
        </Button>
      </div>

      <AcceptRejectModal
        open={acceptOpen}
        onOpenChange={setAcceptOpen}
        clauseId={clause.clause_id}
        mode="accept"
        onSuccess={handleSuccess}
      />
      <AcceptRejectModal
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        clauseId={clause.clause_id}
        mode="reject"
        onSuccess={handleSuccess}
      />
    </div>
  );
}

function HighlightedText({
  text,
  anchors,
}: {
  text: string;
  anchors: string[];
}) {
  if (!anchors.length) {
    return <CrossRefHighlight text={text} />;
  }

  // Bold each anchor text occurrence
  const parts: Array<{ text: string; isAnchor: boolean }> = [];
  let remaining = text;

  for (const anchor of anchors) {
    if (!anchor) continue;
    const idx = remaining.indexOf(anchor);
    if (idx === -1) continue;
    if (idx > 0) parts.push({ text: remaining.slice(0, idx), isAnchor: false });
    parts.push({ text: anchor, isAnchor: true });
    remaining = remaining.slice(idx + anchor.length);
  }
  if (remaining) parts.push({ text: remaining, isAnchor: false });

  if (parts.length === 0) {
    return <CrossRefHighlight text={text} />;
  }

  return (
    <>
      {parts.map((p, i) =>
        p.isAnchor ? (
          <mark
            key={i}
            className="bg-amber-400/20 text-amber-200 rounded px-0.5 font-medium not-italic"
          >
            {p.text}
          </mark>
        ) : (
          <CrossRefHighlight key={i} text={p.text} />
        )
      )}
    </>
  );
}

function CrossRefHighlight({ text }: { text: string }) {
  const CROSS_REF = /\b(?:clause|section|article|schedule|appendix|exhibit)\s+\d+(?:\.\d+)*(?:\([a-z]+\))?/gi;
  const parts = text.split(CROSS_REF);
  const matches = text.match(CROSS_REF) || [];

  return (
    <>
      {parts.map((part, i) => (
        <span key={i}>
          {part}
          {matches[i] && (
            <span className="text-blue-400 font-medium">{matches[i]}</span>
          )}
        </span>
      ))}
    </>
  );
}
