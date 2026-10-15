"use client";

import { useQuery } from "@tanstack/react-query";

// Binary, not JSON - the typed apiClient only handles JSON responses, so this
// is a plain fetch, same reasoning as use-import-codes.ts's multipart upload.
// Disabled until there's a real fileId, same pattern as use-element-detail.ts.
export function useFragmentModel(projectId: number, fileId: number | null) {
  return useQuery({
    queryKey: ["projects", projectId, "files", fileId, "model"],
    queryFn: async () => {
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(
        `${baseUrl}/projects/${projectId}/files/${fileId}/model`,
        { credentials: "include" },
      );
      if (!response.ok) {
        throw new Error(
          response.status === 404
            ? "3D model not available yet"
            : "Couldn't load the 3D model",
        );
      }
      return response.arrayBuffer();
    },
    enabled: fileId !== null,
    // The model binary never changes for a given fileId once extracted - no
    // reason to ever refetch it in the background like the rest of this
    // app's live-status queries do.
    staleTime: Infinity,
  });
}
