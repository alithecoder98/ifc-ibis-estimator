"use client";

import { useQueryClient } from "@tanstack/react-query";
import { type DragEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@/components/ui/progress";
import { useJob } from "@/lib/jobs/use-job";
import { jobStepLabel } from "@/lib/jobs/job-step-label";
import { useUploadFile } from "@/lib/projects/use-upload-file";

const ALLOWED_EXTENSIONS = [".ifc", ".ifczip", ".ifcxml"];

export function UploadDropzone({ projectId }: { projectId: number }) {
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [jobId, setJobId] = useState<number | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const upload = useUploadFile(projectId);
  const job = useJob(jobId);
  const queryClient = useQueryClient();

  const isUploading = upload.isPending;
  const isProcessing = jobId !== null && job.data?.status === "running";
  const isDone = job.data?.status === "done";
  const jobFailed = job.data?.status === "failed";
  const uploadFailed = upload.isError && !localError;

  // The job-poll cache (["jobs", jobId]) is the only thing useJob touches -
  // every other query on the page (file status badge, Overview stats,
  // Elements tab) was left showing its pre-upload snapshot until a full
  // reload, even though "Processing complete" below correctly implied
  // everything had actually finished. Confirmed live: Total elements stayed
  // at 0 with the file still showing "Uploaded" right after a real upload
  // that had genuinely extracted and classified everything.
  useEffect(() => {
    if (isDone) {
      queryClient.invalidateQueries({ queryKey: ["projects", projectId] });
    }
  }, [isDone, projectId, queryClient]);

  function hasAllowedExtension(file: File): boolean {
    const name = file.name.toLowerCase();
    return ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
  }

  function startUpload(file: File) {
    setLocalError(null);
    if (!hasAllowedExtension(file)) {
      setLocalError(
        `"${file.name}" isn't an IFC file (expected .ifc, .ifczip, or .ifcxml).`,
      );
      return;
    }
    setUploadPercent(0);
    upload.mutate(
      { file, onProgress: setUploadPercent },
      { onSuccess: (ifcFile) => setJobId(ifcFile.job_id ?? null) },
    );
  }

  function reset() {
    setJobId(null);
    setUploadPercent(0);
    setLocalError(null);
    upload.reset();
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDraggingOver(false);
    const file = event.dataTransfer.files[0];
    if (file) startUpload(file);
  }

  const isActive = isUploading || isProcessing;

  return (
    <Card>
      <CardContent>
        {!isActive && !isDone && !jobFailed && (
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setIsDraggingOver(true);
            }}
            onDragLeave={() => setIsDraggingOver(false)}
            onDrop={handleDrop}
            className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
              isDraggingOver
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25"
            }`}
          >
            <p className="text-muted-foreground mb-3 text-sm">
              Drag an IFC file here, or
            </p>
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
            >
              Choose file
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_EXTENSIONS.join(",")}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) startUpload(file);
                event.target.value = "";
              }}
            />
          </div>
        )}

        {isUploading && (
          <Progress value={uploadPercent}>
            <ProgressLabel>Uploading...</ProgressLabel>
            <ProgressValue />
          </Progress>
        )}

        {isProcessing && job.data && (
          <Progress value={job.data.progress}>
            <ProgressLabel>{jobStepLabel(job.data.progress)}</ProgressLabel>
            <ProgressValue />
          </Progress>
        )}

        {isDone && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-green-700 dark:text-green-500">
              Processing complete.
            </p>
            <Button variant="outline" size="sm" onClick={reset}>
              Upload another
            </Button>
          </div>
        )}

        {(localError || uploadFailed || jobFailed) && (
          <div className="space-y-2">
            <p className="text-sm text-red-600" role="alert">
              {localError ??
                (jobFailed
                  ? (job.data?.error ?? "Processing failed.")
                  : "Upload failed - please try again.")}
            </p>
            <Button variant="outline" size="sm" onClick={reset}>
              Try again
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
