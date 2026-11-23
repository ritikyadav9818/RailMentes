import { beforeEach, describe, expect, it } from "vitest";

import { mockNetwork, mockSnapshot } from "../mocks";
import { baselineAt, resetHistoryStore, useHistoryStore } from "./useHistoryStore";

const at = (tick: number, extra: Partial<typeof mockSnapshot> = {}) => ({ ...mockSnapshot, tick, ...extra });
const ingest = (tick: number, source: "live" | "mock" = "live", extra: Partial<typeof mockSnapshot> = {}) =>
  useHistoryStore.getState().ingest(at(tick, extra), mockNetwork, source);

beforeEach(resetHistoryStore);

describe("useHistoryStore", () => {
  it("builds the axis and one track per train", () => {
    ingest(100);
    const s = useHistoryStore.getState();
    expect(s.axis).not.toBeNull();
    expect(s.tracks.size).toBe(mockSnapshot.trains.length);
    expect(s.tick).toBe(100);
  });

  it("appends to the recorded path as the tick advances", () => {
    ingest(100);
    ingest(101);
    ingest(102);
    const track = [...useHistoryStore.getState().tracks.values()].find((t) => t.actual.length > 0);
    expect(track?.actual.length).toBeGreaterThanOrEqual(2);
    expect(useHistoryStore.getState().runId).toBe(0);
  });

  it("a repeated tick (pause, injected disruption) records no new point but remembers new disruptions", () => {
    ingest(100);
    const before = useHistoryStore.getState().tracks;
    ingest(100, "live", { disruptions: [{ id: "m-001", kind: "fog", start_tick: 100, end_tick: 160, target_ids: [], speed_factor: 0.6, description: "" }] });
    const s = useHistoryStore.getState();
    expect(s.tracks).toBe(before);
    expect(s.disruptions.has("m-001")).toBe(true);
  });

  it("keeps disruptions and conflicts after the snapshot stops listing them", () => {
    const d = { id: "d-9", kind: "fog" as const, start_tick: 90, end_tick: 120, target_ids: [], speed_factor: 0.7, description: "" };
    const c = { id: "c-9", kind: "block" as const, severity: "low" as const, train_ids: [], location: "GNK", time_min: 130, description: "" };
    ingest(100, "live", { disruptions: [d], conflicts: [c] });
    ingest(101, "live", { disruptions: [], conflicts: [] });
    const s = useHistoryStore.getState();
    expect(s.disruptions.has("d-9")).toBe(true);
    expect(s.conflicts.has("c-9")).toBe(true);
    expect(s.activeConflicts.has("c-9")).toBe(false);
  });

  it("starts a new run when the tick goes backwards (reset or replay)", () => {
    ingest(100);
    ingest(101);
    ingest(0);
    const s = useHistoryStore.getState();
    expect(s.runId).toBe(1);
    expect([...s.tracks.values()].every((t) => t.actual.length <= 1)).toBe(true);
  });

  it("starts a new run when the data source changes from demo data to live", () => {
    ingest(100, "mock");
    ingest(101, "live");
    expect(useHistoryStore.getState().runId).toBe(1);
  });

  it("carries the previous run's KPI trace over a replay as a baseline, and not over a plain reset", () => {
    ingest(10);
    ingest(11);
    useHistoryStore.getState().armReplay();
    ingest(0);
    const s = useHistoryStore.getState();
    expect(s.baseline?.trace.map((p) => p.t)).toEqual([10, 11]);
    ingest(1);
    ingest(0); // a plain reset: no replay armed
    expect(useHistoryStore.getState().baseline).toBeNull();
  });

  it("finds the baseline KPI at the same time of day", () => {
    const baseline = { strategy: "no_control" as const, trace: [{ t: 5, avgDelay: 1, punctuality: 100 }, { t: 10, avgDelay: 2, punctuality: 90 }] };
    expect(baselineAt(baseline, 4)).toBeNull();
    expect(baselineAt(baseline, 7)?.avgDelay).toBe(1);
    expect(baselineAt(baseline, 99)?.avgDelay).toBe(2);
    expect(baselineAt(null, 5)).toBeNull();
  });

  it("can dismiss the baseline", () => {
    ingest(10);
    useHistoryStore.getState().armReplay();
    ingest(0);
    useHistoryStore.getState().dismissBaseline();
    expect(useHistoryStore.getState().baseline).toBeNull();
  });
});
