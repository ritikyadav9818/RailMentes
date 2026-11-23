/**
 * Decides which station labels are drawn at the current zoom and on which side of the line.
 *  - level of detail: major stations (size 1) and junctions always, size 2 from tier 2, the rest from tier 3
 *  - side: away from branches that leave the station, otherwise alternating above / below
 *  - no overlaps: boxes are checked in screen space; a minor label that does not fit is hidden
 * Pure function of the layout, the screen zoom and the tier, so it is easy to test.
 */
import type { MapLayout, StationNode } from "./layout";

export type Side = "above" | "below";

export interface LabelSpec {
  code: string;
  side: Side;
  /** show the station name next to the code */
  showName: boolean;
}

/** Rough text metrics in screen px for the label font sizes used by the map. */
const CODE_W = 8.4;
const NAME_W = 6.1;
const BOX_H = 34;

export function tierOf(node: StationNode): 1 | 2 | 3 {
  if (node.isJunction || node.size === 1) return 1;
  return node.size === 2 ? 2 : 3;
}

/** Sides of a station that a track leaves towards (a label there would sit on the track). */
function blockedSides(layout: MapLayout, code: string): Set<Side> {
  const blocked = new Set<Side>();
  const here = layout.stations[code];
  for (const s of layout.segments) {
    const other = s.from === code ? layout.stations[s.to] : s.to === code ? layout.stations[s.from] : null;
    if (!other) continue;
    const dx = Math.abs(other.x - here.x);
    const dy = other.y - here.y;
    // steeper than ~25 degrees counts as leaving up or down
    if (Math.abs(dy) > dx * 0.45) blocked.add(dy > 0 ? "below" : "above");
  }
  return blocked;
}

interface Box {
  l: number;
  r: number;
  t: number;
  b: number;
}

function overlaps(a: Box, b: Box): boolean {
  return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t;
}

function mainLineY(layout: MapLayout): number {
  const first = layout.mainLine[0];
  return first ? layout.stations[first].y : 0;
}

/**
 * Label specs for the stations that are visible at `tier`; `k` is the screen px per world unit,
 * `textScale` how much the label text is enlarged at this zoom.
 */
export function placeLabels(layout: MapLayout, k: number, tier: 1 | 2 | 3, textScale = 1): Map<string, LabelSpec> {
  const shown = layout.stationList
    .filter((s) => tierOf(s) <= tier)
    .sort((a, b) => tierOf(a) - tierOf(b) || a.x - b.x);
  // neighbours along the line get opposite sides
  const rank = new Map([...shown].sort((a, b) => a.x - b.x).map((s, i) => [s.code, i]));
  const result = new Map<string, LabelSpec>();
  const placed: Box[] = [];

  for (const node of shown) {
    const blocked = blockedSides(layout, node.code);
    const showName = tierOf(node) === 1 || tier >= 2;
    const width = (Math.max(node.code.length * CODE_W, showName ? node.name.length * NAME_W : 0) + 8) * textScale;
    const sx = node.x * k;
    const sy = node.y * k;
    const near = (node.isJunction ? 24 : 16) * textScale;
    const box = (side: Side): Box => {
      const h = BOX_H * textScale;
      const t = side === "above" ? sy - near - h : sy + near;
      return { l: sx - width / 2, r: sx + width / 2, t, b: t + h };
    };

    let preferred: Side;
    if (blocked.has("below") && !blocked.has("above")) preferred = "above";
    else if (blocked.has("above") && !blocked.has("below")) preferred = "below";
    else if (!node.onMainLine) preferred = node.y > mainLineY(layout) ? "below" : "above";
    else preferred = (rank.get(node.code) ?? 0) % 2 === 0 ? "above" : "below";

    const alt: Side = preferred === "above" ? "below" : "above";
    const pick = [preferred, alt].find((s) => !blocked.has(s) && !placed.some((p) => overlaps(p, box(s))));
    if (pick) {
      placed.push(box(pick));
      result.set(node.code, { code: node.code, side: pick, showName });
    } else if (tierOf(node) === 1) {
      // a major station is always labelled, even if it has to sit close to another label
      placed.push(box(preferred));
      result.set(node.code, { code: node.code, side: preferred, showName });
    }
  }
  return result;
}
