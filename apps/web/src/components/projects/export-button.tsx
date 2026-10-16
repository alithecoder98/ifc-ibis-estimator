"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

// The export endpoints return raw files (Content-Disposition: attachment),
// not JSON - the typed apiClient (openapi-fetch) is built around JSON bodies, so
// this bypasses it with a plain fetch, same credentials:"include" requirement for
// the httpOnly auth cookie to cross the localhost:3000 <-> :8000 origin split.
type Format = "csv" | "excel";

const FORMAT_CONFIG: Record<
  Format,
  { path: string; filename: string; label: string }
> = {
  csv: { path: "export", filename: "export.csv", label: "Download CSV" },
  excel: {
    path: "export.xlsx",
    filename: "export.xlsx",
    label: "Download Excel",
  },
};

export function ExportButton({ projectId }: { projectId: number }) {
  const [downloading, setDownloading] = useState<Format | null>(null);
  const [error, setError] = useState<Format | null>(null);

  async function handleDownload(format: Format) {
    setDownloading(format);
    setError(null);
    try {
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const { path, filename } = FORMAT_CONFIG[format];
      const response = await fetch(`${baseUrl}/projects/${projectId}/${path}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("export failed");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `project-${projectId}-${filename}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(format);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button
          onClick={() => handleDownload("csv")}
          disabled={downloading !== null}
        >
          {downloading === "csv" ? "Preparing..." : "Download CSV"}
        </Button>
        <Button
          variant="outline"
          onClick={() => handleDownload("excel")}
          disabled={downloading !== null}
        >
          {downloading === "excel" ? "Preparing..." : "Download Excel"}
        </Button>
      </div>
      {/* Not the client's real IBIS import format yet - that template hasn't
          arrived (see CLAUDE.md). Same data as the CSV, as a real workbook. */}
      <p className="text-muted-foreground text-xs">
        Excel export uses a general layout, not the client&apos;s final IBIS
        import template yet.
      </p>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          Couldn&apos;t generate the {error === "csv" ? "CSV" : "Excel"} export.
          Try again.
        </p>
      )}
    </div>
  );
}
