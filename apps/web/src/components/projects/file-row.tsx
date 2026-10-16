"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@/components/ui/progress";
import { jobStepLabel } from "@/lib/jobs/job-step-label";
import { useJob } from "@/lib/jobs/use-job";
import { useReprocessFile } from "@/lib/projects/use-reprocess-file";
import { statusBadge } from "@/lib/projects/status-badge";
import type { components } from "@/lib/api/schema";

type IfcFileOut = components["schemas"]["IfcFileOut"];

const PROCESSABLE_STATUSES = new Set(["uploaded", "failed"]);

// A file's status row used to be static - "Uploaded" forever with no way to
// tell whether a job was actually running or had been silently lost (found
// live: a file's upload-time job can vanish from the Redis queue entirely,
// e.g. on a Redis restart, while the file's own status row stays "uploaded"
// with nothing to recover it - no polling, no button, just a permanent dead
// end). This tracks a locally-triggered job's live progress and otherwise
// offers a manual "Process file"/"Retry" action for exactly that stuck case.
export function FileRow({
  projectId,
  file,
}: {
  projectId: number;
  file: IfcFileOut;
}) {
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const job = useJob(activeJobId);
  const reprocess = useReprocessFile(projectId, file.id);
  const queryClient = useQueryClient();

  const isDone = job.data?.status === "done";
  useEffect(() => {
    if (isDone) {
      queryClient.invalidateQueries({ queryKey: ["projects", projectId] });
    }
  }, [isDone, projectId, queryClient]);

  const fileBadge = statusBadge(file.status);
  const canProcess = PROCESSABLE_STATUSES.has(file.status);
  const isTracking =
    activeJobId !== null &&
    (job.data?.status === "queued" || job.data?.status === "running");

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <span>{file.filename}</span>
        <div className="flex items-center gap-4">
          <span className="text-muted-foreground text-xs">
            {new Date(file.uploaded_at).toLocaleString()}
          </span>
          {isTracking && job.data ? (
            <div className="w-44">
              <Progress value={job.data.progress}>
                <ProgressLabel>{jobStepLabel(job.data.progress)}</ProgressLabel>
                <ProgressValue />
              </Progress>
            </div>
          ) : (
            <Badge variant={fileBadge.variant}>{fileBadge.label}</Badge>
          )}
          {canProcess && !isTracking && (
            <Button
              size="sm"
              variant="outline"
              disabled={reprocess.isPending}
              onClick={() =>
                reprocess.mutate(undefined, {
                  onSuccess: (data) => setActiveJobId(data?.id ?? null),
                })
              }
            >
              {reprocess.isPending
                ? "Starting..."
                : file.status === "failed"
                  ? "Retry processing"
                  : "Process file"}
            </Button>
          )}
        </div>
      </CardContent>
      {reprocess.isError && (
        <CardContent className="pt-0">
          <p className="text-sm text-red-600" role="alert">
            Couldn&apos;t start processing. Try again.
          </p>
        </CardContent>
      )}
    </Card>
  );
}
