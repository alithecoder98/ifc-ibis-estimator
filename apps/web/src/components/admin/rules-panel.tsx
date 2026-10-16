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
import { useSuggestRules } from "@/lib/admin/use-suggest-rules";
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
  const suggestRules = useSuggestRules();

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
            {/* Base UI's Select.Value shows the raw stored value unless given
                a children render-prop (unlike Radix) - was showing the
                literal "__all__" sentinel, and "active"/"suggested" instead
                of their capitalized labels. */}
            <SelectValue placeholder="Status">
              {(value: string) =>
                value === ALL
                  ? "All statuses"
                  : value === "active"
                    ? "Active"
                    : "Suggested"
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="suggested">Suggested</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            disabled={suggestRules.isPending}
            onClick={() => suggestRules.mutate()}
          >
            {suggestRules.isPending
              ? "Scanning corrections..."
              : "Suggest from corrections"}
          </Button>
          <Button onClick={openCreate}>New rule</Button>
        </div>
      </div>

      {suggestRules.isError && (
        <ErrorState message="Couldn't scan corrections for rule suggestions." />
      )}
      {suggestRules.isSuccess && (
        <p className="text-muted-foreground text-sm">
          {suggestRules.data.created.length === 0
            ? "No new patterns found."
            : `${suggestRules.data.created.length} new rule${
                suggestRules.data.created.length === 1 ? "" : "s"
              } suggested.`}
          {suggestRules.data.already_covered_count > 0 &&
            ` (${suggestRules.data.already_covered_count} pattern${
              suggestRules.data.already_covered_count === 1 ? "" : "s"
            } already covered by an existing rule.)`}
        </p>
      )}

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
