"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useSplitElement(projectId: number, elementId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST(
        "/projects/{project_id}/elements/{element_id}/split",
        {
          params: { path: { project_id: projectId, element_id: elementId } },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      // New child elements + the parent's own is_split_parent flag affect
      // the elements list, the Overview totals, and this element's own
      // detail (split_child_ids) - same broad invalidation shape as every
      // other mutation here.
      queryClient.invalidateQueries({
        queryKey: ["projects", projectId, "elements"],
      });
      queryClient.invalidateQueries({
        queryKey: ["projects", projectId, "summary"],
      });
    },
  });
}
