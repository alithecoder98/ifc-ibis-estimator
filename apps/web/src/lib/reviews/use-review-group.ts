"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type ReviewCreate = components["schemas"]["ReviewCreate"];

export function useReviewGroup(projectId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      groupHash,
      body,
    }: {
      groupHash: string;
      body: ReviewCreate;
    }) => {
      const { data, error } = await apiClient.POST(
        "/projects/{project_id}/groups/{group_hash}/reviews",
        {
          params: { path: { project_id: projectId, group_hash: groupHash } },
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
