"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type ReviewCreate = components["schemas"]["ReviewCreate"];

export function useReviewElement(projectId: number, elementId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: ReviewCreate) => {
      const { data, error } = await apiClient.POST(
        "/projects/{project_id}/elements/{element_id}/reviews",
        {
          params: { path: { project_id: projectId, element_id: elementId } },
          body,
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projects", projectId, "elements"],
      });
      queryClient.invalidateQueries({
        queryKey: ["projects", projectId, "summary"],
      });
    },
  });
}
