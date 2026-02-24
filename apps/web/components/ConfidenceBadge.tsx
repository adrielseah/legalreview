import { Badge } from "@/components/ui/badge";
import type { Confidence } from "@clauselens/shared";

const CONFIG: Record<Confidence, { label: string; variant: "success" | "warning" | "danger" }> = {
  high: { label: "High", variant: "success" },
  medium: { label: "Medium", variant: "warning" },
  low: { label: "Low (OCR)", variant: "danger" },
};

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const { label, variant } = CONFIG[confidence];
  return <Badge variant={variant}>{label}</Badge>;
}
