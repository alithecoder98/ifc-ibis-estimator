"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ElementTable } from "@/components/projects/element-table";
import { ExportButton } from "@/components/projects/export-button";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { ResultsOverview } from "@/components/projects/results-overview";
import { UploadDropzone } from "@/components/projects/upload-dropzone";
import { statusBadge } from "@/lib/projects/status-badge";
import { useProject } from "@/lib/projects/use-project";
import { useProjectFiles } from "@/lib/projects/use-project-files";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);

  const { data: project, isLoading, isError } = useProject(projectId);
  const { data: files } = useProjectFiles(projectId);
  const [editOpen, setEditOpen] = useState(false);

  if (isLoading) return <p className="text-muted-foreground">Loading...</p>;
  if (isError || !project) {
    return (
      <p className="text-sm text-red-600" role="alert">
        Couldn&apos;t load this project.
      </p>
    );
  }

  const badge = statusBadge(project.status);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{project.name}</h1>
          <Badge variant={badge.variant}>{badge.label}</Badge>
        </div>
        <Button variant="outline" onClick={() => setEditOpen(true)}>
          Rename
        </Button>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="elements">Elements</TabsTrigger>
          <TabsTrigger value="3d">3D</TabsTrigger>
          <TabsTrigger value="export">Export</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 pt-4">
          <Card>
            <CardContent className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-muted-foreground">
                  Classification engine
                </div>
                <div>{project.classification_engine}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Created</div>
                <div>{new Date(project.created_at).toLocaleString()}</div>
              </div>
            </CardContent>
          </Card>

          <ResultsOverview projectId={projectId} />

          <UploadDropzone projectId={projectId} />

          <div className="space-y-2">
            <h2 className="text-sm font-medium">Files</h2>
            {files && files.length > 0 ? (
              files.map((file) => {
                const fileBadge = statusBadge(file.status);
                return (
                  <Card key={file.id}>
                    <CardContent className="flex items-center justify-between">
                      <span>{file.filename}</span>
                      <div className="flex items-center gap-4">
                        <span className="text-muted-foreground text-xs">
                          {new Date(file.uploaded_at).toLocaleString()}
                        </span>
                        <Badge variant={fileBadge.variant}>
                          {fileBadge.label}
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                );
              })
            ) : (
              <p className="text-muted-foreground text-sm">
                No file uploaded yet.
              </p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="elements" className="pt-4">
          <ElementTable projectId={projectId} />
        </TabsContent>

        <TabsContent value="3d" className="pt-4">
          <p className="text-muted-foreground text-sm">
            The 3D viewer arrives in Phase 5.
          </p>
        </TabsContent>

        <TabsContent value="export" className="pt-4">
          <ExportButton projectId={projectId} />
        </TabsContent>
      </Tabs>

      <ProjectDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        project={{ id: project.id, name: project.name }}
      />
    </div>
  );
}
