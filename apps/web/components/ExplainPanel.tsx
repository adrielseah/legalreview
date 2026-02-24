"use client";

import { useEffect, useState } from "react";
import { Loader2, RefreshCw, BookOpen, MessageSquare, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { explainClause } from "@/lib/api";

interface ExplanationData {
  clause_plain: string;
  comment_plain: string;
  risk_plain: string;
}

interface Props {
  clauseId: string;
  initialExplanation?: ExplanationData | null;
}

export function ExplainPanel({ clauseId, initialExplanation }: Props) {
  const [explanation, setExplanation] = useState<ExplanationData | null>(
    initialExplanation || null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-trigger on mount if no cached explanation
  useEffect(() => {
    if (!explanation && !loading) {
      fetchExplanation(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clauseId]);

  const fetchExplanation = async (force: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const data = await explainClause(clauseId, force);
      setExplanation(data);
    } catch (e: any) {
      setError(e.message || "Failed to generate explanation");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-xs py-4">
        <Loader2 className="h-4 w-4 animate-spin" />
        Generating plain English explanation…
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-destructive">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchExplanation(true)}
          className="gap-1.5 text-xs"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </Button>
      </div>
    );
  }

  if (!explanation) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Plain English</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => fetchExplanation(true)}
          className="h-6 px-2 text-[10px] gap-1"
        >
          <RefreshCw className="h-3 w-3" />
          Regenerate
        </Button>
      </div>

      <div className="space-y-3">
        <ExplainSection
          icon={<BookOpen className="h-3.5 w-3.5 text-blue-400" />}
          label="What this clause means"
          text={explanation.clause_plain}
        />
        <ExplainSection
          icon={<MessageSquare className="h-3.5 w-3.5 text-amber-400" />}
          label="What the reviewer flagged"
          text={explanation.comment_plain}
        />
        <ExplainSection
          icon={<AlertTriangle className="h-3.5 w-3.5 text-red-400" />}
          label="Potential risk"
          text={explanation.risk_plain}
        />
      </div>
    </div>
  );
}

function ExplainSection({
  icon,
  label,
  text,
}: {
  icon: React.ReactNode;
  label: string;
  text: string;
}) {
  return (
    <div className="rounded-md bg-muted/40 p-3 space-y-1.5">
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className="text-xs leading-relaxed text-foreground/90">{text}</p>
    </div>
  );
}
