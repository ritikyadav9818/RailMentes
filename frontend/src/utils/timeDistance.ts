/**
 * Pure maths for the time-distance (string) graph.
 *
 * Vertical axis: distance along the corridor. The main line uses its real km. Branch and spur stations
 * sit on offset lanes: a separate band below the main line, so they can never be mistaken for main-line
 * positions. Horizontal axis: scenario time in minutes.
 *
 * A train is a polyline of (time, distance) points: planned (timetable), actual (recorded) and
 * predicted (delay model, future only).
 */
import type { Conflict, Disruption, NetworkInfo, Position, StateSnapshot, TrainCategory, TrainState } from "../api/types";
import { affectedBlockIds } from "./disruptions";
import { computeLayout, type MapLayout } from "./layout";

/** Gap (km) between the main line and the branch band, and between two branches. */
export const BAND_GAP_KM = 6;
/** Half width (min) of the shaded area around a predicted conflict time. */
export const CONFLICT_HALF_WIDTH_MIN = 6;

export interface AxisStation {
  code: string;
  name: string;
  km: number;
  branch: boolean;
  size: 1 | 2 | 3;
}

export interface DistanceAxis {
  stations: AxisStation[];
  km: Record<string, number>;
  maxKm: number;
  /** distance where the branch band starts (null if there are no branch stations) */
  branchStartKm: number | null;
  layout: MapLayout;
}

/** Colours per train type. Chosen apart from the delay colours (green / amber / orange / red). */
export const CATEGORY_COLORS: Record<TrainCategory, string> = {
  premium: "#c4b5fd",
  express: "#38bdf8",
  passenger: "#e2e8f0",
  freight: "#d4a373",
};

export interface Sample {
  /** scenario minute */
  t: number;
  /** distance on the axis */
  km: number;
}

/** Distance of every station on the axis. Branch stations go into a band after the main line. */
export function buildAxis(network: NetworkInfo): DistanceAxis {
  const layout = computeLayout(network);
  const km: Record<string, number> = {};
  let run = 0;
  layout.mainLine.forEach((code, i) => {
    if (i > 0) {
      const seg = layout.segments.find(
        (s) => (s.from === layout.mainLine[i - 1] && s.to === code) || (s.to === layout.mainLine[i - 1] && s.from === code),
      );
      run += seg?.lengthKm ?? 0;
    }
    km[code] = run;
  });
  const mainKm = run;

  // each branch = the stations reached through one first step away from the main line
  const adjacent = new Map<string, { to: string; km: number }[]>();
  for (const s of layout.segments) {
    adjacent.set(s.from, [...(adjacent.get(s.from) ?? []), { to: s.to, km: s.lengthKm }]);
    adjacent.set(s.to, [...(adjacent.get(s.to) ?? []), { to: s.from, km: s.lengthKm }]);
  }
  let cursor = mainKm + BAND_GAP_KM;
  let branchStartKm: number | null = null;
  for (const code of layout.mainLine) {
    for (const first of adjacent.get(code) ?? []) {
      if (km[first.to] !== undefined) continue;
      branchStartKm ??= cursor;
      let farthest = cursor;
      const stack: [string, number][] = [[first.to, cursor]];
      km[first.to] = cursor;
      while (stack.length > 0) {
        const [here, at] = stack.pop() as [string, number];
        for (const next of adjacent.get(here) ?? []) {
          if (km[next.to] !== undefined) continue;
          km[next.to] = at + next.km;
          farthest = Math.max(farthest, km[next.to]);
          stack.push([next.to, km[next.to]]);
        }
      }
      cursor = farthest + BAND_GAP_KM;
    }
  }
  // anything unreachable is parked after the band so the graph still draws
  for (const s of network.stations) {
    if (km[s.code] === undefined) {
      km[s.code] = cursor;
      cursor += BAND_GAP_KM;
    }
  }
  const mainSet = new Set(layout.mainLine);
  const stations: AxisStation[] = network.stations
    .map((s) => ({ code: s.code, name: s.name, km: km[s.code], branch: !mainSet.has(s.code), size: s.size }))
    .sort((a, b) => a.km - b.km);
  return { stations, km, maxKm: Math.max(0, ...stations.map((s) => s.km)), branchStartKm, layout };
}

