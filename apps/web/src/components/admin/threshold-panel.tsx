"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useThreshold } from "@/lib/admin/use-threshold";
import { useUpdateThreshold } from "@/lib/admin/use-update-threshold";

export function ThresholdPanel() {
  const { data, isLoading, isError } = useThreshold();
  const update = useUpdateThreshold();
  const [value, setValue] = useState("");

  // Only seed the field once the real value has loaded - an empty-string
  // default would otherwise flash before overwriting itself.
  useEffect(() => {
    if (data) setValue(String(data.auto_accept_threshold));
  }, [data]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return;
    update.mutate(parsed);
  }

  if (isLoading) {
    return <p className="text-muted-foreground text-sm">Loading...</p>;
  }
  if (isError) {
    return (
      <p className="text-sm text-red-600" role="alert">
        Couldn&apos;t load the threshold.
      </p>
    );
  }

  return (
    <Card className="max-w-sm">
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-medium">
            Auto-accept confidence threshold
          </h3>
          <p className="text-muted-foreground text-sm">
            Classifications scoring at or above this are auto-accepted;
            everything else goes to the review queue. Changes apply to the next
            classification run - no restart needed.{" "}
            <code className="text-xs">scripts/calibrate.py</code> picks a value
            against ground truth, once there is any.
          </p>
        </div>
        <form onSubmit={handleSubmit} className="flex items-end gap-2">
          <div className="space-y-2">
            <Label htmlFor="threshold">Threshold (0-1)</Label>
            <Input
              id="threshold"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className="w-28"
            />
          </div>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving..." : "Save"}
          </Button>
        </form>
        {update.isError && (
          <p className="text-sm text-red-600" role="alert">
            Couldn&apos;t save - value must be between 0 and 1.
          </p>
        )}
        {update.isSuccess && (
          <p className="text-sm text-green-700 dark:text-green-500">Saved.</p>
        )}
      </CardContent>
    </Card>
  );
}
