"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

// {global_id: local_id} for the loaded fragments model - lets the viewer map
// an element (by GlobalId, the same identifier everywhere else in this app)
// to the local id the That Open Engine APIs (Hider, highlight, etc.) expect.
// Disabled until there's a real fileId, same "disabled not skipped" pattern
// as use-element-detail.ts.
export function useFragmentIdMap(projectId: number, fileId: number | null) {
  return useQuery({
    queryKey: ["projects", projectId, "files", fileId, "fragment-ids"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/projects/{project_id}/files/{file_id}/fragment-ids",
        {
          params: {
            path: { project_id: projectId, file_id: fileId as number },
          },
        },
      );
      if (error) throw error;
      return data;
    },
    enabled: fileId !== null,
  });
}
