"use client";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { statusBadge } from "@/lib/projects/status-badge";
import { useElementDetail } from "@/lib/projects/use-element-detail";

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
  } = useElementDetail(projectId, elementId);

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
            <p className="text-muted-foreground text-sm">Loading...</p>
          )}
          {isError && (
            <p className="text-sm text-red-600" role="alert">
              Couldn&apos;t load this element.
            </p>
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
                {detail.reviews.length > 0 ? (
                  <ul className="space-y-1 text-sm">
                    {detail.reviews.map((review, index) => (
                      <li key={index} className="rounded-md border px-2 py-1">
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
