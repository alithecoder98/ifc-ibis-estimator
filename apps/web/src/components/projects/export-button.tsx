"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

// The export endpoint returns a raw CSV file (Content-Disposition: attachment),
// not JSON - the typed apiClient (openapi-fetch) is built around JSON bodies, so
// this bypasses it with a plain fetch, same credentials:"include" requirement for
// the httpOnly auth cookie to cross the localhost:3000 <-> :8000 origin split.
export function ExportButton({ projectId }: { projectId: number }) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState(false);

  async function handleDownload() {
    setIsDownloading(true);
    setError(false);
    try {
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${baseUrl}/projects/${projectId}/export`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("export failed");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `project-${projectId}-export.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(true);
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button onClick={handleDownload} disabled={isDownloading}>
        {isDownloading ? "Preparing..." : "Download CSV"}
      </Button>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          Couldn&apos;t generate the export. Try again.
        </p>
      )}
    </div>
  );
}
