"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useProject(projectId: number) {
  return useQuery({
    queryKey: ["projects", projectId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      });
      if (error) throw error;
      return data;
    },
  });
}
