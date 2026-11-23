import { describe, expect, it } from "vitest";

import type { Conflict, Disruption, NetworkInfo, StateSnapshot, TrainState } from "../api/types";
import { mockNetwork, mockSnapshot } from "../mocks";
import {
  BAND_GAP_KM,
  appendSample,
  buildAxis,
  conflictRects,
  disruptionRects,
  linearScale,
  locationSpan,
  mergePlanned,
  positionKm,
  predictedPath,
  tickStep,
  timeTicks,
  updateTracks,
} from "./timeDistance";

/** A-B-C is the main line (10 km + 20 km); D hangs off B on a 5 km branch. */
const network: NetworkInfo = {
  disclaimer: "test",
  stations: [
    { code: "A", name: "Alpha", size: 1, platforms: 2, is_junction: false, freight_only: false },
    { code: "B", name: "Bravo", size: 1, platforms: 2, is_junction: true, freight_only: false },
    { code: "C", name: "Charlie", size: 1, platforms: 2, is_junction: false, freight_only: false },
    { code: "D", name: "Delta", size: 3, platforms: 1, is_junction: false, freight_only: false },
  ],
  blocks: [
    { id: "A-B-1", from_code: "A", to_code: "B", length_km: 10, line: "single", speed_limit_kmph: 100 },
    { id: "B-C-1", from_code: "B", to_code: "C", length_km: 20, line: "single", speed_limit_kmph: 100 },
    { id: "B-D-1", from_code: "B", to_code: "D", length_km: 5, line: "single", speed_limit_kmph: 60 },
  ],
};

function train(over: Partial<TrainState> = {}): TrainState {
  return {
    id: "T1",
    name: "Test express",
    category: "express",
    priority: 3,
    position: { block_id: "B-C-1", offset_km: 5, direction: "fwd", at_station: null },
    speed_kmph: 80,
    delay_min: 4,
    status: "running",
    next_stations: [
      { station: "C", will_stop: true, scheduled_min: 60, predicted_min: 64 },
    ],
    delay_factors: [],
    ...over,
  };
}

function snapshot(tick: number, trains: TrainState[], extra: Partial<StateSnapshot> = {}): StateSnapshot {
  return { ...mockSnapshot, tick, trains, disruptions: [], conflicts: [], recommendations: [], ...extra };
}

describe("buildAxis", () => {
  const axis = buildAxis(network);

  it("puts the main line at its real kilometres", () => {
    expect(axis.km.A).toBe(0);
    expect(axis.km.B).toBe(10);
    expect(axis.km.C).toBe(30);
  });

  it("puts branch stations on an offset lane after the main line", () => {
    expect(axis.km.D).toBe(30 + BAND_GAP_KM);
    expect(axis.branchStartKm).toBe(30 + BAND_GAP_KM);
    expect(axis.stations.find((s) => s.code === "D")?.branch).toBe(true);
    expect(axis.stations.find((s) => s.code === "B")?.branch).toBe(false);
  });

  it("lists stations in distance order and knows the maximum", () => {
    const kms = axis.stations.map((s) => s.km);
    expect([...kms].sort((a, b) => a - b)).toEqual(kms);
    expect(axis.maxKm).toBe(36);
  });

  it("works for the real corridor: every station gets a distance and the band starts after the main line", () => {
    const real = buildAxis(mockNetwork);
    for (const s of mockNetwork.stations) expect(Number.isFinite(real.km[s.code])).toBe(true);
    const mainMax = Math.max(...real.layout.mainLine.map((c) => real.km[c]));
    for (const s of real.stations.filter((x) => x.branch)) expect(s.km).toBeGreaterThan(mainMax);
  });
});

