"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { getJob } from "@/lib/api";
import { sendBrowserNotification } from "@/lib/utils";

interface Props {
  jobId: string;
  filename: string;
  onDone?: () => void;
}

export function JobStatusBadge({ jobId, filename, onDone }: Props) {
  const [status, setStatus] = useState<string>("pending");
  const [stage, setStage] = useState<string | null>(null);
  const [progressDetail, setProgressDetail] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!jobId) return;

    let interval: ReturnType<typeof setInterval>;
    let done = false;

    const poll = async () => {
      try {
        const job = await getJob(jobId);
        setStatus(job.status);
        setStage(job.stage);
        setProgressDetail(job.progress_detail);
        setProgress(job.progress);

        if (job.status === "done") {
          done = true;
          clearInterval(interval);
          sendBrowserNotification(
            "ClauseLens — Processing complete",
            `${filename} has been processed and is ready for review.`
          );
          onDone?.();
        } else if (job.status === "failed") {
          done = true;
          clearInterval(interval);
        }
      } catch {
        // Silently ignore polling errors
      }
    };

    poll();
    interval = setInterval(poll, 1500);
    return () => clearInterval(interval);
  }, [jobId, filename, onDone]);

  if (status === "done") {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        Done
      </Badge>
    );
  }

  if (status === "failed") {
    return (
      <Badge variant="danger" className="gap-1">
        <AlertCircle className="h-3 w-3" />
        Failed
      </Badge>
    );
  }

  if (status === "running" || status === "pending") {
    return (
      <div className="space-y-1">
        <Badge variant="info" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          {stage ? stage.charAt(0).toUpperCase() + stage.slice(1) : "Processing"}
        </Badge>
        {progressDetail && (
          <p className="text-[10px] text-muted-foreground">{progressDetail}</p>
        )}
        <div className="h-1 bg-muted rounded-full overflow-hidden w-24">
          <div
            className="h-full bg-blue-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    );
  }

  return (
    <Badge variant="secondary" className="gap-1">
      <Clock className="h-3 w-3" />
      Not started
    </Badge>
  );
}
