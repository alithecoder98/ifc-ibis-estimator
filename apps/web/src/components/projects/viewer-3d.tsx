"use client";

import * as OBC from "@thatopen/components";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { useFragmentIdMap } from "@/lib/projects/use-fragment-id-map";
import { useFragmentModel } from "@/lib/projects/use-fragment-model";
import { useProjectElements } from "@/lib/projects/use-project-elements";

const ALL = "__all__";

type Engine = {
  components: OBC.Components;
  world: OBC.SimpleWorld<
    OBC.SimpleScene,
    OBC.OrthoPerspectiveCamera,
    OBC.SimpleRenderer
  >;
  hider: OBC.Hider;
  clipper: OBC.Clipper;
  modelId: string;
};

// Loaded only while the 3D tab is actually the active one (see
// projects/[id]/page.tsx) - mounting this spins up a real WebGL context, and
// browsers only allow a handful of those at once.
export function Viewer3D({
  projectId,
  fileId,
}: {
  projectId: number;
  fileId: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<Engine | null>(null);
  const [engineReady, setEngineReady] = useState(false);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [clippingEnabled, setClippingEnabled] = useState(false);
  const [storeyFilter, setStoreyFilter] = useState(ALL);

  const model = useFragmentModel(projectId, fileId);
  const idMap = useFragmentIdMap(projectId, fileId);
  const { data: elements } = useProjectElements(projectId);

  const storeys = useMemo(
    () =>
      [
        ...new Set((elements ?? []).map((e) => e.storey).filter(Boolean)),
      ] as string[],
    [elements],
  );

  // Set up the engine once per file. Three.js/WebGL can't run on the server,
  // and this component is only ever dynamically imported with ssr:false, but
  // the engine itself still needs its own explicit mount/dispose cycle tied
  // to this component's lifetime - unmounting (switching tabs away) must
  // free the WebGL context, not just stop referencing it.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const components = new OBC.Components();
    const worlds = components.get(OBC.Worlds);
    const world = worlds.create<
      OBC.SimpleScene,
      OBC.OrthoPerspectiveCamera,
      OBC.SimpleRenderer
    >();
    world.scene = new OBC.SimpleScene(components);
    world.renderer = new OBC.SimpleRenderer(components, container);
    world.camera = new OBC.OrthoPerspectiveCamera(components);
    world.scene.setup();
    components.init();

    const hider = components.get(OBC.Hider);
    const clipper = components.get(OBC.Clipper);

    engineRef.current = {
      components,
      world,
      hider,
      clipper,
      modelId: `file-${fileId}`,
    };
    setEngineReady(true);

    return () => {
      setEngineReady(false);
      setModelLoaded(false);
      components.dispose();
      engineRef.current = null;
    };
  }, [fileId]);

  // Load the fragments binary into the engine once both are ready.
  useEffect(() => {
    const engine = engineRef.current;
    if (!engineReady || !engine || !model.data) return;
    let cancelled = false;

    async function load() {
      if (!engine) return;
      try {
        const fragments = engine.components.get(OBC.FragmentsManager);
        if (!fragments.initialized) {
          fragments.init(await OBC.FragmentsManager.getWorker());
        }
        const loaded = await fragments.core.load(model.data as ArrayBuffer, {
          modelId: engine.modelId,
          camera: engine.world.camera.three,
        });
        if (cancelled) return;
        // Without this, fragments renders with frustum culling disabled and
        // nothing becomes visible - confirmed live via a real console warning
        // ("model ... is being rendered before useCamera() has been called")
        // that a blank canvas alone never surfaced.
        loaded.useCamera(engine.world.camera.three);
        engine.world.scene.three.add(loaded.object);
        await fragments.core.update(true);
        if (cancelled) return;
        await engine.world.camera.fit(engine.world.meshes);
        setModelLoaded(true);
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Couldn't load the 3D model",
          );
        }
      }
    }
    load();

    return () => {
      cancelled = true;
    };
  }, [engineReady, model.data]);

  function handleFit() {
    const engine = engineRef.current;
    if (engine) engine.world.camera.fit(engine.world.meshes);
  }

  function handleToggleClipping() {
    const engine = engineRef.current;
    if (!engine) return;
    const next = !clippingEnabled;
    engine.clipper.enabled = next;
    setClippingEnabled(next);
  }

  function handleClearClipping() {
    engineRef.current?.clipper.deleteAll();
  }

  async function applyStoreyFilter(storey: string) {
    const engine = engineRef.current;
    const map = idMap.data;
    if (!engine || !map || !elements) return;

    if (storey === ALL) {
      await engine.hider.set(true);
      return;
    }
    const localIds = elements
      .filter((e) => e.storey === storey)
      .map((e) => map[e.global_id])
      .filter((id): id is number => id !== undefined);
    await engine.hider.isolate({ [engine.modelId]: new Set(localIds) });
  }

  const isLoading = model.isLoading || idMap.isLoading;
  const isError = model.isError || idMap.isError || loadError !== null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={handleFit}
          disabled={!modelLoaded}
        >
          Fit to model
        </Button>
        <Button
          size="sm"
          variant={clippingEnabled ? "default" : "outline"}
          onClick={handleToggleClipping}
          disabled={!modelLoaded}
        >
          Clipping (double-click to cut)
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleClearClipping}
          disabled={!modelLoaded}
        >
          Clear cuts
        </Button>
        <Select
          value={storeyFilter}
          onValueChange={(value) => {
            const next = value ?? ALL;
            setStoreyFilter(next);
            applyStoreyFilter(next);
          }}
        >
          <SelectTrigger size="sm" disabled={!modelLoaded}>
            <SelectValue placeholder="Storey" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All storeys</SelectItem>
            {storeys.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isError && (
        <ErrorState
          message={
            loadError ??
            "Couldn't load the 3D model - try re-extracting the file."
          }
        />
      )}
      {isLoading && !isError && (
        <Skeleton className="h-[600px] w-full rounded-lg" />
      )}

      <div
        ref={containerRef}
        className="h-[600px] w-full overflow-hidden rounded-lg border"
        style={{ display: isLoading || isError ? "none" : "block" }}
      />
    </div>
  );
}
