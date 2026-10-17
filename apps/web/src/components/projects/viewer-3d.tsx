"use client";

import * as OBC from "@thatopen/components";
import { RenderedFaces } from "@thatopen/fragments";
import type * as FRAGS from "@thatopen/fragments";
import { Minus, Plus, Ruler } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

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

const SELECTED_MATERIAL: FRAGS.MaterialDefinition = {
  color: new THREE.Color("#4f46e5"), // indigo-600, matches the app's primary
  renderedFaces: RenderedFaces.TWO, // highlight visible from both sides
  opacity: 1,
  transparent: false,
};

type Engine = {
  components: OBC.Components;
  world: OBC.SimpleWorld<
    OBC.SimpleScene,
    OBC.OrthoPerspectiveCamera,
    OBC.SimpleRenderer
  >;
  hider: OBC.Hider;
  clipper: OBC.Clipper;
  fragments: OBC.FragmentsManager;
  modelId: string;
};

// Loaded only while the 3D tab is actually the active one (see
// projects/[id]/page.tsx) - mounting this spins up a real WebGL context, and
// browsers only allow a handful of those at once.
export function Viewer3D({
  projectId,
  fileId,
  selectedElementId,
  onSelectElement,
}: {
  projectId: number;
  fileId: number;
  // Lifted to the parent page (Phase 5.2) so selecting an element in the
  // Elements table highlights it here when you switch to the 3D tab, and
  // clicking an element in 3D opens it in the Elements table when you switch
  // back - the two tabs are never visible at once in this app's layout, so
  // "sync" means the shared selection survives the tab switch, not a live
  // side-by-side highlight.
  selectedElementId?: number | null;
  onSelectElement?: (elementId: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<Engine | null>(null);
  const highlightedLocalIdsRef = useRef<Set<number>>(new Set());
  const [engineReady, setEngineReady] = useState(false);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [clippingEnabled, setClippingEnabled] = useState(false);
  const [storeyFilter, setStoreyFilter] = useState(ALL);
  const [classFilter, setClassFilter] = useState(ALL);
  const [wireframeEnabled, setWireframeEnabled] = useState(false);
  const [measureMode, setMeasureMode] = useState(false);
  const [measureDistance, setMeasureDistance] = useState<number | null>(null);
  const measurePointsRef = useRef<THREE.Vector3[]>([]);

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
  const ifcClasses = useMemo(
    () => [...new Set((elements ?? []).map((e) => e.ifc_class))],
    [elements],
  );

  // idMap.data is {global_id: local_id} - selection sync and click-to-select
  // both need the reverse direction too (local_id -> element), built once per
  // map/elements change rather than scanning on every click.
  const localIdToElementId = useMemo(() => {
    const map = new Map<number, number>();
    if (!idMap.data || !elements) return map;
    const globalIdToElementId = new Map(
      elements.map((e) => [e.global_id, e.id]),
    );
    for (const [globalId, localId] of Object.entries(idMap.data)) {
      const elementId = globalIdToElementId.get(globalId);
      if (elementId !== undefined) map.set(localId, elementId);
    }
    return map;
  }, [idMap.data, elements]);

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
    const fragments = components.get(OBC.FragmentsManager);

    engineRef.current = {
      components,
      world,
      hider,
      clipper,
      fragments,
      modelId: `file-${fileId}`,
    };
    setEngineReady(true);

    return () => {
      setEngineReady(false);
      setModelLoaded(false);
      components.dispose();
      engineRef.current = null;
      highlightedLocalIdsRef.current = new Set();
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
        if (!engine.fragments.initialized) {
          engine.fragments.init(await OBC.FragmentsManager.getWorker());
        }
        const loaded = await engine.fragments.core.load(
          model.data as ArrayBuffer,
          { modelId: engine.modelId, camera: engine.world.camera.three },
        );
        if (cancelled) return;
        // Without this, fragments renders with frustum culling disabled and
        // nothing becomes visible - confirmed live via a real console warning
        // ("model ... is being rendered before useCamera() has been called")
        // that a blank canvas alone never surfaced.
        loaded.useCamera(engine.world.camera.three);
        engine.world.scene.three.add(loaded.object);
        await engine.fragments.core.update(true);
        if (cancelled) return;
        // world.meshes is a separate bookkeeping Set nothing here ever
        // populates - camera.fit(world.meshes) silently no-ops on an empty
        // Set, which is why the model used to load tiny and off-center with
        // every zoom/pan looking like it "didn't work." fitToItems() with no
        // argument fits every model FragmentsManager has loaded instead - the
        // same method the selection-sync effect below already uses correctly.
        await engine.world.camera.fitToItems();
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

  // Selection sync (Phase 5.2): when the shared selection changes (e.g. the
  // Elements table set it before this tab became active), highlight that one
  // element and fit the camera to it. Clears the previous highlight first -
  // FragmentsManager.resetHighlight() only clears what you pass it.
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || !modelLoaded) return;

    async function syncSelection() {
      if (!engine) return;
      if (highlightedLocalIdsRef.current.size > 0) {
        await engine.fragments.resetHighlight({
          [engine.modelId]: highlightedLocalIdsRef.current,
        });
        highlightedLocalIdsRef.current = new Set();
      }
      if (selectedElementId === null || selectedElementId === undefined) {
        return;
      }
      const element = elements?.find((e) => e.id === selectedElementId);
      const localId = element ? idMap.data?.[element.global_id] : undefined;
      if (localId === undefined) return;

      const items = { [engine.modelId]: new Set([localId]) };
      await engine.fragments.highlight(SELECTED_MATERIAL, items);
      highlightedLocalIdsRef.current = new Set([localId]);
      await engine.world.camera.fitToItems(items);
    }
    syncSelection();
  }, [selectedElementId, modelLoaded, elements, idMap.data]);

  function handleFit() {
    const engine = engineRef.current;
    // See the load effect above - fitToItems() with no argument fits all
    // loaded models, unlike the old camera.fit(world.meshes) call which
    // always fit an empty Set and never actually moved the camera.
    if (engine) engine.world.camera.fitToItems();
  }

  function handleZoom(step: number) {
    const engine = engineRef.current;
    engine?.world.camera.controls.dolly(step, true);
  }

  // Clipping and Measure both repurpose the canvas's click/double-click
  // gestures, and nothing kept them mutually exclusive - confirmed live
  // (reported as "buttons not working properly"): with both toggled on, a
  // double-click's two leading click events still fed the measure-point
  // collector while the trailing dblclick simultaneously created a clipping
  // plane, racing each other on the same gesture. Turning one on now turns
  // the other off, same as a toolbar's exclusive tool selection.
  function handleToggleClipping() {
    const engine = engineRef.current;
    if (!engine) return;
    const next = !clippingEnabled;
    engine.clipper.enabled = next;
    setClippingEnabled(next);
    if (next) {
      setMeasureMode(false);
      setMeasureDistance(null);
      measurePointsRef.current = [];
    }
  }

  function handleClearClipping() {
    engineRef.current?.clipper.deleteAll();
  }

  function handleToggleWireframe() {
    const engine = engineRef.current;
    if (!engine) return;
    const next = !wireframeEnabled;
    engine.world.scene.three.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const materials = Array.isArray(object.material)
        ? object.material
        : [object.material];
      for (const material of materials) {
        if ("wireframe" in material) {
          (material as THREE.MeshBasicMaterial).wireframe = next;
        }
      }
    });
    setWireframeEnabled(next);
  }

  // Storey and IFC-class filters combine (intersect), not override each
  // other - an estimator narrowing to "Ground Floor" and then also to
  // "IfcWall" expects both to apply together, same as the Elements table's
  // own filters.
  async function applyVisibilityFilters(storey: string, ifcClass: string) {
    const engine = engineRef.current;
    const map = idMap.data;
    if (!engine || !map || !elements) return;

    if (storey === ALL && ifcClass === ALL) {
      await engine.hider.set(true);
      return;
    }
    const localIds = elements
      .filter(
        (e) =>
          (storey === ALL || e.storey === storey) &&
          (ifcClass === ALL || e.ifc_class === ifcClass),
      )
      .map((e) => map[e.global_id])
      .filter((id): id is number => id !== undefined);
    await engine.hider.isolate({ [engine.modelId]: new Set(localIds) });
  }

  // The "double-click to cut" label was a promise the code never kept -
  // Clipper never attaches its own dblclick listener (confirmed by reading
  // its source: setEvents() only wires onBeforeDelete and fragment-material
  // subscriptions), so enabling clipping previously just flipped an internal
  // flag with no visible effect. Clipper.create() reads the mouse position
  // Raycasters/Mouse already track automatically from real pointer events,
  // so this only needs to call it, not do any raycasting itself.
  async function handleCanvasDoubleClick() {
    const engine = engineRef.current;
    if (!engine || !clippingEnabled) return;
    await engine.clipper.create(engine.world);
  }

  function handleToggleMeasure() {
    const next = !measureMode;
    setMeasureMode(next);
    setMeasureDistance(null);
    measurePointsRef.current = [];
    if (next && clippingEnabled) {
      const engine = engineRef.current;
      if (engine) engine.clipper.enabled = false;
      setClippingEnabled(false);
    }
  }

  // Click-to-select (Phase 5.2) and click-to-measure share the same
  // raycast - which behavior fires depends on whether measure mode is on.
  async function handleCanvasClick(event: React.MouseEvent<HTMLDivElement>) {
    const engine = engineRef.current;
    if (!engine || !modelLoaded || !engine.world.renderer) return;
    const canvas = engine.world.renderer.three.domElement;
    const rect = canvas.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    const result = await engine.fragments.raycast({
      camera: engine.world.camera.three,
      mouse,
      dom: canvas,
    });
    if (!result) return;

    if (measureMode) {
      const points = [...measurePointsRef.current, result.point];
      if (points.length < 2) {
        measurePointsRef.current = points;
        return;
      }
      setMeasureDistance(points[0].distanceTo(points[1]));
      measurePointsRef.current = [];
      return;
    }

    const elementId = localIdToElementId.get(result.localId);
    if (elementId !== undefined) onSelectElement?.(elementId);
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
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleZoom(5)}
            disabled={!modelLoaded}
            aria-label="Zoom in"
          >
            <Plus className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleZoom(-5)}
            disabled={!modelLoaded}
            aria-label="Zoom out"
          >
            <Minus className="size-4" />
          </Button>
        </div>
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
        <Button
          size="sm"
          variant={wireframeEnabled ? "default" : "outline"}
          onClick={handleToggleWireframe}
          disabled={!modelLoaded}
        >
          Wireframe
        </Button>
        <Button
          size="sm"
          variant={measureMode ? "default" : "outline"}
          onClick={handleToggleMeasure}
          disabled={!modelLoaded}
        >
          <Ruler className="mr-1 size-4" />
          {measureMode ? "Click two points..." : "Measure"}
        </Button>
        <Select
          value={storeyFilter}
          onValueChange={(value) => {
            const next = value ?? ALL;
            setStoreyFilter(next);
            applyVisibilityFilters(next, classFilter);
          }}
        >
          <SelectTrigger size="sm" disabled={!modelLoaded}>
            {/* Base UI's Select.Value shows the raw stored value unless
                given a children render-prop (unlike Radix) - was showing
                the literal "__all__" sentinel instead of "All storeys". */}
            <SelectValue placeholder="Storey">
              {(value: string) => (value === ALL ? "All storeys" : value)}
            </SelectValue>
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
        <Select
          value={classFilter}
          onValueChange={(value) => {
            const next = value ?? ALL;
            setClassFilter(next);
            applyVisibilityFilters(storeyFilter, next);
          }}
        >
          <SelectTrigger size="sm" disabled={!modelLoaded}>
            <SelectValue placeholder="IFC class">
              {(value: string) => (value === ALL ? "All classes" : value)}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All classes</SelectItem>
            {ifcClasses.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {measureDistance !== null && (
          <span className="bg-accent text-accent-foreground rounded-md px-2 py-1 text-sm font-medium tabular-nums">
            {measureDistance.toFixed(3)} m
          </span>
        )}
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
        onClick={handleCanvasClick}
        onDoubleClick={handleCanvasDoubleClick}
        className="h-[600px] w-full overflow-hidden rounded-lg border"
        style={{
          display: isLoading || isError ? "none" : "block",
          cursor: measureMode ? "crosshair" : undefined,
        }}
      />
    </div>
  );
}
