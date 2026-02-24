"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { uploadInit, uploadFileDirect, uploadComplete } from "@/lib/api";

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

  const updateUpload = (index: number, update: Partial<FileUploadState>) => {
    setUploads((prev) =>
      prev.map((u, i) => (i === index ? { ...u, ...update } : u))
    );
  };

  const processFile = async (file: File, index: number) => {
    updateUpload(index, { status: "uploading", uploadPct: 0 });

    try {
      // Step 1: Init upload
      const { document_id, upload_url } = await uploadInit(
        vendorCaseId,
        file.name
      );

      // Step 2: Upload to storage
      await uploadFileDirect(upload_url, file, (pct) => {
        updateUpload(index, { uploadPct: pct });
      });

      // Step 3: Complete upload (triggers processing)
      updateUpload(index, { status: "processing", uploadPct: 100 });
      const { job_id } = await uploadComplete(document_id);
      updateUpload(index, { jobId: job_id });

      onUploadComplete?.(job_id, document_id);
    } catch (err: any) {
      updateUpload(index, { status: "error", error: err.message });
    }
  };

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const MAX_BYTES = 25 * 1024 * 1024;
      const validFiles = acceptedFiles.filter((f) => {
        if (f.size > MAX_BYTES) {
          alert(`${f.name} exceeds the 25 MB limit.`);
          return false;
        }
        return true;
      });

      const startIndex = uploads.length;
      const newUploads: FileUploadState[] = validFiles.map((file) => ({
        file,
        status: "idle",
        uploadPct: 0,
        jobId: null,
        error: null,
      }));
      setUploads((prev) => [...prev, ...newUploads]);

      validFiles.forEach((file, i) => {
        processFile(file, startIndex + i);
      });
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

      {uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((upload, i) => (
            <div
              key={i}
              className="flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2"
            >
              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{upload.file.name}</p>
                {upload.status === "uploading" && (
                  <div className="mt-1">
                    <div className="h-1 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 transition-all duration-200"
                        style={{ width: `${upload.uploadPct}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      Uploading {upload.uploadPct}%
                    </p>
                  </div>
                )}
                {upload.status === "processing" && (
                  <p className="text-[10px] text-blue-400 mt-0.5 flex items-center gap-1">
                    <Loader2 className="h-2.5 w-2.5 animate-spin" />
                    Processing…
                  </p>
                )}
                {upload.status === "done" && (
                  <p className="text-[10px] text-emerald-400 mt-0.5">Done</p>
                )}
                {upload.status === "error" && (
                  <p className="text-[10px] text-destructive mt-0.5 truncate">
                    {upload.error}
                  </p>
                )}
              </div>
              <div className="shrink-0">
                {upload.status === "done" && (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                )}
                {upload.status === "error" && (
                  <AlertCircle className="h-4 w-4 text-destructive" />
                )}
                {(upload.status === "uploading" || upload.status === "processing") && (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
