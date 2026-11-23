/**
 * D3 drawing of the time-distance graph. React owns the container; this module owns the SVG inside it.
 * Each update only sets attributes on a fixed set of groups (a data join per train), so a new snapshot
 * costs a few dozen path updates and never re-renders React components.
 */
import * as d3 from "d3";

import { useHistoryStore } from "../../store/useHistoryStore";
import { useRailStore } from "../../store/useRailStore";
import { delayColor } from "../../utils/delay";
import { clockFromScenarioMinute } from "../../utils/time";
import {
  CATEGORY_COLORS,
  TIME_DOMAIN,
  conflictRects,
  disruptionRects,
  drawable,
  tickStep,
  timeTicks,
  trackColor,
  type DistanceAxis,
  type Sample,
  type TrainTrack,
} from "../../utils/timeDistance";

export type ColorMode = "type" | "delay";

export const MARGIN = { left: 62, right: 14, top: 12, bottom: 26 };
const KM_PAD = 3;
const MAX_ZOOM = 14;

export interface GraphHandlers {
  onHover: (hover: { id: string; x: number; y: number } | null) => void;
  onSelect: (id: string) => void;
}

export interface GraphController {
  resize: (width: number, height: number) => void;
  render: () => void;
  setMode: (mode: ColorMode) => void;
  zoomBy: (factor: number) => void;
  reset: () => void;
  goToNow: () => void;
  destroy: () => void;
}

const FOG = "#94a3b8";

function rectStyle(kind: string, closed: boolean): { fill: string; opacity: number; hatch: boolean } {
  if (closed) return { fill: "#f04438", opacity: 0.2, hatch: true };
  if (kind === "fog" || kind === "weather_slowdown") return { fill: FOG, opacity: 0.16, hatch: false };
  return { fill: "#f5a524", opacity: 0.16, hatch: false };
}

