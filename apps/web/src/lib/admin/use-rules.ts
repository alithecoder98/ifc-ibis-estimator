"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useRules(status: "suggested" | "active" | null) {
  return useQuery({
    queryKey: ["rules", status],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/rules", {
        params: { query: status ? { status_filter: status } : {} },
      });
      if (error) throw error;
      return data;
    },
  });
}
