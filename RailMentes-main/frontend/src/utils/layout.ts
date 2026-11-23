/**
 * Computes the schematic map from GET /network. Nothing is hard-coded to one corridor:
 *  1. blocks are grouped into segments (one station pair, blocks in numeric order),
 *  2. the longest path through the station graph becomes the main line (left to right, by km),
 *  3. every other station hangs on a branch that leaves its junction up or down, alternating.
 * Assumes the network is a tree (true for the corridor); cycles are ignored safely.
 */
import type { BlockInfo, LineType, NetworkInfo, Position } from "../api/types";
import type { Point } from "./interpolate";
import { clamp, lerpPoint } from "./interpolate";

export interface LayoutOptions {
  /** screen units per km; derived from `targetWidth` when not given */
  kmScale: number;
  /** width the main line should span, used to derive kmScale */
  targetWidth: number;
  /** vertical distance between lanes (main line = lane 0) */
  laneGap: number;
  padding: { left: number; right: number; top: number; bottom: number };
  /** half distance between the two rails of a double line */
  railOffset: number;
}

export const DEFAULT_LAYOUT: Omit<LayoutOptions, "kmScale"> = {
  targetWidth: 1500,
  laneGap: 200,
  padding: { left: 50, right: 50, top: 50, bottom: 50 },
  railOffset: 6,
};

export interface StationNode extends Point {
  code: string;
  name: string;
  isJunction: boolean;
  freightOnly: boolean;
  size: 1 | 2 | 3;
  onMainLine: boolean;
}

export interface LayoutBlock {
  id: string;
  segmentId: string;
  /** km from the segment's from-station to the start of this block */
  startKm: number;
  lengthKm: number;
}

interface SegmentBase {
  id: string;
  from: string;
  to: string;
  line: LineType;
  lengthKm: number;
  blocks: LayoutBlock[];
}

export interface LayoutSegment extends SegmentBase {
  /** screen position of the from-station and the to-station */
  a: Point;
  b: Point;
}

export interface MapLayout {
  width: number;
  height: number;
  stations: Record<string, StationNode>;
  stationList: StationNode[];
  segments: LayoutSegment[];
  /** block id -> its segment and position inside it */
  blocks: Record<string, { segment: LayoutSegment; block: LayoutBlock }>;
  mainLine: string[];
  options: LayoutOptions;
}

interface Edge {
  to: string;
  km: number;
}

/** Trailing number of a block id: "BHP-GNK-3" -> 3 (0 if none). */
function blockOrder(id: string): number {
  const m = /-(\d+)$/.exec(id);
  return m ? Number(m[1]) : 0;
}

/** Group blocks into segments, keeping the network's order of first appearance. */
export function buildSegments(blocks: BlockInfo[]): SegmentBase[] {
  const groups = new Map<string, BlockInfo[]>();
  for (const b of blocks) {
    const key = `${b.from_code}-${b.to_code}`;
    groups.set(key, [...(groups.get(key) ?? []), b]);
  }
  return [...groups.entries()].map(([id, list]) => {
    const sorted = [...list].sort((p, q) => blockOrder(p.id) - blockOrder(q.id));
    let km = 0;
    const laid: LayoutBlock[] = sorted.map((b) => {
      const item = { id: b.id, segmentId: id, startKm: km, lengthKm: b.length_km };
      km += b.length_km;
      return item;
    });
    return {
      id,
      from: sorted[0].from_code,
      to: sorted[0].to_code,
      line: sorted.some((b) => b.line === "single") ? ("single" as const) : ("double" as const),
      lengthKm: km,
      blocks: laid,
    };
  });
}

function buildAdjacency(segs: SegmentBase[]): Map<string, Edge[]> {
  const adj = new Map<string, Edge[]>();
  const add = (from: string, to: string, km: number) => adj.set(from, [...(adj.get(from) ?? []), { to, km }]);
  for (const s of segs) {
    add(s.from, s.to, s.lengthKm);
    add(s.to, s.from, s.lengthKm);
  }
  return adj;
}

/** Walk the graph from `start`; returns distance (km) and parent of every reachable station. */
function walk(adj: Map<string, Edge[]>, start: string) {
  const dist = new Map<string, number>([[start, 0]]);
  const parent = new Map<string, string | null>([[start, null]]);
  const stack = [start];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    for (const e of adj.get(cur) ?? []) {
      if (dist.has(e.to)) continue;
      dist.set(e.to, (dist.get(cur) ?? 0) + e.km);
      parent.set(e.to, cur);
      stack.push(e.to);
    }
  }
  return { dist, parent };
}

