"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ErrorState } from "@/components/shared/error-state";
import { useProjectSummary } from "@/lib/projects/use-project-summary";

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent>
        <div className="text-muted-foreground text-xs">{label}</div>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}

export function ResultsOverview({ projectId }: { projectId: number }) {
  const {
    data: summary,
    isLoading,
    isError,
    refetch,
  } = useProjectSummary(projectId);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (isError || !summary) {
    return (
      <ErrorState
        message="Couldn't load the project summary."
        onRetry={() => refetch()}
      />
    );
  }

  const hasWarnings =
    summary.warnings.missing_quantity > 0 ||
    summary.warnings.proxy_element > 0 ||
    summary.warnings.unmapped > 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total elements" value={summary.total_elements} />
        <StatCard label="Auto-accepted" value={summary.auto_accepted} />
        <StatCard label="Needs review" value={summary.needs_review} />
        <StatCard label="Corrected" value={summary.corrected} />
      </div>

      {hasWarnings && (
        <Card>
          <CardContent className="space-y-1">
            <h3 className="text-sm font-medium">Warnings</h3>
            <ul className="text-muted-foreground space-y-0.5 text-sm">
              {summary.warnings.missing_quantity > 0 && (
                <li>
                  {summary.warnings.missing_quantity} element(s) with no
                  quantity data
                </li>
              )}
              {summary.warnings.proxy_element > 0 && (
                <li>
                  {summary.warnings.proxy_element} proxy element(s) (not
                  classified by the authoring tool)
                </li>
              )}
              {summary.warnings.unmapped > 0 && (
                <li>
                  {summary.warnings.unmapped} element(s) with no matching IBIS
                  code
                </li>
              )}
            </ul>
          </CardContent>
        </Card>
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium">Totals by IBIS code</h3>
        {summary.totals_by_code.length > 0 ? (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Internal element</TableHead>
                  <TableHead className="text-right">Elements</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead>Unit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.totals_by_code.map((total) => (
                  <TableRow key={`${total.ibis_code}-${total.unit}`}>
                    <TableCell>{total.ibis_code}</TableCell>
                    <TableCell>{total.internal_element}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {total.element_count}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {total.quantity}
                    </TableCell>
                    <TableCell>{total.unit ?? "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        ) : (
          <p className="text-muted-foreground text-sm">
            No classified elements yet.
          </p>
        )}
      </div>
    </div>
  );
}
