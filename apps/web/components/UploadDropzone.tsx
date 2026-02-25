"use client";

import { useCallback, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadInit, uploadFileDirect, uploadComplete, getJob } from "@/lib/api";

interface FileUploadState {
  file: File;
  status: "idle" | "uploading" | "processing" | "done" | "error";
  uploadPct: number;
  jobId: string | null;
  error: string | null;
}

interface Props {
  vendorCaseId: string;
  onUploadComplete?: (jobId: string, documentId: string) => void;
}

export function UploadDropzone({ vendorCaseId, onUploadComplete }: Props) {
  const [uploads, setUploads] = useState<FileUploadState[]>([]);
  const [queueStatus, setQueueStatus] = useState<{
    total: number;
    current: number;
    filename: string;
  } | null>(null);

  const updateUpload = (index: number, update: Partial<FileUploadState>) => {
    setUploads((prev) =>
      prev.map((u, i) => (i === index ? { ...u, ...update } : u))
    );
  };

  const processingRef = useRef(false);

  /** Poll job until it reaches a terminal state to avoid exhausting DB connections when multiple docs are dropped. */
  const waitForJobEnd = (jobId: string): Promise<void> => {
    const TERMINAL = ["done", "failed", "duplicate"];
    return new Promise((resolve) => {
      const poll = async () => {
        try {
          const job = await getJob(jobId);
          if (TERMINAL.includes(job.status)) {
            resolve();
            return;
          }
        } catch {
          // Ignore poll errors
        }
        setTimeout(poll, 2000);
      };
      poll();
    });
  };

  const processFile = async (
    file: File,
    index: number
  ): Promise<string | null> => {
    updateUpload(index, { status: "uploading", uploadPct: 0 });

    try {
      const { document_id, upload_url } = await uploadInit(
        vendorCaseId,
        file.name
      );

      await uploadFileDirect(upload_url, file, (pct) => {
        updateUpload(index, { uploadPct: pct });
      });

      updateUpload(index, { status: "processing", uploadPct: 100 });
      const { job_id } = await uploadComplete(document_id);
      updateUpload(index, { jobId: job_id });

      onUploadComplete?.(job_id, document_id);
      return job_id;
    } catch (err: any) {
      updateUpload(index, { status: "error", error: err.message });
      return null;
    }
  };

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const MAX_BYTES = 25 * 1024 * 1024;
      const validFiles = acceptedFiles.filter((f) => {
        if (f.size > MAX_BYTES) {
          alert(`${f.name} exceeds the 25 MB limit.`);
          return false;
        }
        return true;
      });

      if (validFiles.length === 0) return;
      if (processingRef.current) return;
      processingRef.current = true;

      const startIndex = uploads.length;
      const newUploads: FileUploadState[] = validFiles.map((file) => ({
        file,
        status: "idle",
        uploadPct: 0,
        jobId: null,
        error: null,
      }));
      setUploads((prev) => [...prev, ...newUploads]);

      const total = validFiles.length;
      for (let i = 0; i < total; i++) {
        setQueueStatus({
          total,
          current: i + 1,
          filename: validFiles[i].name,
        });
        const jobId = await processFile(validFiles[i], startIndex + i);
        if (jobId) await waitForJobEnd(jobId);
      }

      setQueueStatus(null);
      processingRef.current = false;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [vendorCaseId, uploads.length]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    multiple: true,
  });

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-blue-400 bg-blue-400/10"
            : "border-border hover:border-muted-foreground/50 hover:bg-accent/30"
        )}
      >
        <input {...getInputProps()} />
        <Upload className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
        <p className="text-sm font-medium">
          {isDragActive ? "Drop files here…" : "Drag & drop .pdf or .docx files"}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          or click to browse — max 25 MB per file
        </p>
      </div>

      {queueStatus && (
        <p className="text-xs text-muted-foreground rounded-md bg-muted/60 px-3 py-2">
          <span className="font-medium text-foreground">
            {queueStatus.total} file{queueStatus.total !== 1 ? "s" : ""} in queue
          </span>
          {" — processing one at a time. "}
          Now: {queueStatus.current} of {queueStatus.total}
          {" — "}
          <span className="truncate inline-block max-w-[200px] align-bottom" title={queueStatus.filename}>
            {queueStatus.filename}
          </span>
        </p>
      )}
    </div>
  );
}
