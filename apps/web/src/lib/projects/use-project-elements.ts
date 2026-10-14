"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

// Returns the project's full element list - filtering/sorting/grouping/search
// all happen client-side against this one in-memory set (see CLAUDE.md's 4.4
// entry for why no server-side paging: virtualisation, not paging, is what
// solves rendering 5,000+ rows smoothly).
export function useProjectElements(projectId: number) {
  return useQuery({
    queryKey: ["projects", projectId, "elements"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/projects/{project_id}/elements",
        { params: { path: { project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}
