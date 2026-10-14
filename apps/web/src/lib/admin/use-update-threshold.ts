"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useUpdateThreshold() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (value: number) => {
      const { data, error } = await apiClient.PATCH("/settings/threshold", {
        body: { auto_accept_threshold: value },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "threshold"] });
    },
  });
}
