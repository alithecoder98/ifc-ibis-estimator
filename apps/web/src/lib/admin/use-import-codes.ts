"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { components } from "@/lib/api/schema";

type CodeListOut = components["schemas"]["CodeListOut"];

// Plain fetch, not the typed apiClient: openapi-fetch's generated body type for
// this endpoint is {file: string} (FastAPI's UploadFile shows up as a string in
// the schema), not FormData - same reason use-upload-file.ts bypasses the typed
// client for multipart. No upload-progress need here (admin action, not a
// user-facing progress bar), so plain fetch is enough, unlike that XHR-based one.
async function importCodes(file: File): Promise<CodeListOut[]> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${baseUrl}/codes/import`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    let message = "Import failed.";
    try {
      message = (await response.json()).error?.message ?? message;
    } catch {
      // response body wasn't JSON - keep the generic message
    }
    throw new Error(message);
  }
  return response.json() as Promise<CodeListOut[]>;
}

export function useImportCodes() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: importCodes,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["codes"] });
    },
  });
}
