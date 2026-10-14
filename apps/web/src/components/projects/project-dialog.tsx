"use client";

import { type FormEvent, useEffect, useState } from "react";

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
import { useCreateProject } from "@/lib/projects/use-create-project";
import { useUpdateProject } from "@/lib/projects/use-update-project";

// Shared create/edit form: editing a project today only means renaming it (the
// other editable field, classification_engine, is an AI/infra setting that
// belongs in the admin area per CLAUDE.md's Phase 4.6, not this dialog).
export function ProjectDialog({
  open,
  onOpenChange,
  project,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project?: { id: number; name: string };
  onSaved?: (projectId: number) => void;
}) {
  const [name, setName] = useState(project?.name ?? "");
  const createProject = useCreateProject();
  const updateProject = useUpdateProject(project?.id ?? -1);
  const isEditing = project !== undefined;
  const mutation = isEditing ? updateProject : createProject;

  // Reset the field to the current project's name (or blank, for create) every
  // time the dialog opens - otherwise a second "New Project" open would still
  // show whatever was typed (or left over from editing) last time.
  useEffect(() => {
    if (open) setName(project?.name ?? "");
  }, [open, project]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate(
      { name },
      {
        onSuccess: (saved) => {
          onOpenChange(false);
          if (saved) onSaved?.(saved.id);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Rename project" : "New project"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              required
            />
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
