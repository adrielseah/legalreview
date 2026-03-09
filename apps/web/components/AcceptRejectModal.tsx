"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { acceptClause, rejectClause } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clauseId: string;
  mode: "accept" | "reject";
  defaultNotes?: string;
  onSuccess?: () => void;
}

export function AcceptRejectModal({ open, onOpenChange, clauseId, mode, defaultNotes, onSuccess }: Props) {
  const [sourceDocument, setSourceDocument] = useState("");
  const [notes, setNotes] = useState(defaultNotes ?? "");
  useEffect(() => {
    if (open && defaultNotes) setNotes(defaultNotes);
  }, [open, defaultNotes]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    try {
      const opts = {
        source_document: sourceDocument.trim() || null,
        notes: notes.trim() || null,
      };
      if (mode === "accept") {
        await acceptClause(clauseId, opts);
      } else {
        await rejectClause(clauseId, opts);
      }
      onOpenChange(false);
      setSourceDocument("");
      setNotes("");
      onSuccess?.();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const isAccept = mode === "accept";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isAccept ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-400" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-red-400" />
            )}
            {isAccept ? "Accept as Precedent" : "Mark as Problematic"}
          </DialogTitle>
        </DialogHeader>

        <p className="text-xs text-muted-foreground">
          {isAccept
            ? "This clause will be added to the accepted precedents database and used for future similarity comparisons."
            : "This clause will be flagged as rejected/problematic. Future similar clauses will show a red warning."}
        </p>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="source_doc">
              Source Document{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Input
              id="source_doc"
              placeholder="e.g. Vendor Agreement v2.1"
              value={sourceDocument}
              onChange={(e) => setSourceDocument(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="notes">
              Notes{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Textarea
              id="notes"
              placeholder={
                isAccept
                  ? "e.g. Standard indemnity cap agreed at $2M"
                  : "e.g. Unlimited liability — not acceptable"
              }
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="min-h-[80px]"
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            variant={isAccept ? "success" : "destructive"}
            onClick={handleSubmit}
            disabled={loading}
            className="gap-1.5"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {isAccept ? "Accept" : "Mark as Problematic"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