describe("positionKm", () => {
  const axis = buildAxis(network);

  it("is the station distance when the train is at a station", () => {
    expect(positionKm(axis, { block_id: null, offset_km: 0, direction: null, at_station: "B" })).toBe(10);
  });

  it("measures forward trains from the block start", () => {
    expect(positionKm(axis, { block_id: "B-C-1", offset_km: 5, direction: "fwd", at_station: null })).toBeCloseTo(15);
  });

  it("measures reverse trains from the block end", () => {
    expect(positionKm(axis, { block_id: "B-C-1", offset_km: 5, direction: "rev", at_station: null })).toBeCloseTo(25);
  });

  it("interpolates onto the branch lane", () => {
    expect(positionKm(axis, { block_id: "B-D-1", offset_km: 2.5, direction: "fwd", at_station: null })).toBeCloseTo(23);
  });

  it("returns null for unknown blocks and stations", () => {
    expect(positionKm(axis, { block_id: "NOPE", offset_km: 1, direction: "fwd", at_station: null })).toBeNull();
    expect(positionKm(axis, { block_id: null, offset_km: 0, direction: null, at_station: "ZZ" })).toBeNull();
  });
});

describe("locationSpan", () => {
  const axis = buildAxis(network);
  it("spans a block, or a single point for a station", () => {
    expect(locationSpan(axis, "B-C-1")).toEqual([10, 30]);
    expect(locationSpan(axis, "C")).toEqual([30, 30]);
    expect(locationSpan(axis, "nope")).toBeNull();
  });
});

describe("appendSample", () => {
  it("adds a new point and ignores time that does not advance", () => {
    const one = appendSample([], { t: 1, km: 0 });
    expect(appendSample(one, { t: 1, km: 5 })).toBe(one);
    expect(appendSample(one, { t: 2, km: 5 })).toHaveLength(2);
  });

  it("keeps only the first and last point of a stop", () => {
    let pts = appendSample([], { t: 1, km: 10 });
    pts = appendSample(pts, { t: 2, km: 10 });
    pts = appendSample(pts, { t: 3, km: 10 });
    pts = appendSample(pts, { t: 4, km: 10 });
    expect(pts).toEqual([
      { t: 1, km: 10 },
      { t: 4, km: 10 },
    ]);
    pts = appendSample(pts, { t: 5, km: 12 });
    expect(pts).toHaveLength(3);
  });
});

describe("planned and predicted paths", () => {
  const axis = buildAxis(network);

  it("merges planned stops over several snapshots in time order", () => {
    const first = mergePlanned([], train({ next_stations: [{ station: "B", will_stop: true, scheduled_min: 20, predicted_min: 22 }, { station: "C", will_stop: true, scheduled_min: 60, predicted_min: 62 }] }), axis);
    const later = mergePlanned(first, train({ next_stations: [{ station: "C", will_stop: true, scheduled_min: 60, predicted_min: 66 }] }), axis);
    expect(later).toEqual([
      { t: 20, km: 10 },
      { t: 60, km: 30 },
    ]);
  });

  it("builds the predicted path from the current position through future predictions only", () => {
    const t = train({
      next_stations: [
        { station: "C", will_stop: true, scheduled_min: 60, predicted_min: 64 },
        { station: "D", will_stop: true, scheduled_min: 90, predicted_min: 95 },
      ],
    });
    const path = predictedPath(t, axis, 40);
    expect(path[0]).toEqual({ t: 40, km: 15 });
    expect(path.map((p) => p.t)).toEqual([40, 64, 95]);
    // a prediction that is not after "now" is skipped
    expect(predictedPath(train({ next_stations: [{ station: "C", will_stop: true, scheduled_min: 30, predicted_min: 30 }] }), axis, 40)).toEqual([]);
  });

  it("has no predicted path for a train that is not on the line", () => {
    expect(predictedPath(train({ position: null }), axis, 10)).toEqual([]);
  });
});