function farthest(dist: Map<string, number>): string {
  let best = "";
  let bestKm = -1;
  for (const [code, km] of dist) {
    if (km > bestKm) {
      best = code;
      bestKm = km;
    }
  }
  return best;
}

/** Longest station path, ordered so the station listed first in the network ends up on the left. */
export function findMainLine(stationCodes: string[], segs: SegmentBase[]): string[] {
  if (stationCodes.length === 0) return [];
  const adj = buildAdjacency(segs);
  const end1 = farthest(walk(adj, stationCodes[0]).dist);
  const second = walk(adj, end1);
  const end2 = farthest(second.dist);
  const path: string[] = [];
  for (let cur: string | null = end2; cur !== null; cur = second.parent.get(cur) ?? null) path.push(cur);
  const order = (c: string) => stationCodes.indexOf(c);
  return order(path[0]) <= order(path[path.length - 1]) ? path : path.reverse();
}

function connects(s: { from: string; to: string }, a: string, b: string): boolean {
  return (s.from === a && s.to === b) || (s.from === b && s.to === a);
}

/** Raw (unshifted) station positions: main line on y = 0, branches on lanes above and below. */
function placeStations(
  codes: string[],
  segs: SegmentBase[],
  mainLine: string[],
  options: LayoutOptions,
): Map<string, Point> {
  const adj = buildAdjacency(segs);
  const pos = new Map<string, Point>();

  let km = 0;
  mainLine.forEach((code, i) => {
    if (i > 0) km += segs.find((s) => connects(s, mainLine[i - 1], code))?.lengthKm ?? 0;
    pos.set(code, { x: km * options.kmScale, y: 0 });
  });

  // The first child continues in the lane of its parent, further children open new lanes.
  const placeChildren = (from: string, side: number, lane: number) => {
    let opened = 0;
    for (const edge of adj.get(from) ?? []) {
      if (pos.has(edge.to)) continue;
      const childLane = lane + opened;
      opened += 1;
      const origin = pos.get(from) as Point;
      pos.set(edge.to, { x: origin.x + edge.km * options.kmScale, y: side * options.laneGap * childLane });
      placeChildren(edge.to, side, childLane);
    }
  };

  let branches = 0;
  for (const code of mainLine) {
    for (const edge of adj.get(code) ?? []) {
      if (pos.has(edge.to)) continue;
      branches += 1;
      const side = branches % 2 === 1 ? 1 : -1; // first branch below the main line, next above, ...
      const origin = pos.get(code) as Point;
      // the first step is at least one lane gap wide so the departure reads as a clear diagonal
      const dx = Math.max(edge.km * options.kmScale, options.laneGap);
      pos.set(edge.to, { x: origin.x + dx, y: side * options.laneGap });
      placeChildren(edge.to, side, 1);
    }
  }

  // stations that are not connected to anything: park them to the right
  let spill = Math.max(0, ...[...pos.values()].map((p) => p.x));
  for (const code of codes) {
    if (pos.has(code)) continue;
    spill += options.laneGap;
    pos.set(code, { x: spill, y: 0 });
  }
  return pos;
}

/** Length in km of the path along `line`. */
function pathKm(line: string[], segs: SegmentBase[]): number {
  let km = 0;
  for (let i = 1; i < line.length; i++) km += segs.find((s) => connects(s, line[i - 1], line[i]))?.lengthKm ?? 0;
  return km;
}

export function computeLayout(network: NetworkInfo, partial: Partial<LayoutOptions> = {}): MapLayout {
  const segs = buildSegments(network.blocks);
  const codes = network.stations.map((s) => s.code);
  const mainLine = findMainLine(codes, segs);
  const base = { ...DEFAULT_LAYOUT, ...partial };
  const mainKm = pathKm(mainLine, segs);
  const options: LayoutOptions = { ...base, kmScale: partial.kmScale ?? (mainKm > 0 ? base.targetWidth / mainKm : 10) };
  const raw = placeStations(codes, segs, mainLine, options);

  const minX = Math.min(0, ...[...raw.values()].map((p) => p.x));
  const minY = Math.min(0, ...[...raw.values()].map((p) => p.y));
  const shiftX = options.padding.left - minX;
  const shiftY = options.padding.top - minY;
  const mainSet = new Set(mainLine);

  const stationList: StationNode[] = network.stations.map((s) => {
    const p = raw.get(s.code) as Point;
    return {
      code: s.code,
      name: s.name,
      isJunction: s.is_junction,
      freightOnly: s.freight_only,
      size: s.size,
      onMainLine: mainSet.has(s.code),
      x: p.x + shiftX,
      y: p.y + shiftY,
    };
  });
  const stations = Object.fromEntries(stationList.map((s) => [s.code, s]));

  const segments: LayoutSegment[] = segs.map((s) => ({
    ...s,
    a: { x: stations[s.from].x, y: stations[s.from].y },
    b: { x: stations[s.to].x, y: stations[s.to].y },
  }));
  const blocks: MapLayout["blocks"] = {};
  for (const segment of segments) for (const block of segment.blocks) blocks[block.id] = { segment, block };

  return {
    width: Math.max(0, ...stationList.map((s) => s.x)) + options.padding.right,
    height: Math.max(0, ...stationList.map((s) => s.y)) + options.padding.bottom,
    stations,
    stationList,
    segments,
    blocks,
    mainLine,
    options,
  };
}