export function createGraph(svgEl: SVGSVGElement, handlers: GraphHandlers): GraphController {
  const svg = d3.select(svgEl);
  svg.selectAll("*").remove();
  let width = 0;
  let height = 0;
  let mode: ColorMode = "type";
  let transform = d3.zoomIdentity;
  let frame = 0;

  const defs = svg.append("defs");
  defs
    .append("pattern")
    .attr("id", "td-hatch")
    .attr("width", 7)
    .attr("height", 7)
    .attr("patternUnits", "userSpaceOnUse")
    .attr("patternTransform", "rotate(45)")
    .append("line")
    .attr("x1", 0)
    .attr("x2", 0)
    .attr("y1", 0)
    .attr("y2", 7)
    .attr("stroke", "#f04438")
    .attr("stroke-opacity", 0.55)
    .attr("stroke-width", 2);
  const clip = defs.append("clipPath").attr("id", "td-clip").append("rect");

  const root = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);
  const band = root.append("rect").attr("fill", "#38bdf8").attr("fill-opacity", 0.035);
  const bandLabel = root.append("text").attr("class", "td-band-label").attr("fill", "#8a9bb0").attr("font-size", 10);
  const plot = root.append("g").attr("clip-path", "url(#td-clip)");
  const grid = plot.append("g").attr("class", "td-grid");
  const shades = plot.append("g").attr("class", "td-shades");
  const planned = plot.append("g").attr("class", "td-planned").attr("fill", "none");
  const predicted = plot.append("g").attr("class", "td-predicted").attr("fill", "none");
  const actual = plot.append("g").attr("class", "td-actual").attr("fill", "none");
  const nowLine = plot.append("g").attr("class", "td-now");
  nowLine.append("line").attr("stroke", "#38bdf8").attr("stroke-width", 1.2).attr("stroke-dasharray", "2 3");
  const nowTag = nowLine.append("text").attr("fill", "#38bdf8").attr("font-size", 10).attr("text-anchor", "middle").text("now");
  const hits = plot.append("g").attr("class", "td-hits").attr("fill", "none");
  const yAxis = root.append("g").attr("class", "td-yaxis");
  const xAxis = root.append("g").attr("class", "td-xaxis");
  const overlay = root.append("rect").attr("class", "td-overlay").attr("fill", "none").attr("pointer-events", "none");

  const line = d3.line<Sample>();

  const zoom = d3
    .zoom<SVGSVGElement, unknown>()
    .scaleExtent([1, MAX_ZOOM])
    .on("zoom", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
      transform = event.transform;
      schedule();
    });
  svg.call(zoom).on("dblclick.zoom", null);

  const scales = () => {
    const axis = useHistoryStore.getState().axis;
    const maxKm = axis?.maxKm ?? 100;
    const xBase = d3.scaleLinear().domain(TIME_DOMAIN).range([0, width]);
    const yBase = d3.scaleLinear().domain([-KM_PAD, maxKm + KM_PAD]).range([0, height]);
    return { x: transform.rescaleX(xBase), y: transform.rescaleY(yBase), xBase, yBase };
  };

  function schedule(): void {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      draw();
    });
  }

  function pathOf(points: Sample[], x: d3.ScaleLinear<number, number>, y: d3.ScaleLinear<number, number>): string {
    return line.x((p) => x(p.t)).y((p) => y(p.km))(points) ?? "";
  }

  function drawAxes(axis: DistanceAxis, x: d3.ScaleLinear<number, number>, y: d3.ScaleLinear<number, number>, start: number): void {
    const [d0, d1] = x.domain();
    const ticks = timeTicks([d0, d1], start, tickStep(d1 - d0));
    grid
      .selectAll<SVGLineElement, number>("line.td-vt")
      .data(ticks, (d) => d)
      .join("line")
      .attr("class", "td-vt")
      .attr("x1", (t) => x(t))
      .attr("x2", (t) => x(t))
      .attr("y1", 0)
      .attr("y2", height)
      .attr("stroke", "#ffffff")
      .attr("stroke-opacity", 0.05);
    grid
      .selectAll<SVGLineElement, DistanceAxis["stations"][number]>("line.td-hz")
      .data(axis.stations, (s) => s.code)
      .join("line")
      .attr("class", "td-hz")
      .attr("x1", 0)
      .attr("x2", width)
      .attr("y1", (s) => y(s.km))
      .attr("y2", (s) => y(s.km))
      .attr("stroke", "#ffffff")
      .attr("stroke-opacity", (s) => (s.size === 1 ? 0.12 : 0.06))
      .attr("stroke-dasharray", (s) => (s.size === 1 ? null : "2 4"));

    // station labels: most important first, skip any that would overlap
    const placed: number[] = [];
    const labelled = [...axis.stations]
      .sort((a, b) => a.size - b.size || a.km - b.km)
      .filter((s) => {
        const py = y(s.km);
        if (py < -4 || py > height + 4 || placed.some((q) => Math.abs(q - py) < 13)) return false;
        placed.push(py);
        return true;
      });
    yAxis
      .selectAll<SVGTextElement, DistanceAxis["stations"][number]>("text")
      .data(labelled, (s) => s.code)
      .join("text")
      .attr("x", -8)
      .attr("y", (s) => y(s.km))
      .attr("dy", "0.32em")
      .attr("text-anchor", "end")
      .attr("font-size", 10.5)
      .attr("font-family", "JetBrains Mono Variable, monospace")
      .attr("fill", (s) => (s.branch ? "#7dd3fc" : "#dbe4ee"))
      .text((s) => s.code);

    const tickList = xAxis.selectAll<SVGGElement, number>("g.tick").data(ticks, (t) => t);
    const enter = tickList.enter().append("g").attr("class", "tick");
    enter.append("text").attr("fill", "#8a9bb0").attr("font-size", 10).attr("text-anchor", "middle").attr("font-family", "JetBrains Mono Variable, monospace");
    tickList.exit().remove();
    xAxis
      .selectAll<SVGGElement, number>("g.tick")
      .attr("transform", (t) => `translate(${x(t)},${height + 15})`)
      .select("text")
      .text((t) => clockFromScenarioMinute(t, start));
  }

  function drawBand(axis: DistanceAxis, y: d3.ScaleLinear<number, number>): void {
    if (axis.branchStartKm === null) {
      band.attr("width", 0);
      bandLabel.text("");
      return;
    }
    const top = y(axis.branchStartKm - 3);
    band.attr("x", 0).attr("y", Math.max(0, top)).attr("width", width).attr("height", Math.max(0, height - Math.max(0, top)));
    bandLabel.attr("x", width - 6).attr("y", Math.max(12, top + 12)).attr("text-anchor", "end").text("Branch & spur lanes (offset)");
  }

  function drawShades(axis: DistanceAxis, x: d3.ScaleLinear<number, number>, y: d3.ScaleLinear<number, number>): void {
    const h = useHistoryStore.getState();
    const dis = disruptionRects(axis, [...h.disruptions.values()]);
    const sel = shades
      .selectAll<SVGRectElement, (typeof dis)[number]>("rect.td-dis")
      .data(dis, (r) => r.id);
    sel
      .join("rect")
      .attr("class", "td-dis")
      .attr("x", (r) => x(r.t0))
      .attr("width", (r) => Math.max(0, x(r.t1) - x(r.t0)))
      .attr("y", (r) => y(r.km0))
      .attr("height", (r) => Math.max(2, y(r.km1) - y(r.km0)))
      .attr("fill", (r) => (r.closed ? "url(#td-hatch)" : rectStyle(r.kind, r.closed).fill))
      .attr("fill-opacity", (r) => (r.closed ? 1 : rectStyle(r.kind, r.closed).opacity))
      .selectAll("title")
      .data((r) => [r])
      .join("title")
      .text((r) => `${r.closed ? "Closed" : r.kind.replace("_", " ")} until ${clockFromScenarioMinute(r.t1, h.startMinuteOfDay)}`);

    const cons = conflictRects(axis, [...h.conflicts.values()]);
    shades
      .selectAll<SVGRectElement, (typeof cons)[number]>("rect.td-con")
      .data(cons, (r) => r.id)
      .join("rect")
      .attr("class", "td-con")
      .attr("x", (r) => x(r.t0))
      .attr("width", (r) => Math.max(3, x(r.t1) - x(r.t0)))
      .attr("y", (r) => y(r.km0))
      .attr("height", (r) => Math.max(6, y(r.km1) - y(r.km0)))
      .attr("fill", "#f04438")
      .attr("fill-opacity", (r) => (h.activeConflicts.has(r.id) ? 0.3 : 0.1))
      .attr("stroke", "#f04438")
      .attr("stroke-opacity", (r) => (h.activeConflicts.has(r.id) ? 0.85 : 0.3))
      .attr("stroke-dasharray", "3 2")
      .selectAll("title")
      .data((r) => [r])
      .join("title")
      .text((r) => h.conflicts.get(r.id)?.description ?? "Conflict");
  }

  function drawLines(x: d3.ScaleLinear<number, number>, y: d3.ScaleLinear<number, number>, tracks: TrainTrack[], selected: string | null): void {
    const colour = (t: TrainTrack) => trackColor(t, mode, delayColor);
    const dim = (t: TrainTrack) => (selected && selected !== t.id ? 0.22 : 1);
    const emphasis = (t: TrainTrack) => (selected === t.id ? 1.6 : 1);

    planned
      .selectAll<SVGPathElement, TrainTrack>("path")
      .data(tracks.filter((t) => t.planned.length > 1), (t) => t.id)
      .join("path")
      .attr("d", (t) => pathOf(t.planned, x, y))
      .attr("stroke", colour)
      .attr("stroke-width", (t) => 1 * emphasis(t))
      .attr("stroke-opacity", (t) => 0.28 * dim(t));
    predicted
      .selectAll<SVGPathElement, TrainTrack>("path")
      .data(tracks.filter((t) => t.predicted.length > 1), (t) => t.id)
      .join("path")
      .attr("d", (t) => pathOf(t.predicted, x, y))
      .attr("stroke", colour)
      .attr("stroke-width", (t) => 2 * emphasis(t))
      .attr("stroke-dasharray", "6 4")
      .attr("stroke-opacity", (t) => 0.85 * dim(t));
    actual
      .selectAll<SVGPathElement, TrainTrack>("path")
      .data(tracks.filter((t) => t.actual.length > 1), (t) => t.id)
      .join("path")
      .attr("d", (t) => pathOf(t.actual, x, y))
      .attr("stroke", colour)
      .attr("stroke-width", (t) => 2.4 * emphasis(t))
      .attr("stroke-linejoin", "round")
      .attr("stroke-opacity", (t) => 0.95 * dim(t));

    // wide invisible lines carry hover and click
    hits
      .selectAll<SVGPathElement, TrainTrack>("path")
      .data(tracks, (t) => t.id)
      .join(
        (enter) =>
          enter
            .append("path")
            .attr("stroke", "transparent")
            .attr("stroke-width", 11)
            .attr("pointer-events", "stroke")
            .style("cursor", "pointer")
            .on("pointermove", function (event: PointerEvent, t) {
              const box = svgEl.getBoundingClientRect();
              handlers.onHover({ id: t.id, x: event.clientX - box.left, y: event.clientY - box.top });
            })
            .on("pointerleave", () => handlers.onHover(null))
            .on("click", (_e, t) => handlers.onSelect(t.id)),
        (update) => update,
      )
      .attr("d", (t) => pathOf([...t.actual, ...t.predicted.slice(1)].length > 1 ? [...t.actual, ...t.predicted.slice(1)] : t.planned, x, y));
  }

  function draw(): void {
    const h = useHistoryStore.getState();
    const axis = h.axis;
    if (!axis || width <= 0 || height <= 0) return;
    const { x, y } = scales();
    drawBand(axis, y);
    drawAxes(axis, x, y, h.startMinuteOfDay);
    drawShades(axis, x, y);
    drawLines(x, y, drawable(h.tracks), useRailStore.getState().selectedTrainId);
    const nx = x(Math.max(0, h.tick));
    nowLine.select("line").attr("x1", nx).attr("x2", nx).attr("y1", 0).attr("y2", height);
    nowTag.attr("x", nx).attr("y", 10);
    nowLine.attr("display", h.tick >= 0 ? null : "none");
  }

  function applySize(): void {
    const w = Math.max(0, width);
    const h = Math.max(0, height);
    svg.attr("width", w + MARGIN.left + MARGIN.right).attr("height", h + MARGIN.top + MARGIN.bottom);
    clip.attr("width", w).attr("height", h);
    overlay.attr("width", w).attr("height", h);
    const extent: [[number, number], [number, number]] = [
      [0, 0],
      [w, h],
    ];
    zoom.extent(extent).translateExtent(extent);
  }

  const unsubscribeHistory = useHistoryStore.subscribe(schedule);
  const unsubscribeSelection = useRailStore.subscribe((s, p) => {
    if (s.selectedTrainId !== p.selectedTrainId) schedule();
  });

  return {
    resize: (w, h) => {
      width = Math.max(0, w - MARGIN.left - MARGIN.right);
      height = Math.max(0, h - MARGIN.top - MARGIN.bottom);
      applySize();
      schedule();
    },
    render: schedule,
    setMode: (m) => {
      mode = m;
      schedule();
    },
    zoomBy: (factor) => void svg.transition().duration(160).call(zoom.scaleBy, factor),
    reset: () => void svg.transition().duration(220).call(zoom.transform, d3.zoomIdentity),
    goToNow: () => {
      // zoom in on the action: centred on the clock time now and on where the running trains are
      const h = useHistoryStore.getState();
      const { xBase, yBase } = scales();
      const k = 3;
      const running = [...h.tracks.values()].filter((t) => t.predicted.length > 1 && t.actual.length > 0);
      const kmMid = running.length > 0 ? running.reduce((sum, t) => sum + t.actual[t.actual.length - 1].km, 0) / running.length : (h.axis?.maxKm ?? 0) / 2;
      const tx = Math.min(0, Math.max(width - width * k, width / 2 - xBase(Math.max(0, h.tick)) * k));
      const ty = Math.min(0, Math.max(height - height * k, height / 2 - yBase(kmMid) * k));
      void svg.transition().duration(260).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
    },
    destroy: () => {
      if (frame) cancelAnimationFrame(frame);
      unsubscribeHistory();
      unsubscribeSelection();
      svg.on(".zoom", null);
      svg.selectAll("*").remove();
    },
  };
}

/** Colour swatches for the legend. */
export const TYPE_SWATCHES = Object.entries(CATEGORY_COLORS);
