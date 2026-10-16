"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

// Recovers a file stuck on "uploaded" (or "failed") with no visible way to
// retry - found live: a file's original upload-time job can be lost from the
// Redis queue (e.g. a Redis restart) while its status row stays "uploaded"
// forever, and nothing in the UI ever re-enqueued it.
export function useReprocessFile(projectId: number, fileId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST(
        "/projects/{project_id}/files/{file_id}/reprocess",
        {
          params: { path: { project_id: projectId, file_id: fileId } },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projects", projectId, "files"],
      });
    },
  });
}
