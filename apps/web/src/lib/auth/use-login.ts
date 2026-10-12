"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api/client";

export function useLogin() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      const { data, error } = await apiClient.POST("/auth/login", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: (user) => {
      queryClient.setQueryData(["current-user"], user);
    },
  });
}
