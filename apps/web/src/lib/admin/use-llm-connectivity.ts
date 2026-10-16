"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useLLMConnectivity() {
  return useQuery({
    queryKey: ["settings", "llm"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/settings/llm");
      if (error) throw error;
      return data;
    },
  });
}
