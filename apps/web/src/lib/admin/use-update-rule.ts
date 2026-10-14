"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type RuleUpdate = components["schemas"]["RuleUpdate"];

// Takes the rule id per-call (not as a hook argument) so one instance covers
// editing/activating any row in the rules table, not just one fixed rule.
export function useUpdateRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: RuleUpdate }) => {
      const { data, error } = await apiClient.PATCH("/rules/{rule_id}", {
        params: { path: { rule_id: id } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] });
    },
  });
}
