"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { CodePickerDialog } from "@/components/projects/code-picker-dialog";
import { statusBadge } from "@/lib/projects/status-badge";
import { useElementDetail } from "@/lib/projects/use-element-detail";
import { useReviewElement } from "@/lib/reviews/use-review-element";
import { useUndoReview } from "@/lib/reviews/use-undo-review";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
    </div>
  );
}

export function ElementDetailSheet({
  projectId,
  elementId,
  onOpenChange,
}: {
  projectId: number;
  elementId: number | null;
  onOpenChange: (open: boolean) => void;
}) {
  const {
    data: detail,
    isLoading,
    isError,
    refetch,
  } = useElementDetail(projectId, elementId);

  const [comment, setComment] = useState("");
  const [codePickerOpen, setCodePickerOpen] = useState(false);
  const reviewElement = useReviewElement(projectId, elementId ?? -1);
  const undoReview = useUndoReview(projectId);

  const handleApprove = useCallback(() => {
    reviewElement.mutate(
      { action: "approve", comment: comment || null },
      { onSuccess: () => setComment("") },
    );
  }, [reviewElement, comment]);

  function handleCorrect(code: { ibis_code: string }) {
    reviewElement.mutate(
      {
        action: "correct",
        ibis_code: code.ibis_code,
        comment: comment || null,
      },
      { onSuccess: () => setComment("") },
    );
  }

  const mostRecentReview = detail?.reviews.at(-1);

  // A approves, C opens the correction code picker - only while the sheet is
  // open and an element has loaded. Ignored while typing in an input/textarea
  // (including the code picker's own search box, since focus moves there)
  // so it doesn't fight with typing "a"/"c" as literal characters.
  useEffect(() => {
    if (elementId === null || !detail) return;

    function handleKeyDown(event: KeyboardEvent) {
      const key = event.key.toLowerCase();
      if (key !== "a" && key !== "c") return;

      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return;
      }

      // Without this, the same keypress that opens the code picker can leak
      // into its auto-focused search input (its autoFocus can land within the
      // same event's dispatch, so the browser's own default text-insertion
      // for this keydown fires against the now-focused input) - seen for
      // real: pressing "c" opened the picker with a literal "c" already
      // typed into the search box.
      event.preventDefault();

      if (key === "a") {
        handleApprove();
      } else {
        setCodePickerOpen(true);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [elementId, detail, handleApprove]);

  return (
    <Sheet open={elementId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>
            {detail?.name ?? detail?.global_id ?? "Element"}
          </SheetTitle>
          <SheetDescription>
            {detail?.ifc_class}
            {detail?.predefined_type ? ` / ${detail.predefined_type}` : ""}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-5 px-4 pb-4">
          {isLoading && (
            <div className="space-y-3">
              <Skeleton className="h-24 w-full rounded-md" />
              <Skeleton className="h-24 w-full rounded-md" />
              <Skeleton className="h-24 w-full rounded-md" />
            </div>
          )}
          {isError && (
            <ErrorState
              message="Couldn't load this element."
              onRetry={() => refetch()}
            />
          )}

          {detail && (
            <>
              <Section title="Properties">
                <dl className="grid grid-cols-2 gap-y-1 text-sm">
                  <dt className="text-muted-foreground">Global ID</dt>
                  <dd className="truncate" title={detail.global_id}>
                    {detail.global_id}
                  </dd>
                  <dt className="text-muted-foreground">Storey</dt>
                  <dd>{detail.storey ?? "-"}</dd>
                  <dt className="text-muted-foreground">Object type</dt>
                  <dd>{detail.object_type ?? "-"}</dd>
                  <dt className="text-muted-foreground">External</dt>
                  <dd>
                    {detail.is_external === null
                      ? "-"
                      : detail.is_external
                        ? "Yes"
                        : "No"}
                  </dd>
                  <dt className="text-muted-foreground">Load-bearing</dt>
                  <dd>
                    {detail.load_bearing === null
                      ? "-"
                      : detail.load_bearing
                        ? "Yes"
                        : "No"}
                  </dd>
                </dl>
                {detail.psets && Object.keys(detail.psets).length > 0 && (
                  <pre className="bg-muted mt-2 max-h-40 overflow-auto rounded-md p-2 text-xs">
                    {JSON.stringify(detail.psets, null, 2)}
                  </pre>
                )}
              </Section>

              <Separator />

              <Section title="Material layers">
                {detail.materials && detail.materials.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {detail.materials.map((material, index) => (
                      <li
                        key={index}
                        className="flex justify-between gap-2 rounded-md border px-2 py-1"
                      >
                        <span>
                          {((material as Record<string, unknown>).material as
                            string | undefined) ?? "Unknown material"}
                        </span>
                        {"thickness_mm" in material && (
                          <span className="text-muted-foreground">
                            {String(
                              (material as Record<string, unknown>)
                                .thickness_mm,
                            )}{" "}
                            mm
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No material data.
                  </p>
                )}
              </Section>

              <Separator />

              <Section title="Quantities">
                {detail.quantities.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {detail.quantities.map((quantity, index) => (
                      <li
                        key={index}
                        className="flex justify-between gap-2 rounded-md border px-2 py-1"
                      >
                        <span>{quantity.quantity_type}</span>
                        <span className="tabular-nums">
                          {quantity.value} {quantity.unit}
                        </span>
                        <Badge variant="outline">{quantity.source}</Badge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No quantity data.
                  </p>
                )}
              </Section>

              <Separator />

              <Section title="Classification">
                {detail.classification ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          statusBadge(detail.classification.status).variant
                        }
                      >
                        {statusBadge(detail.classification.status).label}
                      </Badge>
                      <Badge variant="outline">
                        {detail.classification.source}
                      </Badge>
                      {detail.classification.confidence !== null && (
                        <span className="text-muted-foreground">
                          confidence{" "}
                          {detail.classification.confidence.toFixed(2)}
                        </span>
                      )}
                    </div>
                    <div>
                      <span className="font-medium">
                        {detail.classification.ibis_code ?? "No code"}
                      </span>
                      {detail.classification.internal_element && (
                        <span className="text-muted-foreground">
                          {" "}
                          — {detail.classification.internal_element}
                        </span>
                      )}
                    </div>
                    {detail.classification.reasoning && (
                      <p className="text-muted-foreground">
                        {detail.classification.reasoning}
                      </p>
                    )}
                    {detail.classification.flags &&
                      detail.classification.flags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {detail.classification.flags.map((flag) => (
                            <Badge key={flag} variant="destructive">
                              {flag}
                            </Badge>
                          ))}
                        </div>
                      )}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    Not yet classified.
                  </p>
                )}
              </Section>

              <Separator />

              <Section title="Review">
                <Input
                  placeholder="Comment (optional)"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={
                      !detail.classification?.ibis_code ||
                      reviewElement.isPending
                    }
                    onClick={handleApprove}
                    title={
                      !detail.classification?.ibis_code
                        ? "Nothing to approve - this element has no suggested code yet"
                        : undefined
                    }
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={reviewElement.isPending}
                    onClick={() => setCodePickerOpen(true)}
                  >
                    Correct...
                  </Button>
                </div>
                {reviewElement.isError && (
                  <p className="text-sm text-red-600" role="alert">
                    Couldn&apos;t save - please try again.
                  </p>
                )}
                {reviewElement.isSuccess && (
                  <p className="text-sm text-green-700 dark:text-green-500">
                    Saved.
                  </p>
                )}
              </Section>

              <CodePickerDialog
                open={codePickerOpen}
                onOpenChange={setCodePickerOpen}
                candidates={detail.candidates}
                onSelect={handleCorrect}
              />

              <Separator />

              <Section title="Candidate codes">
                {detail.candidates.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {detail.candidates.map((candidate) => (
                      <li
                        key={candidate.ibis_code}
                        className="flex items-center justify-between gap-2 rounded-md border px-2 py-1"
                      >
                        <div className="truncate">
                          <span className="font-medium">
                            {candidate.ibis_code}
                          </span>{" "}
                          <span className="text-muted-foreground">
                            {candidate.internal_element}
                          </span>
                        </div>
                        <span className="tabular-nums">
                          {candidate.score.toFixed(3)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No candidates available.
                  </p>
                )}
              </Section>

              <Separator />

              <Section title="Similar past examples">
                {detail.similar_examples.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {detail.similar_examples.map((example, index) => (
                      <li key={index} className="rounded-md border px-2 py-1">
                        <div>
                          <span className="font-medium">
                            {example.final_ibis_code}
                          </span>{" "}
                          <span className="text-muted-foreground">
                            {example.final_internal_element}
                          </span>
                        </div>
                        <p className="text-muted-foreground truncate text-xs">
                          {example.profile_text}
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No similar examples yet.
                  </p>
                )}
              </Section>

              <Separator />

              <Section title="Review history">
                {undoReview.isError && (
                  <p className="text-sm text-red-600" role="alert">
                    Couldn&apos;t undo - please try again.
                  </p>
                )}
                {detail.reviews.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {detail.reviews.map((review) => (
                      <li
                        key={review.id}
                        className="rounded-md border px-2 py-1"
                      >
                        <div className="flex items-center justify-between">
                          <Badge variant="outline">{review.action}</Badge>
                          <span className="text-muted-foreground text-xs">
                            {review.user_email}
                          </span>
                        </div>
                        {review.comment && (
                          <p className="text-muted-foreground mt-1">
                            {review.comment}
                          </p>
                        )}
                        {review.id === mostRecentReview?.id &&
                          review.action !== "undo" && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="mt-1"
                              disabled={undoReview.isPending}
                              onClick={() => undoReview.mutate(review.id)}
                            >
                              Undo
                            </Button>
                          )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No reviews yet.
                  </p>
                )}
              </Section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