/** Distance of a train position on the axis (null if the block or station is unknown). */
export function positionKm(axis: DistanceAxis, position: Position): number | null {
  if (position.at_station) return axis.km[position.at_station] ?? null;
  if (!position.block_id) return null;
  const hit = axis.layout.blocks[position.block_id];
  if (!hit) return null;
  const { segment, block } = hit;
  const covered = Math.min(Math.max(position.offset_km, 0), block.lengthKm);
  const along = position.direction === "rev" ? block.startKm + block.lengthKm - covered : block.startKm + covered;
  const a = axis.km[segment.from];
  const b = axis.km[segment.to];
  if (a === undefined || b === undefined) return null;
  return a + (b - a) * (segment.lengthKm > 0 ? along / segment.lengthKm : 0);
}

/** Where a location string (block id or station code) lies on the axis, as a [low, high] span. */
export function locationSpan(axis: DistanceAxis, location: string): [number, number] | null {
  const hit = axis.layout.blocks[location];
  if (hit) {
    const { segment, block } = hit;
    const a = axis.km[segment.from];
    const b = axis.km[segment.to];
    if (a === undefined || b === undefined) return null;
    const f0 = block.startKm / segment.lengthKm;
    const f1 = (block.startKm + block.lengthKm) / segment.lengthKm;
    const p = a + (b - a) * f0;
    const q = a + (b - a) * f1;
    return [Math.min(p, q), Math.max(p, q)];
  }
  const st = axis.km[location];
  return st === undefined ? null : [st, st];
}

export interface Rect {
  id: string;
  t0: number;
  t1: number;
  km0: number;
  km1: number;
}

/** Shaded areas for the conflicts: the conflict location, around its predicted time. */
export function conflictRects(axis: DistanceAxis, conflicts: Conflict[]): Rect[] {
  const out: Rect[] = [];
  for (const c of conflicts) {
    const span = locationSpan(axis, c.location);
    if (!span) continue;
    const pad = span[0] === span[1] ? 1.5 : 0;
    out.push({
      id: c.id,
      t0: c.time_min - CONFLICT_HALF_WIDTH_MIN,
      t1: c.time_min + CONFLICT_HALF_WIDTH_MIN,
      km0: span[0] - pad,
      km1: span[1] + pad,
    });
  }
  return out;
}

export interface DisruptionRect extends Rect {
  kind: Disruption["kind"];
  /** true if the speed factor is 0 (nothing can enter) */
  closed: boolean;
}

/** Shaded areas for disruptions: one rectangle per affected block over the disruption's time window. */
export function disruptionRects(axis: DistanceAxis, disruptions: Disruption[]): DisruptionRect[] {
  const out: DisruptionRect[] = [];
  for (const d of disruptions) {
    if (d.kind === "late_departure") continue; // not a place on the line
    if (d.target_ids.length === 0) {
      out.push({ id: `${d.id}`, kind: d.kind, closed: d.speed_factor === 0, t0: d.start_tick, t1: d.end_tick, km0: 0, km1: axis.maxKm });
      continue;
    }
    for (const blockId of affectedBlockIds(axis.layout, d.target_ids)) {
      const span = locationSpan(axis, blockId);
      if (span) out.push({ id: `${d.id}:${blockId}`, kind: d.kind, closed: d.speed_factor === 0, t0: d.start_tick, t1: d.end_tick, km0: span[0], km1: span[1] });
    }
  }
  return out;
}

export interface TrainTrack {
  id: string;
  name: string;
  category: TrainCategory;
  priority: number;
  delay: number;
  /** recorded (time, distance) points since the page was loaded */
  actual: Sample[];
  /** timetable: scheduled time at every station seen, in route order */
  planned: Sample[];
  /** from "now" through the predicted station times (future only) */
  predicted: Sample[];
}

/** Add a sample; a train standing still keeps only the first and last point of the stop. */
export function appendSample(points: Sample[], sample: Sample): Sample[] {
  const n = points.length;
  if (n > 0 && sample.t <= points[n - 1].t) return points;
  if (n >= 2 && points[n - 1].km === points[n - 2].km && points[n - 1].km === sample.km) {
    const copy = points.slice(0, n - 1);
    copy.push(sample);
    return copy;
  }
  return [...points, sample];
}

