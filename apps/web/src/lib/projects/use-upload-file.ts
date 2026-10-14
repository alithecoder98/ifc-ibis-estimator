"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { components } from "@/lib/api/schema";

type IfcFileOut = components["schemas"]["IfcFileOut"];

// XMLHttpRequest, not the typed apiClient/fetch: it's the only one of the three
// that fires upload progress events (fetch's streaming request body isn't
// supported widely enough yet to rely on for real byte-level progress).
function uploadWithProgress(
  projectId: number,
  file: File,
  onProgress: (percent: number) => void,
): Promise<IfcFileOut> {
  return new Promise((resolve, reject) => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${baseUrl}/projects/${projectId}/files`);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as IfcFileOut);
      } else {
        let message = "Upload failed.";
        try {
          message = JSON.parse(xhr.responseText).error?.message ?? message;
        } catch {
          // response body wasn't JSON - keep the generic message
        }
        reject(new Error(message));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed."));

    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

export function useUploadFile(projectId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      file,
      onProgress,
    }: {
      file: File;
      onProgress: (percent: number) => void;
    }) => uploadWithProgress(projectId, file, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projects", projectId, "files"],
      });
    },
  });
}