/** Lane gap limits (world units) when the layout is stretched to an aspect ratio. */
const MIN_LANE_GAP = 150;
const MAX_LANE_GAP = 420;

/**
 * Layout whose width : height is close to `aspect` (the shape of the canvas it will be shown on),
 * so the corridor fills a tall canvas instead of leaving empty bands. Only the vertical spacing
 * between lanes changes; the main line keeps its km scale. Falls back to the default for flat networks.
 */
export function computeLayoutForAspect(network: NetworkInfo, aspect: number): MapLayout {
  const first = computeLayout(network);
  const { padding, laneGap } = first.options;
  const rows = Math.round((first.height - padding.top - padding.bottom) / laneGap);
  if (rows < 1 || !(aspect > 0)) return first;
  const wanted = (first.width / aspect - padding.top - padding.bottom) / rows;
  return computeLayout(network, { laneGap: clamp(wanted, MIN_LANE_GAP, MAX_LANE_GAP) });
}

/** Point `km` along a segment (from its from-station). */
export function pointOnSegment(segment: LayoutSegment, km: number): Point {
  const t = segment.lengthKm > 0 ? clamp(km / segment.lengthKm, 0, 1) : 0;
  return lerpPoint(segment.a, segment.b, t);
}

/** End points of one block on the map, from the segment's from-station side to its to-station side. */
export function blockSpan(layout: MapLayout, blockId: string): { a: Point; b: Point } | null {
  const hit = layout.blocks[blockId];
  if (!hit) return null;
  const { segment, block } = hit;
  return {
    a: pointOnSegment(segment, block.startKm),
    b: pointOnSegment(segment, block.startKm + block.lengthKm),
  };
}

export function blockMidpoint(layout: MapLayout, blockId: string): Point | null {
  const span = blockSpan(layout, blockId);
  return span ? lerpPoint(span.a, span.b, 0.5) : null;
}

/** Unit vector pointing from the segment's from-station to its to-station. */
export function segmentDirection(segment: LayoutSegment): Point {
  const dx = segment.b.x - segment.a.x;
  const dy = segment.b.y - segment.a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: dx / len, y: dy / len };
}

/** Shift a point sideways from the track: +1 = lower side of a left-to-right track, -1 = upper. */
export function railShift(layout: MapLayout, segment: LayoutSegment, p: Point, side: 1 | -1): Point {
  const dir = segmentDirection(segment);
  const d = layout.options.railOffset * side;
  return { x: p.x - dir.y * d, y: p.y + dir.x * d };
}

/**
 * Where a train is drawn. In a block: along the track by its offset in the travel direction.
 * On a double line the forward train runs on the upper rail and the reverse train on the lower
 * rail (left-hand running); a single line has one rail. At a station: the station node.
 * Returns null if the block or station is unknown.
 */
export function trainPoint(layout: MapLayout, position: Position): Point | null {
  if (position.at_station) {
    const st = layout.stations[position.at_station];
    return st ? { x: st.x, y: st.y } : null;
  }
  if (!position.block_id) return null;
  const hit = layout.blocks[position.block_id];
  if (!hit) return null;
  const { segment, block } = hit;
  const covered = clamp(position.offset_km, 0, block.lengthKm);
  const forward = position.direction !== "rev";
  const km = forward ? block.startKm + covered : block.startKm + block.lengthKm - covered;
  const base = pointOnSegment(segment, km);
  return segment.line === "double" ? railShift(layout, segment, base, forward ? -1 : 1) : base;
}
