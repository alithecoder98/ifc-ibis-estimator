"use client";

import { useMutation } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import type { LLMConnectivityInput } from "@/lib/admin/use-update-llm-connectivity";

// Tests the submitted values directly against the live Ollama host (not
// whatever's already saved) - deliberately not tied to useUpdateLLMConnectivity
// so an admin can verify a candidate connection before committing to it.
export function useTestLLMConnectivity() {
  return useMutation({
    mutationFn: async (body: LLMConnectivityInput) => {
      const { data, error } = await apiClient.POST("/settings/llm/test", {
        body,
      });
      if (error) throw error;
      return data;
    },
  });
}
