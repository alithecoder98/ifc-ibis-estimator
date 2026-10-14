"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

// Semantic search (pgvector similarity, Phase 3.1) - distinct from useCodes's
// plain family-filtered browse list. Disabled until there's a real query, same
// "disabled not skipped" pattern as use-element-detail.ts.
export function useSearchCodes(query: string, family: string | null) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: ["codes", "search", trimmed, family],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/codes/search", {
        params: { query: { q: trimmed, ...(family ? { family } : {}) } },
      });
      if (error) throw error;
      return data;
    },
    enabled: trimmed.length > 0,
  });
}