/** Planned points for the stops of one snapshot, merged into what we already know (route order = time order). */
export function mergePlanned(known: Sample[], train: TrainState, axis: DistanceAxis): Sample[] {
  const byTime = new Map<number, Sample>(known.map((s) => [s.t, s]));
  for (const stop of train.next_stations) {
    const km = axis.km[stop.station];
    if (km !== undefined) byTime.set(stop.scheduled_min, { t: stop.scheduled_min, km });
  }
  return [...byTime.values()].sort((a, b) => a.t - b.t);
}

/** Future path: the train's position now, then each predicted station time that is still ahead. */
export function predictedPath(train: TrainState, axis: DistanceAxis, now: number): Sample[] {
  if (!train.position) return [];
  const here = positionKm(axis, train.position);
  if (here === null) return [];
  const out: Sample[] = [{ t: now, km: here }];
  for (const stop of train.next_stations) {
    const km = axis.km[stop.station];
    if (km === undefined || stop.predicted_min <= out[out.length - 1].t) continue;
    out.push({ t: stop.predicted_min, km });
  }
  return out.length > 1 ? out : [];
}

/** Everything the graph needs from one snapshot, folded into the previous tracks. */
export function updateTracks(
  previous: Map<string, TrainTrack>,
  snapshot: StateSnapshot,
  axis: DistanceAxis,
): Map<string, TrainTrack> {
  const next = new Map(previous);
  for (const train of snapshot.trains) {
    const old = previous.get(train.id);
    let actual = old?.actual ?? [];
    if (train.position) {
      const km = positionKm(axis, train.position);
      if (km !== null) actual = appendSample(actual, { t: snapshot.tick, km });
    }
    const planned = mergePlanned(old?.planned ?? [], train, axis);
    if (train.status === "finished" && planned.length > 0 && actual.length > 0) {
      const end = planned[planned.length - 1];
      if (actual[actual.length - 1].km !== end.km) actual = appendSample(actual, { t: snapshot.tick, km: end.km });
    }
    next.set(train.id, {
      id: train.id,
      name: train.name,
      category: train.category,
      priority: train.priority,
      delay: train.delay_min,
      actual,
      planned,
      predicted: predictedPath(train, axis, snapshot.tick),
    });
  }
  return next;
}

export interface LinearScale {
  (value: number): number;
  domain: () => [number, number];
  range: () => [number, number];
}

/** Small linear scale so the maths can be tested without D3 (D3 scales are used for drawing). */
export function linearScale(domain: [number, number], range: [number, number]): LinearScale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  const fn = ((v: number) => r0 + ((v - d0) / span) * (r1 - r0)) as LinearScale;
  fn.domain = () => domain;
  fn.range = () => range;
  return fn;
}

/** Visible time window: the whole simulated day plus a margin. */
export const TIME_DOMAIN: [number, number] = [0, 1560];

/** Clock-aligned tick values (every `step` minutes) inside a domain. */
export function timeTicks(domain: [number, number], startMinuteOfDay: number, step: number): number[] {
  const first = Math.ceil((domain[0] + startMinuteOfDay) / step) * step - startMinuteOfDay;
  const out: number[] = [];
  for (let t = first; t <= domain[1]; t += step) out.push(t);
  return out;
}

/** A readable tick step (minutes) for a visible span: about 8-14 ticks across. */
export function tickStep(spanMin: number): number {
  for (const step of [5, 10, 15, 30, 60, 120, 240]) if (spanMin / step <= 14) return step;
  return 240;
}

/** Colour of a track: by type or by its current delay. */
export function trackColor(track: TrainTrack, mode: "type" | "delay", delayColorOf: (d: number) => string): string {
  return mode === "type" ? CATEGORY_COLORS[track.category] : delayColorOf(track.delay);
}

/** Tracks as drawable line lists, skipping those with nothing to draw. */
export function drawable(tracks: Map<string, TrainTrack>): TrainTrack[] {
  return [...tracks.values()].filter((t) => t.actual.length > 0 || t.planned.length > 1 || t.predicted.length > 1);
}
