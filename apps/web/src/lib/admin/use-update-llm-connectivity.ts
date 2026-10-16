"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export type LLMConnectivityInput = {
  base_url: string;
  embedding_model: string;
  llm_model: string;
};

export function useUpdateLLMConnectivity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: LLMConnectivityInput) => {
      const { data, error } = await apiClient.PATCH("/settings/llm", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "llm"] });
    },
  });
}
