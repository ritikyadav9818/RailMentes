import { describe, expect, it } from "vitest";

import type { Conflict, Recommendation, Severity } from "../api/types";
import { buildFeed } from "./feed";
import { clockFromIso, clockFromScenarioMinute, dayProgress, scenarioStartMinuteOfDay } from "./time";
import { trainTargets, STATION_SPREAD } from "./trainTargets";
import { computeLayout } from "./layout";
import { mockNetwork } from "../mocks";
import type { TrainState } from "../api/types";

const conflict = (id: string, severity: Severity, time_min: number): Conflict => ({
  id,
  kind: "block",
  severity,
  train_ids: ["A", "B"],
  location: "BHP-GNK-1",
  time_min,
  description: id,
});

const rec = (id: string, conflict_ids: string[], status: Recommendation["status"] = "proposed"): Recommendation => ({
  id,
  strategy: "priority",
  status,
  conflict_ids,
  expected_delay_saved_min: 4,
  action: { kind: "hold", train_id: "A", at_station: "GNK", hold_minutes: 4, other_train_id: null, reason: "because" },
});

describe("buildFeed", () => {
  it("sorts by severity, then by time", () => {
    const feed = buildFeed([conflict("c1", "low", 10), conflict("c2", "critical", 50), conflict("c3", "critical", 20)], []);
    expect(feed.active.map((i) => i.key)).toEqual(["c3", "c2", "c1"]);
  });

  it("attaches a recommendation to its conflict as one card", () => {
    const feed = buildFeed([conflict("c1", "high", 10)], [rec("r1", ["c1"])]);
    expect(feed.active).toHaveLength(1);
    expect(feed.active[0].key).toBe("c1"); // same key as the conflict-only card, so no re-mount
    expect(feed.active[0].recommendation?.id).toBe("r1");
  });

  it("drops a proposed recommendation whose conflict is gone", () => {
    const feed = buildFeed([], [rec("r1", ["c-gone"])]);
    expect(feed.active).toHaveLength(0);
    expect(feed.handled).toHaveLength(0);
  });

  it("keeps an ignored recommendation on its card while the conflict remains, and lists applied ones as handled once it is gone", () => {
    const withConflict = buildFeed([conflict("c1", "high", 10)], [rec("r1", ["c1"], "ignored")]);
    expect(withConflict.active[0].recommendation?.status).toBe("ignored");
    const gone = buildFeed([], [rec("r2", ["c1"], "applied")]);
    expect(gone.active).toHaveLength(0);
    expect(gone.handled.map((i) => i.key)).toEqual(["r2"]);
  });

  it("is empty for an empty snapshot", () => {
    expect(buildFeed([], [])).toEqual({ active: [], handled: [] });
  });
});

describe("time helpers", () => {
  it("reads the clock from an ISO string without timezone maths", () => {
    expect(clockFromIso("2026-01-15T08:15:30")).toBe("08:15");
    expect(clockFromIso("2026-01-15T08:15:30", true)).toBe("08:15:30");
    expect(clockFromIso("garbage")).toBe("--:--");
  });

  it("turns scenario minutes into wall-clock times, wrapping past midnight", () => {
    const start = scenarioStartMinuteOfDay("2026-01-15T08:15:00", 135); // scenario started at 06:00
    expect(start).toBe(360);
    expect(clockFromScenarioMinute(135, start)).toBe("08:15");
    expect(clockFromScenarioMinute(1100, start)).toBe("00:20");
  });

  it("limits the day progress to 0..1", () => {
    expect(dayProgress(720)).toBe(0.5);
    expect(dayProgress(5000)).toBe(1);
    expect(dayProgress(-3)).toBe(0);
  });
});

describe("trainTargets", () => {
  const layout = computeLayout(mockNetwork);
  const train = (id: string, position: TrainState["position"]): TrainState => ({
    id,
    name: id,
    category: "express",
    priority: 3,
    position,
    speed_kmph: 0,
    delay_min: 0,
    status: "running",
    next_stations: [],
    delay_factors: [],
  });

  it("leaves out trains without a position and spreads trains standing at one station", () => {
    const at = { block_id: null, offset_km: 0, direction: null, at_station: "VDJ" };
    const targets = trainTargets(layout, [train("T2", at), train("T1", at), train("T0", null)]);
    expect(targets.has("T0")).toBe(false);
    const a = targets.get("T1");
    const b = targets.get("T2");
    expect((b?.x ?? 0) - (a?.x ?? 0)).toBe(STATION_SPREAD);
    expect(((a?.x ?? 0) + (b?.x ?? 0)) / 2).toBeCloseTo(layout.stations.VDJ.x, 5);
  });
});
