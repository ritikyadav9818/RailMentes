/** Which blocks a disruption touches, and which of them the map should draw as weather. */
import type { Disruption, DisruptionKind } from "../api/types";
import type { MapLayout } from "./layout";

/**
 * Resolve disruption targets to block ids. A target may be a block id, a segment id
 * ("BHP-GNK") or a station code (all blocks touching the station); empty = whole network.
 */
export function affectedBlockIds(layout: MapLayout, targetIds: string[]): string[] {
  if (targetIds.length === 0) return Object.keys(layout.blocks);
  const found = new Set<string>();
  for (const target of targetIds) {
    if (layout.blocks[target]) found.add(target);
    for (const seg of layout.segments) {
      if (seg.id === target || seg.from === target || seg.to === target) {
        for (const b of seg.blocks) found.add(b.id);
      }
    }
  }
  return [...found];
}

export const WEATHER_KINDS: DisruptionKind[] = ["fog", "weather_slowdown"];

export function isWeather(d: Disruption): boolean {
  return WEATHER_KINDS.includes(d.kind);
}

/** True when the disruption covers the whole network (no targets). */
export function isNetworkWide(d: Disruption): boolean {
  return d.target_ids.length === 0;
}
