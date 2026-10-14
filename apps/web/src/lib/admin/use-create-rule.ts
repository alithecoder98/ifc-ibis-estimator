"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type RuleCreate = components["schemas"]["RuleCreate"];

export function useCreateRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: RuleCreate) => {
      const { data, error } = await apiClient.POST("/rules", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
    },
  });
}
