"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState } from "@/components/shared/error-state";
import { ElementTable } from "@/components/projects/element-table";
import { ExportButton } from "@/components/projects/export-button";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { ResultsOverview } from "@/components/projects/results-overview";
import { UploadDropzone } from "@/components/projects/upload-dropzone";
import { statusBadge } from "@/lib/projects/status-badge";
import { useProject } from "@/lib/projects/use-project";
import { useProjectFiles } from "@/lib/projects/use-project-files";

// WebGL/Three.js can't run server-side, and even client-side this shouldn't
// be in the initial bundle for a tab most sessions never open - dynamic
// import with ssr:false, per PROMPTS.md's 5.1 spec.
const Viewer3D = dynamic(
  () => import("@/components/projects/viewer-3d").then((m) => m.Viewer3D),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[600px] w-full rounded-lg" />,
  },
);

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);

  const { data: project, isLoading, isError, refetch } = useProject(projectId);
  const { data: files } = useProjectFiles(projectId);
  const [editOpen, setEditOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  // Lifted here (Phase 5.2) so selecting an element in the Elements table and
  // switching to 3D highlights it there, and clicking an element in 3D and
  // switching back opens it in the table - the two tabs are never visible at
  // once in this layout, so this is "sync across a tab switch," not a live
  // side-by-side highlight.
  const [selectedElementId, setSelectedElementId] = useState<number | null>(
    null,
  );
  const [sheetOpen, setSheetOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }
  if (isError || !project) {
    return (
      <ErrorState
        message="Couldn't load this project."
        onRetry={() => refetch()}
      />
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

      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value ?? "overview")}
      >
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
          <ElementTable
            projectId={projectId}
            selectedElementId={selectedElementId}
            onSelectElement={setSelectedElementId}
            sheetOpen={sheetOpen}
            onSheetOpenChange={setSheetOpen}
          />
        </TabsContent>

        <TabsContent value="3d" className="pt-4">
          {(() => {
            const readyFile = files?.find((f) => f.status === "extracted");
            if (!readyFile) {
              return (
                <p className="text-muted-foreground text-sm">
                  Upload and extract a file to see it here.
                </p>
              );
            }
            // Only actually mounted while this tab is the active one - a
            // hidden-but-mounted WebGL canvas would still hold a real context.
            return activeTab === "3d" ? (
              <Viewer3D
                projectId={projectId}
                fileId={readyFile.id}
                selectedElementId={selectedElementId}
                onSelectElement={(elementId) => {
                  setSelectedElementId(elementId);
                  setSheetOpen(true);
                  setActiveTab("elements");
                }}
              />
            ) : null;
          })()}
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
