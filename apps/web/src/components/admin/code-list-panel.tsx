"use client";

import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useCodes } from "@/lib/admin/use-codes";
import { useImportCodes } from "@/lib/admin/use-import-codes";
import { useSearchCodes } from "@/lib/admin/use-search-codes";

const ALL = "__all__";
const ALLOWED_EXTENSIONS = [".csv", ".xlsx"];

export function CodeListPanel() {
  const [familyFilter, setFamilyFilter] = useState(ALL);
  const [search, setSearch] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const family = familyFilter === ALL ? null : familyFilter;
  const browse = useCodes(family);
  // Semantic (pgvector) search only kicks in once there's a query - otherwise
  // the plain family-filtered browse list is what's shown.
  const searchResult = useSearchCodes(search, family);
  const isSearching = search.trim().length > 0;

  const importCodes = useImportCodes();

  const rows = (isSearching ? searchResult.data : browse.data) ?? [];
  const isLoading = isSearching ? searchResult.isLoading : browse.isLoading;
  const isError = isSearching ? searchResult.isError : browse.isError;

  const families = useMemo(
    () =>
      [
        ...new Set((browse.data ?? []).map((c) => c.family).filter(Boolean)),
      ] as string[],
    [browse.data],
  );

  function handleFileChosen(file: File) {
    const name = file.name.toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) return;
    importCodes.mutate(file);
  }

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-medium">Import code list</h3>
            <p className="text-muted-foreground text-sm">
              CSV or XLSX. Each import adds a new version - existing rows
              aren&apos;t overwritten.
            </p>
          </div>
          <div>
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={importCodes.isPending}
            >
              {importCodes.isPending ? "Importing..." : "Choose file"}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_EXTENSIONS.join(",")}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleFileChosen(file);
                event.target.value = "";
              }}
            />
          </div>
        </div>
        {importCodes.isError && (
          <p className="mt-2 text-sm text-red-600" role="alert">
            {importCodes.error instanceof Error
              ? importCodes.error.message
              : "Import failed."}
          </p>
        )}
        {importCodes.isSuccess && (
          <p className="mt-2 text-sm text-green-700 dark:text-green-500">
            Imported {importCodes.data.length} code(s).
          </p>
        )}
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search codes (semantic)..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="max-w-xs"
        />
        <Select
          value={familyFilter}
          onValueChange={(v) => setFamilyFilter(v ?? ALL)}
        >
          <SelectTrigger size="sm">
            <SelectValue placeholder="Family" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All families</SelectItem>
            {families.map((f) => (
              <SelectItem key={f} value={f}>
                {f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground text-xs">
          {rows.length} code(s)
        </span>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading...</p>}
      {isError && (
        <p className="text-sm text-red-600" role="alert">
          Couldn&apos;t load code list.
        </p>
      )}
      {!isLoading && !isError && (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>IBIS code</TableHead>
                <TableHead>Internal element</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Family</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead className="text-right">Version</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground text-center"
                  >
                    No codes found.
                  </TableCell>
                </TableRow>
              )}
              {rows.map((code) => (
                <TableRow key={code.id}>
                  <TableCell>{code.ibis_code}</TableCell>
                  <TableCell>{code.internal_element}</TableCell>
                  <TableCell className="text-muted-foreground max-w-xs truncate">
                    {code.description ?? "-"}
                  </TableCell>
                  <TableCell>{code.family ?? "-"}</TableCell>
                  <TableCell>{code.unit ?? "-"}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {code.version}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
