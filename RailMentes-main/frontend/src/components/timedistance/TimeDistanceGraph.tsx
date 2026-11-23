import { Crosshair, History, Maximize, Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useHistoryStore } from "../../store/useHistoryStore";
import { useRailStore } from "../../store/useRailStore";
import { DELAY_COLORS, DELAY_LABELS, formatDelay, type DelayLevel } from "../../utils/delay";
import { CATEGORY_LABELS } from "../../utils/labels";
import { CATEGORY_COLORS } from "../../utils/timeDistance";
import { cn } from "../../utils/cn";
import { Button } from "../ui/button";
import { createGraph, type ColorMode, type GraphController } from "./graph";

const MODES: { id: ColorMode; label: string }[] = [
  { id: "type", label: "Train type" },
  { id: "delay", label: "Delay" },
];

function LineKey({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}>{children}</span>;
}

/** Legend: line styles, shaded areas, colour key for the chosen mode and the offset-lane note. */
function Legend({ mode }: { mode: ColorMode }) {
  const swatch = (color: string, label: string) => (
    <LineKey key={label}>
      <span className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden="true" />
      {label}
    </LineKey>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-muted" aria-label="Legend">
      <LineKey>
        <svg width="26" height="8" aria-hidden="true">
          <line x1="0" x2="26" y1="4" y2="4" stroke="#dbe4ee" strokeOpacity="0.3" />
        </svg>
        Planned
      </LineKey>
      <LineKey>
        <svg width="26" height="8" aria-hidden="true">
          <line x1="0" x2="26" y1="4" y2="4" stroke="#dbe4ee" strokeWidth="2.4" />
        </svg>
        Actual
      </LineKey>
      <LineKey>
        <svg width="26" height="8" aria-hidden="true">
          <line x1="0" x2="26" y1="4" y2="4" stroke="#dbe4ee" strokeWidth="2" strokeDasharray="6 4" />
        </svg>
        Predicted
      </LineKey>
      <LineKey>
        <span className="h-3 w-4 rounded-sm border border-dashed border-crit/80 bg-crit/30" aria-hidden="true" />
        Conflict
      </LineKey>
      <LineKey>
        <span className="h-3 w-4 rounded-sm bg-slate-400/25" aria-hidden="true" />
        Fog / slowdown
      </LineKey>
      <LineKey>
        <span
          className="h-3 w-4 rounded-sm"
          style={{ backgroundImage: "repeating-linear-gradient(45deg,#f0443899 0 2px,transparent 2px 5px)" }}
          aria-hidden="true"
        />
        Closed block
      </LineKey>
      <span className="hidden h-3 w-px bg-white/10 lg:inline-block" aria-hidden="true" />
      {mode === "type"
        ? Object.entries(CATEGORY_COLORS).map(([cat, color]) => swatch(color, CATEGORY_LABELS[cat as keyof typeof CATEGORY_LABELS]))
        : (Object.keys(DELAY_COLORS) as DelayLevel[]).map((l) => swatch(DELAY_COLORS[l], DELAY_LABELS[l]))}
    </div>
  );
}

/** Time on the horizontal axis, distance along the corridor on the vertical axis, one line per train. */
export function TimeDistanceGraph() {
  const wrap = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const controller = useRef<GraphController | null>(null);
  const [mode, setMode] = useState<ColorMode>("type");
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null);
  const hasAxis = useHistoryStore((s) => s.axis !== null);
  const hasTracks = useHistoryStore((s) => s.tracks.size > 0);
  const selectTrain = useRailStore((s) => s.selectTrain);
  const hovered = useHistoryStore((s) => (hover ? (s.tracks.get(hover.id) ?? null) : null));
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    const svg = svgRef.current;
    const box = wrap.current;
    if (!svg || !box) return;
    const graph = createGraph(svg, {
      onHover: setHover,
      onSelect: (id) => selectTrain(useRailStore.getState().selectedTrainId === id ? null : id),
    });
    graph.setMode(modeRef.current);
    controller.current = graph;
    const fit = () => graph.resize(box.clientWidth, box.clientHeight);
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(box);
    return () => {
      observer.disconnect();
      graph.destroy();
      controller.current = null;
    };
  }, [selectTrain]);

  useEffect(() => controller.current?.setMode(mode), [mode]);

  return (
    <section className="flex h-full min-h-0 flex-col gap-2 p-3" aria-label="Time-distance graph">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div>
          <h2 className="text-title font-semibold text-text">Time-distance graph</h2>
          <p className="text-caption text-muted">
            Distance along the corridor against clock time. Click a line to select the train; scroll to zoom, drag to pan.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-caption text-muted" title="The backend sends only the present moment, so the actual path is drawn from the snapshots this page has received.">
            <History className="h-3 w-3" aria-hidden="true" />
            actual path recorded since page load
          </span>
          <div className="flex rounded-md border border-white/10 p-0.5" role="group" aria-label="Colour lines by">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                aria-pressed={mode === m.id}
                onClick={() => setMode(m.id)}
                className={cn(
                  "rounded px-2 py-1 text-caption font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70",
                  mode === m.id ? "bg-accent/20 text-accent" : "text-muted hover:text-text",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-0.5" role="toolbar" aria-label="Graph zoom">
            <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Zoom in" title="Zoom in" onClick={() => controller.current?.zoomBy(1.5)}>
              <Plus className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Zoom out" title="Zoom out" onClick={() => controller.current?.zoomBy(1 / 1.5)}>
              <Minus className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Zoom to now" title="Zoom to now" onClick={() => controller.current?.goToNow()}>
              <Crosshair className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Show the whole day" title="Show the whole day" onClick={() => controller.current?.reset()}>
              <Maximize className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <div ref={wrap} className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-white/[0.06] bg-bg/60">
        <svg ref={svgRef} role="img" aria-label="Time-distance graph: one line per train, time across, distance down" className="block touch-none select-none" />
        {!hasAxis && (
          <div className="absolute inset-0 grid place-items-center" aria-busy="true">
            <div className="h-3/4 w-11/12 animate-pulse rounded-lg bg-white/[0.04]" />
          </div>
        )}
        {hasAxis && !hasTracks && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
            <p className="max-w-xs text-body text-muted">No trains yet. Press Start: planned, actual and predicted paths appear here as the day runs.</p>
          </div>
        )}
        {hover && hovered && (
          <div
            className="glass-strong pointer-events-none absolute z-10 w-52 rounded-lg px-3 py-2 text-caption"
            style={{ left: Math.min(hover.x + 14, (wrap.current?.clientWidth ?? 600) - 220), top: Math.max(4, hover.y - 14) }}
            role="tooltip"
          >
            <div className="font-mono text-body font-semibold text-text">{hovered.id}</div>
            <div className="text-muted">
              {hovered.name} · {CATEGORY_LABELS[hovered.category]}
            </div>
            <div className="mt-1 text-text">{formatDelay(hovered.delay)}</div>
          </div>
        )}
      </div>

      <Legend mode={mode} />
      <p className="text-micro normal-case tracking-normal text-muted">
        Branch stations sit on offset lanes (the tinted band under the main line); their distances are measured along the branch and are not main-line kilometres.
      </p>
    </section>
  );
}
