"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useProjectFiles(projectId: number) {
  return useQuery({
    queryKey: ["projects", projectId, "files"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/projects/{project_id}/files",
        { params: { path: { project_id: projectId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}
