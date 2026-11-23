import { useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useRailStore } from "../../store/useRailStore";
import { useUiStore } from "../../store/useUiStore";
import { CameraController, SIZE_GROWTH, markerScale, zoomTier, type Insets } from "../../utils/camera";
import { hourFromIso, tintCss } from "../../utils/daylight";
import { ignoreShortcut } from "../../utils/keys";
import { placeLabels } from "../../utils/labelPlacement";
import { computeLayoutForAspect, type MapLayout } from "../../utils/layout";
import { ConflictLayer } from "./ConflictLayer";
import { MapDefs, MapGrid } from "./MapDefs";
import { MapLegend } from "./MapLegend";
import { MapToolbar } from "./MapToolbar";
import { Minimap } from "./Minimap";
import { StationLayer } from "./StationLayer";
import { TrackLayer } from "./TrackLayer";
import { TrainTooltip } from "./TrainTooltip";
import { TrainsLayer, type HoverInfo } from "./TrainsLayer";
import { WeatherLayer } from "./WeatherLayer";

/** Screen px kept free for the floating KPI chips (top) and the legend / minimap row (bottom). */
const INSETS: Insets = { top: 108, right: 72, bottom: 104, left: 40 };
/** Pointer moves shorter than this are clicks, not drags. */
const DRAG_THRESHOLD_PX = 4;

/**
 * Width : height of the map area, estimated from the window (not the element) so that opening a
 * side panel never re-lays-out the map. Rounded to steps of 0.25 so a window resize rarely changes it.
 */
function useCanvasAspect(): number {
  const [aspect, setAspect] = useState(() => estimateAspect());
  useEffect(() => {
    const onResize = () => setAspect(estimateAspect());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return aspect;
}

function estimateAspect(): number {
  const wide = window.innerWidth >= 1600; // the alerts panel starts open on wide screens
  const w = window.innerWidth - (wide ? 350 : 90) - INSETS.left - INSETS.right;
  const h = window.innerHeight - 90 - INSETS.top - INSETS.bottom;
  if (h <= 0 || w <= 0) return 2;
  return Math.min(2.75, Math.max(1.25, Math.round((w / h) * 4) / 4));
}

/** The corridor as a pannable, zoomable SVG schematic with live trains and overlays. */
export function NetworkMap() {
  const network = useRailStore((s) => s.network);
  const snapshot = useRailStore((s) => s.snapshot);
  const aspect = useCanvasAspect();
  const layout = useMemo(() => (network ? computeLayoutForAspect(network, aspect) : null), [network, aspect]);

  if (!layout || !snapshot) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-body text-muted" role="status">
        <Loader2 className="h-4 w-4 animate-spin" /> Connecting to the control centre...
      </div>
    );
  }
  return <MapCanvas layout={layout} />;
}

