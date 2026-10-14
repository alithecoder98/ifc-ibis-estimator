"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useThreshold() {
  return useQuery({
    queryKey: ["settings", "threshold"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/settings/threshold");
      if (error) throw error;
      return data;
    },
  });
}
