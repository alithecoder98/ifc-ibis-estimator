"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type ProjectUpdate = components["schemas"]["ProjectUpdate"];

export function useUpdateProject(projectId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: ProjectUpdate) => {
      const { data, error } = await apiClient.PATCH("/projects/{project_id}", {
        params: { path: { project_id: projectId } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["projects", projectId] });
    },
  });
}