function MapCanvas({ layout }: { layout: MapLayout }) {
  const snapshot = useRailStore((s) => s.snapshot);
  const reduced = useReducedMotion() ?? false;
  const reducedRef = useRef(reduced);
  reducedRef.current = reduced;

  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const world = useRef<SVGGElement>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  // zoom tier and a coarse zoom step: labels are re-placed only when one of them changes
  const [view, setView] = useState({ tier: 1 as 1 | 2 | 3, step: 0 });

  const controller = useMemo(
    () => new CameraController({ minX: 0, minY: 0, maxX: layout.width, maxY: layout.height }, INSETS),
    [layout],
  );

  // camera -> DOM, without React: world transform, marker scale, and the label detail level
  useEffect(
    () =>
      controller.subscribe((cam, size, fitK) => {
        if (!world.current || !svg.current) return;
        world.current.setAttribute("transform", `translate(${cam.x.toFixed(2)} ${cam.y.toFixed(2)}) scale(${cam.k.toFixed(5)})`);
        svg.current.style.setProperty("--ms", markerScale(cam.k, fitK).toFixed(5));
        if (size.w > 0) svg.current.style.visibility = "visible";
        const tier = zoomTier(cam.k / fitK);
        const step = Math.round(Math.log(cam.k) / Math.log(1.15));
        setView((v) => (v.tier === tier && v.step === step ? v : { tier, step }));
      }),
    [controller],
  );

  // container size -> camera
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const apply = () => controller.setSize({ w: el.clientWidth, h: el.clientHeight });
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [controller]);

  // easing loop; reduced motion jumps instead of gliding
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const frame = (now: number) => {
      controller.tick((now - last) / 1000, reducedRef.current);
      last = now;
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [controller]);

  // wheel zoom needs a non-passive listener so the page does not scroll
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      const speed = e.ctrlKey ? 0.01 : 0.0016; // pinch on a trackpad arrives as ctrl + wheel
      controller.zoomBy(Math.exp(-px * speed), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [controller]);

  // keyboard: + / - zoom, 0 or F fits
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (ignoreShortcut(e) || useUiStore.getState().tab !== "map") return;
      if (e.key === "+" || e.key === "=") controller.zoomBy(1.4);
      else if (e.key === "-" || e.key === "_") controller.zoomBy(1 / 1.4);
      else if (e.key === "0" || e.key.toLowerCase() === "f") controller.fit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [controller]);

  // drag to pan; a click on a train stays a click unless the pointer really moved
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) < DRAG_THRESHOLD_PX) return;
    if (!d.moved) {
      d.moved = true;
      setHover(null);
      e.currentTarget.setPointerCapture(e.pointerId);
      if (box.current) box.current.style.cursor = "grabbing";
    }
    controller.panBy(e.clientX - d.x, e.clientY - d.y);
    d.x = e.clientX;
    d.y = e.clientY;
  };
  const endDrag = () => {
    if (drag.current?.moved) suppressClick.current = true;
    drag.current = null;
    if (box.current) box.current.style.cursor = "";
  };

  const labels = useMemo(
    () => placeLabels(layout, controller.cam.k, view.tier, Math.pow(controller.rel, SIZE_GROWTH)),
    [layout, controller, view],
  );
  const reverse = useMemo(
    () => new Map((snapshot?.trains ?? []).filter((t) => t.position?.block_id && t.position.direction === "rev").map((t) => [t.position?.block_id as string, true])),
    [snapshot?.trains],
  );

  if (!snapshot) return null;
  const hovered = hover ? snapshot.trains.find((t) => t.id === hover.id) : undefined;
  const rect = box.current?.getBoundingClientRect();
  const hour = hourFromIso(snapshot.sim_time);

  return (
    <div
      ref={box}
      className="relative h-full w-full touch-none select-none overflow-hidden"
      style={{ background: "radial-gradient(120% 90% at 50% 42%, #111c29 0%, #0a1119 55%, #070b10 100%)" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onClickCapture={(e) => {
        if (suppressClick.current) {
          e.stopPropagation();
          suppressClick.current = false;
        }
      }}
    >
      {/* day / night wash; it fades slowly as the simulated clock moves */}
      <div
        className="pointer-events-none absolute inset-0 transition-[background-color] duration-[1500ms]"
        style={{ backgroundColor: tintCss(hour) }}
        data-testid="daylight"
        aria-hidden="true"
      />
      <svg
        ref={svg}
        className="absolute inset-0 h-full w-full"
        style={{ visibility: "hidden", cursor: "grab" }}
        role="img"
        aria-label="Schematic map of the rail corridor with live train positions"
      >
        <MapDefs />
        <g ref={world}>
          <MapGrid />
          <TrackLayer layout={layout} blocks={snapshot.blocks} disruptions={snapshot.disruptions} reverse={reverse} />
          <WeatherLayer layout={layout} disruptions={snapshot.disruptions} />
          <StationLayer layout={layout} labels={labels} />
          <ConflictLayer layout={layout} conflicts={snapshot.conflicts} />
          <TrainsLayer layout={layout} trains={snapshot.trains} tick={snapshot.tick} controller={controller} onHover={setHover} />
        </g>
      </svg>
      {/* vignette keeps the eye on the centre and the overlays readable at the edges */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse at 50% 50%, transparent 55%, rgb(3 6 10 / 0.55) 100%)" }}
        aria-hidden="true"
      />
      {hovered && hover && rect && <TrainTooltip train={hovered} x={hover.clientX - rect.left} y={hover.clientY - rect.top} />}

      <div className="pointer-events-none absolute inset-x-3 bottom-3 flex items-end justify-between gap-3">
        <div className="pointer-events-auto min-w-0 max-w-[calc(100%-13rem)]">
          <MapLegend />
        </div>
        <div className="pointer-events-auto shrink-0">
          <Minimap layout={layout} controller={controller} trains={snapshot.trains} conflicts={snapshot.conflicts} />
        </div>
      </div>
      <div className="absolute right-3 top-1/2 -translate-y-1/2">
        <MapToolbar controller={controller} />
      </div>
    </div>
  );
}
