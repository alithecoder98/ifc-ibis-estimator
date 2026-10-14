"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

const TERMINAL_STATUSES = new Set(["done", "failed"]);

// Polls while the job is still running, stops once it reaches a terminal
// status - enabled is false (no job yet, e.g. before an upload starts) skips
// the query entirely rather than polling a nonexistent id.
export function useJob(jobId: number | null) {
  return useQuery({
    queryKey: ["jobs", jobId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/jobs/{job_id}", {
        params: { path: { job_id: jobId! } },
      });
      if (error) throw error;
      return data;
    },
    enabled: jobId !== null,
    refetchInterval: (query) =>
      query.state.data && TERMINAL_STATUSES.has(query.state.data.status)
        ? false
        : 1500,
  });
}
