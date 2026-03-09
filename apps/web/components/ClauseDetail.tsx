"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Download, ChevronDown, ChevronUp, User, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ExplainPanel } from "@/components/ExplainPanel";
import { SimilarityPanel } from "@/components/SimilarityPanel";
import { AcceptRejectModal } from "@/components/AcceptRejectModal";
import { getExportUrl, getPrecedentStatus } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { ClauseCard } from "@clauselens/shared";

interface Props {
  clause: ClauseCard;
  documentId: string;
  runId?: string | null;
  onPrecedentChange?: (sentiment: string) => void;
}

export function ClauseDetail({ clause, documentId, runId, onPrecedentChange }: Props) {
  const [showFullText, setShowFullText] = useState(false);
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [similarRefreshKey, setSimilarRefreshKey] = useState(0);
  const [precedentSentiment, setPrecedentSentiment] = useState<string | null>(null);

  useEffect(() => {
    getPrecedentStatus(clause.clause_id)
      .then((res) => setPrecedentSentiment(res.sentiment))
      .catch(() => {});
  }, [clause.clause_id]);

  const cleanText = clause.clause_text.replace(
    /\n*\[Clause boundary\s*[—–-]\s*annotation spans both clauses\]\n*/gi,
    "\n\n"
  );
  const clauseLines = cleanText.split("\n");
  const isLong = clauseLines.length > 10 || cleanText.length > 600;
  const displayText = isLong && !showFullText
    ? cleanText.slice(0, 600) + "…"
    : cleanText;

  const handleAcceptSuccess = () => {
    setSimilarRefreshKey((k) => k + 1);
    setPrecedentSentiment("accepted");
    onPrecedentChange?.("accepted");
  };

  const handleRejectSuccess = () => {
    setSimilarRefreshKey((k) => k + 1);
    setPrecedentSentiment("rejected");
    onPrecedentChange?.("rejected");
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <ConfidenceBadge confidence={clause.confidence} />
            <span className="text-[10px] text-muted-foreground capitalize">
              {clause.expansion_method.replace(/_/g, " ")}
            </span>
            {clause.ocr_used && (
              <span className="text-[10px] text-amber-400">OCR used</span>
            )}
            {precedentSentiment === "accepted" && (
              <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-950/30 border border-emerald-700/40 rounded-full px-2 py-0.5">
                <CheckCircle2 className="h-3 w-3" />
                Accepted as Precedent
              </span>
            )}
            {precedentSentiment === "rejected" && (
              <span className="flex items-center gap-1 text-[10px] font-medium text-red-400 bg-red-950/30 border border-red-700/40 rounded-full px-2 py-0.5">
                <AlertTriangle className="h-3 w-3" />
                Marked as Problematic
              </span>
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
          Legal&apos;s Comment{clause.comments.length !== 1 ? "s" : ""}{" "}
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
        defaultNotes={clause.comments.map((c) => c.author ? `${c.author}: ${c.comment_text}` : c.comment_text).join("\n")}
        onSuccess={handleAcceptSuccess}
      />
      <AcceptRejectModal
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        clauseId={clause.clause_id}
        mode="reject"
        defaultNotes={clause.comments.map((c) => c.author ? `${c.author}: ${c.comment_text}` : c.comment_text).join("\n")}
        onSuccess={handleRejectSuccess}
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
