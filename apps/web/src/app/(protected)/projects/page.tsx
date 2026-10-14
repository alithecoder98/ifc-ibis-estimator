"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { statusBadge } from "@/lib/projects/status-badge";
import { useProjects } from "@/lib/projects/use-projects";

export default function ProjectsPage() {
  const { data: projects, isLoading, isError } = useProjects();
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

      {isLoading && <p className="text-muted-foreground">Loading...</p>}
      {isError && (
        <p className="text-sm text-red-600" role="alert">
          Couldn&apos;t load projects. Try refreshing the page.
        </p>
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
              <Card className="hover:bg-muted/50 transition-colors">
                <CardContent className="flex items-center justify-between">
                  <span className="font-medium">{project.name}</span>
                  <div className="flex items-center gap-4">
                    <span className="text-muted-foreground text-xs">
                      Updated{" "}
                      {new Date(project.updated_at).toLocaleDateString()}
                    </span>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <ProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
