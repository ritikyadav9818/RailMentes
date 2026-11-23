/** Target map position of every visible train in one snapshot. */
import type { TrainState } from "../api/types";
import type { Point } from "./interpolate";
import { trainPoint, type MapLayout } from "./layout";

/** Horizontal gap between markers of trains standing at the same station. */
export const STATION_SPREAD = 13;

/**
 * Trains with no position (not started, finished) are left out. Trains at the same station
 * are spread sideways, in id order, so none hides another.
 */
export function trainTargets(layout: MapLayout, trains: TrainState[]): Map<string, Point> {
  const targets = new Map<string, Point>();
  const atStation = new Map<string, TrainState[]>();

  for (const train of trains) {
    if (!train.position) continue;
    const point = trainPoint(layout, train.position);
    if (!point) continue;
    targets.set(train.id, point);
    const code = train.position.at_station;
    if (code) atStation.set(code, [...(atStation.get(code) ?? []), train]);
  }

  for (const group of atStation.values()) {
    if (group.length < 2) continue;
    const sorted = [...group].sort((a, b) => a.id.localeCompare(b.id));
    sorted.forEach((train, i) => {
      const p = targets.get(train.id) as Point;
      targets.set(train.id, { x: p.x + (i - (sorted.length - 1) / 2) * STATION_SPREAD, y: p.y });
    });
  }
  return targets;
}
