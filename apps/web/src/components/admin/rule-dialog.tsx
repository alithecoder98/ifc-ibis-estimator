"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateRule } from "@/lib/admin/use-create-rule";
import { useUpdateRule } from "@/lib/admin/use-update-rule";
import type { components } from "@/lib/api/schema";

type RuleCondition = components["schemas"]["RuleCondition"];
type RuleOut = components["schemas"]["RuleOut"];

const FIELDS: RuleCondition["field"][] = [
  "ifc_class",
  "predefined_type",
  "material_keyword",
  "thickness_mm",
  "is_external",
  "load_bearing",
  "storey_keyword",
];
const OPERATORS: RuleCondition["operator"][] = ["==", "contains", "between"];
const BOOLEAN_FIELDS = new Set(["is_external", "load_bearing"]);

// A condition's `value` is typed `Any` on the backend - this form keeps every
// value as plain text while editing and only parses it into bool/number/[min,
// max] on submit, based on the field/operator chosen. Simpler than a different
// input widget per field for what's an internal admin tool, not end-user UI.
type DraftCondition = {
  field: RuleCondition["field"];
  operator: RuleCondition["operator"];
  value: string;
};

function parseValue(condition: DraftCondition): unknown {
  if (condition.operator === "between") {
    return condition.value.split(",").map((part) => Number(part.trim()));
  }
  if (BOOLEAN_FIELDS.has(condition.field)) {
    return condition.value.trim().toLowerCase() === "true";
  }
  if (condition.field === "thickness_mm") {
    return Number(condition.value);
  }
  return condition.value;
}

function conditionsToDraft(
  conditions: { field: string; operator: string; value: unknown }[],
): DraftCondition[] {
  return conditions.map((c) => ({
    field: c.field as RuleCondition["field"],
    operator: c.operator as RuleCondition["operator"],
    value: Array.isArray(c.value) ? c.value.join(", ") : String(c.value),
  }));
}

export function RuleDialog({
  open,
  onOpenChange,
  rule,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rule?: RuleOut;
}) {
  const isEditing = rule !== undefined;
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const mutation = isEditing ? updateRule : createRule;

  const [resultIbisCode, setResultIbisCode] = useState("");
  const [resultInternalElement, setResultInternalElement] = useState("");
  const [priority, setPriority] = useState("0");
  const [status, setStatus] = useState<"suggested" | "active">("active");
  const [conditions, setConditions] = useState<DraftCondition[]>([
    { field: "ifc_class", operator: "==", value: "" },
  ]);

  useEffect(() => {
    if (!open) return;
    setResultIbisCode(rule?.result_ibis_code ?? "");
    setResultInternalElement(rule?.result_internal_element ?? "");
    setPriority(String(rule?.priority ?? 0));
    setStatus((rule?.status as "suggested" | "active") ?? "active");
    setConditions(
      rule && rule.conditions.length > 0
        ? conditionsToDraft(
            rule.conditions as {
              field: string;
              operator: string;
              value: unknown;
            }[],
          )
        : [{ field: "ifc_class", operator: "==", value: "" }],
    );
  }, [open, rule]);

  function updateCondition(index: number, patch: Partial<DraftCondition>) {
    setConditions((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const body = {
      conditions: conditions.map((c) => ({
        field: c.field,
        operator: c.operator,
        value: parseValue(c),
      })),
      result_ibis_code: resultIbisCode,
      result_internal_element: resultInternalElement,
      priority: Number(priority),
      status,
    };

    if (isEditing) {
      updateRule.mutate(
        { id: rule.id, body },
        { onSuccess: () => onOpenChange(false) },
      );
    } else {
      createRule.mutate(body, { onSuccess: () => onOpenChange(false) });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Edit rule" : "New rule"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Conditions (all must match)</Label>
            <div className="space-y-2">
              {conditions.map((condition, index) => (
                <div key={index} className="flex items-center gap-1">
                  <Select
                    value={condition.field}
                    onValueChange={(v) =>
                      v &&
                      updateCondition(index, {
                        field: v as RuleCondition["field"],
                      })
                    }
                  >
                    <SelectTrigger size="sm" className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FIELDS.map((f) => (
                        <SelectItem key={f} value={f}>
                          {f}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={condition.operator}
                    onValueChange={(v) =>
                      v &&
                      updateCondition(index, {
                        operator: v as RuleCondition["operator"],
                      })
                    }
                  >
                    <SelectTrigger size="sm" className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {OPERATORS.map((op) => (
                        <SelectItem key={op} value={op}>
                          {op}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    value={condition.value}
                    onChange={(event) =>
                      updateCondition(index, { value: event.target.value })
                    }
                    placeholder={
                      condition.operator === "between"
                        ? "min, max"
                        : BOOLEAN_FIELDS.has(condition.field)
                          ? "true / false"
                          : "value"
                    }
                    className="flex-1"
                    required
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={conditions.length === 1}
                    onClick={() =>
                      setConditions((prev) =>
                        prev.filter((_, i) => i !== index),
                      )
                    }
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setConditions((prev) => [
                  ...prev,
                  { field: "ifc_class", operator: "==", value: "" },
                ])
              }
            >
              Add condition
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="result-ibis-code">Result IBIS code</Label>
              <Input
                id="result-ibis-code"
                value={resultIbisCode}
                onChange={(event) => setResultIbisCode(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="priority">Priority</Label>
              <Input
                id="priority"
                type="number"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="result-internal-element">
              Result internal element
            </Label>
            <Input
              id="result-internal-element"
              value={resultInternalElement}
              onChange={(event) => setResultInternalElement(event.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Status</Label>
            <Select
              value={status}
              onValueChange={(v) => v && setStatus(v as "suggested" | "active")}
            >
              <SelectTrigger size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="suggested">Suggested</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {mutation.isError && (
            <p className="text-sm text-red-600" role="alert">
              Something went wrong - please try again.
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
