"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useLogout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const { error } = await apiClient.POST("/auth/logout");
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.setQueryData(["current-user"], null);
    },
  });
}
