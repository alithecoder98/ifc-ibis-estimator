"use client";

import { ChevronRight, FolderKanban } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { statusBadge } from "@/lib/projects/status-badge";
import { useProjects } from "@/lib/projects/use-projects";

export default function ProjectsPage() {
  const router = useRouter();
  const { data: projects, isLoading, isError, refetch } = useProjects();
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);

  const filtered = (projects ?? []).filter((project) =>
    project.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Projects</h1>
        <Button onClick={() => setDialogOpen(true)}>New project</Button>
      </div>

      <Input
        placeholder="Search projects..."
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        className="max-w-sm"
      />

      {isLoading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      )}
      {isError && (
        <ErrorState
          message="Couldn't load projects."
          onRetry={() => refetch()}
        />
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <p className="text-muted-foreground">
          {projects && projects.length > 0
            ? "No projects match your search."
            : "No projects yet - create one to get started."}
        </p>
      )}

      <div className="space-y-2">
        {filtered.map((project) => {
          const badge = statusBadge(project.status);
          return (
            <Link key={project.id} href={`/projects/${project.id}`}>
              <Card className="hover:border-primary/40 transition-all hover:shadow-sm">
                <CardContent className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="bg-accent text-accent-foreground flex h-9 w-9 items-center justify-center rounded-lg">
                      <FolderKanban className="h-4.5 w-4.5" />
                    </div>
                    <span className="font-medium">{project.name}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-muted-foreground text-xs">
                      Updated{" "}
                      {new Date(project.updated_at).toLocaleDateString()}
                    </span>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                    <ChevronRight className="text-muted-foreground h-4 w-4" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <ProjectDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSaved={(projectId) => router.push(`/projects/${projectId}`)}
      />
    </div>
  );
}
