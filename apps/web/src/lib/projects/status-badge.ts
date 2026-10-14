import type { VariantProps } from "class-variance-authority";

import type { badgeVariants } from "@/components/ui/badge";

type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

// Both project.status and an uploaded file's status are free-form strings set
// by the backend (see CLAUDE.md's core data model) - this maps the values each
// one actually uses today to a variant/label, with an honest fallback for
// anything else so a future new status never renders blank or throws.
const KNOWN_STATUSES: Record<string, { label: string; variant: BadgeVariant }> =
  {
    draft: { label: "Draft", variant: "secondary" },
    uploaded: { label: "Uploaded", variant: "secondary" },
    extracting: { label: "Extracting", variant: "default" },
    extracted: { label: "Extracted", variant: "outline" },
    failed: { label: "Failed", variant: "destructive" },
  };

export function statusBadge(status: string): {
  label: string;
  variant: BadgeVariant;
} {
  return (
    KNOWN_STATUSES[status] ?? {
      label: status.charAt(0).toUpperCase() + status.slice(1),
      variant: "secondary",
    }
  );
}
