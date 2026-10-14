"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useCodes(family: string | null) {
  return useQuery({
    queryKey: ["codes", family],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/codes", {
        params: { query: family ? { family } : {} },
      });
      if (error) throw error;
      return data;
    },
  });
}
