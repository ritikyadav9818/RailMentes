import { beforeEach, describe, expect, it } from "vitest";

import { mockNetwork, mockSnapshot } from "../mocks";
import type { ScenarioInfo, StateSnapshot } from "../api/types";
import { DEFAULT_SETTINGS, resetRailStore, useRailStore } from "./useRailStore";

const frame = (tick: number): StateSnapshot => ({ ...mockSnapshot, tick });
const store = () => useRailStore.getState();

beforeEach(() => resetRailStore());

describe("initial state", () => {
  it("starts empty and connecting, with default settings", () => {
    expect(store().snapshot).toBeNull();
    expect(store().connection).toBe("connecting");
    expect(store().dataSource).toBe("none");
    expect(store().settings).toEqual(DEFAULT_SETTINGS);
    expect(store().selectedTrainId).toBeNull();
  });
});

describe("applySnapshot", () => {
  it("keeps the previous snapshot for interpolation and marks the connection live", () => {
    store().applySnapshot(frame(1), "live", 1000);
    store().applySnapshot(frame(2), "live", 1100);
    expect(store().snapshot?.tick).toBe(2);
    expect(store().previous?.tick).toBe(1);
    expect(store().connection).toBe("online");
    expect(store().dataSource).toBe("live");
    expect(store().everLive).toBe(true);
    expect(store().receivedAt).toBe(1100);
  });

  it("measures the time between snapshots, but not for repeated ticks or stalls", () => {
    store().applySnapshot(frame(1), "live", 1000);
    store().applySnapshot(frame(2), "live", 1100);
    expect(store().intervalMs).toBe(100);
    store().applySnapshot(frame(2), "live", 9000); // same tick, e.g. after pause
    expect(store().intervalMs).toBe(100);
    store().applySnapshot(frame(3), "live", 30_000); // long stall
    expect(store().intervalMs).toBe(100);
  });
});

describe("strategy follows the backend", () => {
  it("updates the dropdown value only when the snapshot's strategy changes", () => {
    store().applySnapshot({ ...mockSnapshot, strategy: "no_control" }, "live", 1);
    store().updateSettings({ strategy: "fcfs" }); // picked in the UI, not sent yet
    store().applySnapshot({ ...mockSnapshot, strategy: "no_control", tick: 2 }, "live", 2);
    expect(store().settings.strategy).toBe("fcfs");
    store().applySnapshot({ ...mockSnapshot, strategy: "cpsat", tick: 3 }, "live", 3);
    expect(store().settings.strategy).toBe("cpsat");
  });
});

describe("socket status and the offline fallback", () => {
  it("stays quiet while the first attempt is running", () => {
    store().setSocketStatus("connecting", 0);
    expect(store().connection).toBe("connecting");
    expect(store().snapshot).toBeNull();
  });

  it("falls back to the mock snapshot and mock network when the first attempt fails", () => {
    store().setSocketStatus("reconnecting", 1);
    expect(store().connection).toBe("offline_demo");
    expect(store().dataSource).toBe("mock");
    expect(store().snapshot).toBe(mockSnapshot);
    expect(store().network).toBe(mockNetwork);
  });

  it("keeps a live network when the mock snapshot is shown", () => {
    const live = { ...mockNetwork, disclaimer: "live" };
    store().setNetwork(live, "live");
    store().showMockData();
    expect(store().network).toBe(live);
    expect(store().dataSource).toBe("mock");
  });

  it("replaces the demo data as soon as a live snapshot arrives", () => {
    store().setSocketStatus("reconnecting", 1);
    store().applySnapshot(frame(7), "live", 5);
    expect(store().dataSource).toBe("live");
    expect(store().connection).toBe("online");
    expect(store().snapshot?.tick).toBe(7);
  });

  it("keeps the last live data on screen when the connection drops later", () => {
    store().applySnapshot(frame(9), "live", 5);
    store().setSocketStatus("reconnecting", 1);
    expect(store().connection).toBe("reconnecting");
    expect(store().dataSource).toBe("live");
    expect(store().snapshot?.tick).toBe(9);
    store().showMockData(); // must not overwrite live data
    expect(store().dataSource).toBe("live");
  });
});

describe("settings and selection", () => {
  it("merges settings patches", () => {
    store().updateSettings({ speed: 8 });
    store().updateSettings({ intensity: "high" });
    expect(store().settings).toMatchObject({ speed: 8, intensity: "high", seed: 42 });
  });

  it("syncs settings from GET /scenario plus the snapshot strategy", () => {
    const info: ScenarioInfo = { seed: 7, intensity: "medium", month: 11, speed: 5, running: false, tick: 0, finished: false };
    store().syncScenario(info, "priority");
    expect(store().settings).toEqual({ seed: 7, intensity: "medium", month: 11, speed: 5, strategy: "priority" });
  });

  it("selects and deselects a train", () => {
    store().selectTrain("22401");
    expect(store().selectedTrainId).toBe("22401");
    store().selectTrain(null);
    expect(store().selectedTrainId).toBeNull();
  });
});
