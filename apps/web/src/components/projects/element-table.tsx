"use client";

import {
  type ColumnDef,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getGroupedRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { ElementDetailSheet } from "@/components/projects/element-detail-sheet";
import { statusBadge } from "@/lib/projects/status-badge";
import { useProjectElements } from "@/lib/projects/use-project-elements";
import type { components } from "@/lib/api/schema";

type ElementRow = components["schemas"]["ElementRowOut"];

const ALL = "__all__";

const COLUMN_LABELS: Record<string, string> = {
  element: "Element",
  ifc_class: "IFC class",
  storey: "Storey",
  material: "Material",
  quantity: "Quantity",
  suggested_ibis_code: "Suggested code",
  internal_element: "Internal element",
  confidence: "Confidence",
  status: "Status",
  family: "Family",
};

const columns: ColumnDef<ElementRow>[] = [
  {
    id: "element",
    header: "Element",
    accessorFn: (row) => row.name ?? row.global_id,
  },
  { id: "ifc_class", header: "IFC class", accessorKey: "ifc_class" },
  { id: "storey", header: "Storey", accessorKey: "storey" },
  { id: "material", header: "Material", accessorKey: "material" },
  {
    id: "quantity",
    header: "Quantity",
    // accessorFn must stay numeric (not the "value unit" display string) or
    // TanStack's default sort would compare lexicographically - "100 m2"
    // sorting before "20 m2".
    accessorFn: (row) => row.quantity,
    cell: ({ row }) =>
      row.original.quantity !== null
        ? `${row.original.quantity} ${row.original.unit ?? ""}`.trim()
        : "-",
  },
  {
    id: "suggested_ibis_code",
    header: "Suggested code",
    accessorKey: "suggested_ibis_code",
  },
  {
    id: "internal_element",
    header: "Internal element",
    accessorKey: "internal_element",
  },
  {
    id: "confidence",
    header: "Confidence",
    accessorKey: "confidence",
    cell: ({ getValue }) => {
      const value = getValue<number | null>();
      return value !== null ? value.toFixed(2) : "-";
    },
  },
  {
    id: "status",
    header: "Status",
    accessorKey: "status",
    cell: ({ getValue }) => {
      const value = getValue<string | null>();
      if (!value) return "-";
      const badge = statusBadge(value);
      return <Badge variant={badge.variant}>{badge.label}</Badge>;
    },
  },
  { id: "family", header: "Family", accessorKey: "family" },
  { id: "group_hash", header: "Group", accessorKey: "group_hash" },
];

const DEFAULT_VISIBILITY: VisibilityState = { group_hash: false };

export function ElementTable({ projectId }: { projectId: number }) {
  const {
    data: elements,
    isLoading,
    isError,
    refetch,
  } = useProjectElements(projectId);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [familyFilter, setFamilyFilter] = useState(ALL);
  const [storeyFilter, setStoreyFilter] = useState(ALL);
  const [minConfidence, setMinConfidence] = useState("");
  const [maxConfidence, setMaxConfidence] = useState("");
  const [grouped, setGrouped] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] =
    useState<VisibilityState>(DEFAULT_VISIBILITY);
  const [selectedElementId, setSelectedElementId] = useState<number | null>(
    null,
  );

  // A fresh [] on every render (when elements is still undefined) would
  // defeat every useMemo below it, which all depend on this reference.
  const rows = useMemo(() => elements ?? [], [elements]);

  const statuses = useMemo(
    () => [...new Set(rows.map((r) => r.status).filter(Boolean))] as string[],
    [rows],
  );
  const families = useMemo(
    () => [...new Set(rows.map((r) => r.family))],
    [rows],
  );
  const storeys = useMemo(
    () => [...new Set(rows.map((r) => r.storey).filter(Boolean))] as string[],
    [rows],
  );

  const filteredData = useMemo(() => {
    const min = minConfidence === "" ? null : Number(minConfidence);
    const max = maxConfidence === "" ? null : Number(maxConfidence);
    const needle = search.trim().toLowerCase();

    return rows.filter((row) => {
      if (statusFilter !== ALL && row.status !== statusFilter) return false;
      if (familyFilter !== ALL && row.family !== familyFilter) return false;
      if (storeyFilter !== ALL && row.storey !== storeyFilter) return false;
      if (min !== null && (row.confidence ?? -1) < min) return false;
      if (max !== null && (row.confidence ?? 2) > max) return false;
      if (needle) {
        const haystack = [
          row.name,
          row.global_id,
          row.internal_element,
          row.suggested_ibis_code,
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [
    rows,
    statusFilter,
    familyFilter,
    storeyFilter,
    minConfidence,
    maxConfidence,
    search,
  ]);

  // Must stay referentially stable across renders - a fresh [] literal inline
  // in `state.grouping` below (with no onGroupingChange handler) made TanStack
  // Table think grouping changed on every single render, triggering an
  // internal reset that re-rendered this component hundreds of times per
  // second with zero user interaction and zero network calls. Only found by
  // actually rendering the page in a browser - no test or curl-based check
  // could have caught a pure client-side render storm like this.
  const grouping = useMemo(() => (grouped ? ["group_hash"] : []), [grouped]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: {
      sorting,
      columnVisibility,
      grouping,
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowId: (row) => String(row.id),
  });

  const { rows: tableRows } = table.getRowModel();
  // Group header rows have nothing to open a detail panel for - J/K navigation
  // (and the row-click handler below) only ever care about the leaf rows.
  const leafRows = useMemo(
    () => tableRows.filter((row) => !row.getIsGrouped()),
    [tableRows],
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 40,
    overscan: 10,
  });

  // J/K move to the next/previous row in whatever order is currently on
  // screen (respecting sort/filter/group) and open that row's detail panel -
  // works whether the panel is already open or not. Ignored while typing in
  // a filter/search field or a dialog form so it doesn't fight with "j"/"k"
  // as literal characters.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const key = event.key.toLowerCase();
      if (key !== "j" && key !== "k") return;

      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return;
      }
      if (leafRows.length === 0) return;

      const currentIndex = leafRows.findIndex(
        (row) => row.original.id === selectedElementId,
      );
      const nextIndex =
        key === "j"
          ? Math.min(currentIndex + 1, leafRows.length - 1)
          : Math.max(currentIndex - 1, 0);
      const nextRow = leafRows[nextIndex];
      setSelectedElementId(nextRow.original.id);

      const indexInTableRows = tableRows.findIndex((r) => r.id === nextRow.id);
      if (indexInTableRows >= 0) {
        virtualizer.scrollToIndex(indexInTableRows);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [leafRows, tableRows, selectedElementId, virtualizer]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-9 w-full max-w-2xl" />
        <div className="space-y-1 rounded-lg border p-2">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      </div>
    );
  }
  if (isError) {
    return (
      <ErrorState message="Couldn't load elements." onRetry={() => refetch()} />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search elements..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="max-w-xs"
        />

        <Select
          value={statusFilter}
          onValueChange={(value) => setStatusFilter(value ?? ALL)}
        >
          <SelectTrigger size="sm">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {statuses.map((s) => {
              const badge = statusBadge(s);
              return (
                <SelectItem key={s} value={s}>
                  {badge.label}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>

        <Select
          value={familyFilter}
          onValueChange={(value) => setFamilyFilter(value ?? ALL)}
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

        <Select
          value={storeyFilter}
          onValueChange={(value) => setStoreyFilter(value ?? ALL)}
        >
          <SelectTrigger size="sm">
            <SelectValue placeholder="Storey" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All storeys</SelectItem>
            {storeys.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1">
          <Input
            type="number"
            min={0}
            max={1}
            step={0.1}
            placeholder="Min conf."
            value={minConfidence}
            onChange={(event) => setMinConfidence(event.target.value)}
            className="w-24"
          />
          <span className="text-muted-foreground">-</span>
          <Input
            type="number"
            min={0}
            max={1}
            step={0.1}
            placeholder="Max conf."
            value={maxConfidence}
            onChange={(event) => setMaxConfidence(event.target.value)}
            className="w-24"
          />
        </div>

        <Button
          variant={grouped ? "default" : "outline"}
          size="sm"
          onClick={() => setGrouped((g) => !g)}
        >
          Group by type
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
            Columns
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {table.getAllLeafColumns().map((column) => (
              <DropdownMenuCheckboxItem
                key={column.id}
                checked={column.getIsVisible()}
                onCheckedChange={(checked) =>
                  column.toggleVisibility(!!checked)
                }
              >
                {COLUMN_LABELS[column.id] ?? column.id}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <span className="text-muted-foreground ml-auto text-xs">
          {filteredData.length} of {rows.length} elements
        </span>
      </div>

      <div className="rounded-lg border">
        <div className="bg-muted/50 flex border-b text-sm font-medium">
          {table.getHeaderGroups()[0]?.headers.map((header) => (
            <button
              key={header.id}
              onClick={header.column.getToggleSortingHandler()}
              className="hover:bg-muted flex min-w-32 flex-1 items-center gap-1 px-2 py-2 text-left"
            >
              {flexRender(header.column.columnDef.header, header.getContext())}
              {header.column.getIsSorted() === "asc" && "↑"}
              {header.column.getIsSorted() === "desc" && "↓"}
            </button>
          ))}
        </div>

        {tableRows.length === 0 ? (
          <p className="text-muted-foreground p-6 text-center text-sm">
            {rows.length === 0
              ? "No elements yet."
              : "No elements match your filters."}
          </p>
        ) : (
          <div ref={scrollRef} className="h-[600px] overflow-auto">
            <div
              style={{
                height: `${virtualizer.getTotalSize()}px`,
                position: "relative",
              }}
            >
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const row = tableRows[virtualRow.index];
                return (
                  <div
                    key={row.id}
                    className="absolute flex w-full items-center border-b text-sm"
                    style={{
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {row.getIsGrouped() ? (
                      <button
                        onClick={row.getToggleExpandedHandler()}
                        className="flex min-w-32 flex-1 items-center gap-1 px-2 font-medium"
                      >
                        {row.getIsExpanded() ? (
                          <ChevronDown className="size-4" />
                        ) : (
                          <ChevronRight className="size-4" />
                        )}
                        Group of {row.subRows.length} element(s)
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setSelectedElementId(row.original.id)}
                        className="hover:bg-muted flex h-full w-full items-center text-left"
                      >
                        {row.getVisibleCells().map((cell) => (
                          <div
                            key={cell.id}
                            className="min-w-32 flex-1 truncate px-2"
                          >
                            {flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext(),
                            )}
                          </div>
                        ))}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <ElementDetailSheet
        projectId={projectId}
        elementId={selectedElementId}
        onOpenChange={(open) => {
          if (!open) setSelectedElementId(null);
        }}
      />
    </div>
  );
}
