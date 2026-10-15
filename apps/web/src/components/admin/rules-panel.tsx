"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { RuleDialog } from "@/components/admin/rule-dialog";
import { useDeleteRule } from "@/lib/admin/use-delete-rule";
import { useRules } from "@/lib/admin/use-rules";
import { useUpdateRule } from "@/lib/admin/use-update-rule";
import type { components } from "@/lib/api/schema";

type RuleOut = components["schemas"]["RuleOut"];

const ALL = "__all__";

function conditionsSummary(
  conditions: { field: string; operator: string; value: unknown }[],
): string {
  return conditions
    .map(
      (c) =>
        `${c.field} ${c.operator} ${Array.isArray(c.value) ? c.value.join("-") : c.value}`,
    )
    .join(" and ");
}

export function RulesPanel() {
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<RuleOut | undefined>(
    undefined,
  );

  const status =
    statusFilter === ALL ? null : (statusFilter as "suggested" | "active");
  const { data: rules, isLoading, isError, refetch } = useRules(status);
  const updateRule = useUpdateRule();
  const deleteRule = useDeleteRule();

  function openCreate() {
    setEditingRule(undefined);
    setDialogOpen(true);
  }

  function openEdit(rule: RuleOut) {
    setEditingRule(rule);
    setDialogOpen(true);
  }

  function toggleStatus(rule: RuleOut) {
    updateRule.mutate({
      id: rule.id,
      body: { status: rule.status === "active" ? "suggested" : "active" },
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v ?? ALL)}
        >
          <SelectTrigger size="sm" className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="suggested">Suggested</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={openCreate}>New rule</Button>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}
      {isError && (
        <ErrorState message="Couldn't load rules." onRetry={() => refetch()} />
      )}
      {!isLoading && !isError && (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">Priority</TableHead>
                <TableHead>Conditions</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(rules ?? []).length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="text-muted-foreground text-center"
                  >
                    No rules found.
                  </TableCell>
                </TableRow>
              )}
              {(rules ?? []).map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="text-right tabular-nums">
                    {rule.priority}
                  </TableCell>
                  <TableCell
                    className="text-muted-foreground max-w-xs truncate"
                    title={conditionsSummary(
                      rule.conditions as {
                        field: string;
                        operator: string;
                        value: unknown;
                      }[],
                    )}
                  >
                    {conditionsSummary(
                      rule.conditions as {
                        field: string;
                        operator: string;
                        value: unknown;
                      }[],
                    )}
                  </TableCell>
                  <TableCell>
                    {rule.result_ibis_code} - {rule.result_internal_element}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        rule.status === "active" ? "default" : "secondary"
                      }
                    >
                      {rule.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(rule)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleStatus(rule)}
                    >
                      {rule.status === "active" ? "Suggest" : "Activate"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteRule.mutate(rule.id)}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <RuleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        rule={editingRule}
      />
    </div>
  );
}
