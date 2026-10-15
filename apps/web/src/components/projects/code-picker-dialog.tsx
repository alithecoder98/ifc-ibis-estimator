"use client";

import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useSearchCodes } from "@/lib/admin/use-search-codes";
import type { components } from "@/lib/api/schema";

type CandidateOut = components["schemas"]["CandidateOut"];
type CodeListOut = components["schemas"]["CodeListOut"];

// Candidates-first (the element's own shortlist, already ranked by score),
// falling back to a live semantic search for anything not already shortlisted
// - same search endpoint the admin code-list browser uses (Phase 3.1/4.6).
export function CodePickerDialog({
  open,
  onOpenChange,
  candidates,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  candidates: CandidateOut[];
  onSelect: (code: { ibis_code: string; internal_element: string }) => void;
}) {
  const [query, setQuery] = useState("");
  const searchResult = useSearchCodes(query, null);
  const isSearching = query.trim().length > 0;

  function pick(ibisCode: string, internalElement: string) {
    onSelect({ ibis_code: ibisCode, internal_element: internalElement });
    setQuery("");
    onOpenChange(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setQuery("");
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Choose a code</DialogTitle>
        </DialogHeader>
        <Input
          placeholder="Search codes..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoFocus
        />
        <div className="max-h-80 space-y-1 overflow-y-auto">
          {!isSearching && candidates.length === 0 && (
            <p className="text-muted-foreground py-4 text-center text-sm">
              No candidates for this element - try searching.
            </p>
          )}
          {!isSearching &&
            candidates.map((candidate) => (
              <button
                key={candidate.ibis_code}
                type="button"
                onClick={() =>
                  pick(candidate.ibis_code, candidate.internal_element)
                }
                className="hover:bg-muted flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-sm"
              >
                <div className="truncate">
                  <span className="font-medium">{candidate.ibis_code}</span>{" "}
                  <span className="text-muted-foreground">
                    {candidate.internal_element}
                  </span>
                </div>
                <span className="text-muted-foreground tabular-nums">
                  {candidate.score.toFixed(3)}
                </span>
              </button>
            ))}
          {isSearching && searchResult.isLoading && (
            <p className="text-muted-foreground py-4 text-center text-sm">
              Searching...
            </p>
          )}
          {isSearching &&
            !searchResult.isLoading &&
            (searchResult.data ?? []).length === 0 && (
              <p className="text-muted-foreground py-4 text-center text-sm">
                No matching codes.
              </p>
            )}
          {isSearching &&
            (searchResult.data ?? []).map((code: CodeListOut) => (
              <button
                key={code.id}
                type="button"
                onClick={() => pick(code.ibis_code, code.internal_element)}
                className="hover:bg-muted flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-sm"
              >
                <div className="truncate">
                  <span className="font-medium">{code.ibis_code}</span>{" "}
                  <span className="text-muted-foreground">
                    {code.internal_element}
                  </span>
                </div>
              </button>
            ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