describe("updateTracks", () => {
  const axis = buildAxis(network);

  it("records the actual path tick by tick and keeps the plan", () => {
    let tracks = updateTracks(new Map(), snapshot(10, [train()]), axis);
    tracks = updateTracks(tracks, snapshot(11, [train({ position: { block_id: "B-C-1", offset_km: 6, direction: "fwd", at_station: null } })]), axis);
    const t = tracks.get("T1");
    expect(t?.actual.map((p) => p.t)).toEqual([10, 11]);
    expect(t?.actual[1].km).toBeCloseTo(16);
    expect(t?.planned).toEqual([{ t: 60, km: 30 }]);
    expect(t?.predicted.length).toBeGreaterThan(1);
  });

  it("closes the actual path at the last station when the train finishes", () => {
    let tracks = updateTracks(new Map(), snapshot(10, [train()]), axis);
    tracks = updateTracks(tracks, snapshot(70, [train({ position: null, status: "finished", next_stations: [] })]), axis);
    expect(tracks.get("T1")?.actual.at(-1)).toEqual({ t: 70, km: 30 });
  });

  it("does not change the previous map", () => {
    const before = new Map();
    updateTracks(before, snapshot(10, [train()]), axis);
    expect(before.size).toBe(0);
  });
});

describe("shaded areas", () => {
  const axis = buildAxis(network);

  it("places a conflict at its block around its time", () => {
    const c: Conflict = { id: "c-1", kind: "single_line_meeting", severity: "high", train_ids: ["T1", "T2"], location: "B-C-1", time_min: 100, description: "x" };
    const [r] = conflictRects(axis, [c]);
    expect(r.km0).toBe(10);
    expect(r.km1).toBe(30);
    expect(r.t0).toBeLessThan(100);
    expect(r.t1).toBeGreaterThan(100);
  });

  it("gives a station-located conflict some height, and skips unknown locations", () => {
    const base: Conflict = { id: "c-2", kind: "block", severity: "low", train_ids: [], location: "B", time_min: 50, description: "" };
    const [r] = conflictRects(axis, [base]);
    expect(r.km1).toBeGreaterThan(r.km0);
    expect(conflictRects(axis, [{ ...base, location: "nowhere" }])).toEqual([]);
  });

  it("shades a closure over its blocks and window, and whole-network fog over the full height", () => {
    const closure: Disruption = { id: "d-1", kind: "block_closure", start_tick: 30, end_tick: 90, target_ids: ["B-C-1"], speed_factor: 0, description: "" };
    const fog: Disruption = { id: "d-2", kind: "fog", start_tick: 10, end_tick: 50, target_ids: [], speed_factor: 0.6, description: "" };
    const late: Disruption = { id: "d-3", kind: "late_departure", start_tick: 0, end_tick: 20, target_ids: ["T1"], speed_factor: 1, description: "" };
    const rects = disruptionRects(axis, [closure, fog, late]);
    const c = rects.find((r) => r.id.startsWith("d-1"));
    expect(c).toMatchObject({ closed: true, t0: 30, t1: 90, km0: 10, km1: 30 });
    const f = rects.find((r) => r.id === "d-2");
    expect(f).toMatchObject({ closed: false, km0: 0, km1: axis.maxKm });
    expect(rects.some((r) => r.id.startsWith("d-3"))).toBe(false);
  });
});

describe("scales and ticks", () => {
  it("maps a domain onto a range linearly", () => {
    const s = linearScale([0, 100], [10, 210]);
    expect(s(0)).toBe(10);
    expect(s(50)).toBe(110);
    expect(s(100)).toBe(210);
    expect(s.domain()).toEqual([0, 100]);
  });

  it("does not divide by zero on an empty domain", () => {
    expect(Number.isFinite(linearScale([5, 5], [0, 100])(5))).toBe(true);
  });

  it("aligns ticks to the clock and keeps them inside the domain", () => {
    // the scenario starts at 06:20, so a tick every 30 min falls on :00 and :30
    const ticks = timeTicks([0, 100], 6 * 60 + 20, 30);
    expect(ticks).toEqual([10, 40, 70, 100]);
  });

  it("picks a coarser step for a longer span", () => {
    expect(tickStep(60)).toBeLessThan(tickStep(1500));
    expect(1500 / tickStep(1500)).toBeLessThanOrEqual(14);
  });
});
