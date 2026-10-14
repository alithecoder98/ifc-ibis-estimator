"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

// elementId is null while the detail panel is closed - disabled rather than
// skipped, so the sheet can mount ahead of the first click without firing a
// request for a nonexistent element.
export function useElementDetail(projectId: number, elementId: number | null) {
  return useQuery({
    queryKey: ["projects", projectId, "elements", elementId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/projects/{project_id}/elements/{element_id}",
        {
          params: {
            path: { project_id: projectId, element_id: elementId as number },
          },
        },
      );
      if (error) throw error;
      return data;
    },
    enabled: elementId !== null,
  });
}
