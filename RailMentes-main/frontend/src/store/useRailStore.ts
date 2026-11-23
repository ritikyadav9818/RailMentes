/** Single Zustand store: latest snapshot, connection status, scenario settings, selected train. */
import { create } from "zustand";

import type { Intensity, NetworkInfo, ScenarioInfo, StateSnapshot, StrategyName } from "../api/types";
import type { SocketStatus } from "../api/socket";
import { mockNetwork, mockSnapshot } from "../mocks";
import { smoothInterval } from "../utils/interpolate";

/**
 * connecting      first attempt in progress, nothing to show yet
 * online          live data from the backend
 * reconnecting    was live, connection lost; the last snapshot stays on screen
 * offline_demo    never reached the backend; showing the bundled mock snapshot
 */
export type Connection = "connecting" | "online" | "reconnecting" | "offline_demo";
export type DataSource = "none" | "live" | "mock";

/** What the control bar edits. Applied to the backend by the control actions. */
export interface Settings {
  seed: number;
  intensity: Intensity;
  month: number;
  /** ticks (simulated minutes) per real second, 0.5 to 20 */
  speed: number;
  strategy: StrategyName;
}

export const DEFAULT_SETTINGS: Settings = { seed: 42, intensity: "none", month: 1, speed: 1, strategy: "no_control" };
export const SPEED_MIN = 0.5;
export const SPEED_MAX = 20;

export interface RailState {
  network: NetworkInfo | null;
  networkSource: DataSource;
  snapshot: StateSnapshot | null;
  /** the snapshot before `snapshot` (the map slides from one to the other) */
  previous: StateSnapshot | null;
  /** performance.now() when `snapshot` arrived */
  receivedAt: number;
  /** smoothed real time between snapshots, ms (null until measured) */
  intervalMs: number | null;
  connection: Connection;
  dataSource: DataSource;
  /** true once a live snapshot has been received in this page session */
  everLive: boolean;
  settings: Settings;
  selectedTrainId: string | null;

  setNetwork: (network: NetworkInfo, source: DataSource) => void;
  applySnapshot: (snapshot: StateSnapshot, source: DataSource, now?: number) => void;
  setSocketStatus: (status: SocketStatus, attempt: number) => void;
  showMockData: () => void;
  updateSettings: (patch: Partial<Settings>) => void;
  syncScenario: (info: ScenarioInfo, strategy: StrategyName) => void;
  selectTrain: (id: string | null) => void;
}

const initial = {
  network: null,
  networkSource: "none" as DataSource,
  snapshot: null,
  previous: null,
  receivedAt: 0,
  intervalMs: null,
  connection: "connecting" as Connection,
  dataSource: "none" as DataSource,
  everLive: false,
  settings: DEFAULT_SETTINGS,
  selectedTrainId: null,
};

const now = (): number => (typeof performance !== "undefined" ? performance.now() : Date.now());

export const useRailStore = create<RailState>()((set, get) => ({
  ...initial,

  setNetwork: (network, source) => set({ network, networkSource: source }),

  applySnapshot: (snapshot, source, at = now()) => {
    const s = get();
    // repeated frames with the same tick (pause, injected disruption) must not distort the timing
    const advanced = s.snapshot !== null && snapshot.tick !== s.snapshot.tick;
    const intervalMs = source === "live" && advanced ? smoothInterval(s.intervalMs, at - s.receivedAt) : s.intervalMs;
    set({
      snapshot,
      previous: s.snapshot,
      receivedAt: at,
      intervalMs,
      dataSource: source,
      everLive: s.everLive || source === "live",
      connection: source === "live" ? "online" : s.connection,
      // the backend's strategy wins when it changes (e.g. started from another client)
      settings:
        source === "live" && s.snapshot && snapshot.strategy !== s.snapshot.strategy
          ? { ...s.settings, strategy: snapshot.strategy }
          : s.settings,
    });
  },

  setSocketStatus: (status, attempt) => {
    const s = get();
    if (status === "open" || status === "closed") return;
    if (status === "connecting") {
      if (s.snapshot === null) set({ connection: "connecting" });
      return;
    }
    // status === "reconnecting": a connection attempt failed
    if (s.everLive) set({ connection: "reconnecting" });
    else if (attempt >= 1) get().showMockData();
  },

  showMockData: () => {
    const s = get();
    if (s.everLive) return;
    set({
      network: s.networkSource === "live" ? s.network : mockNetwork,
      networkSource: s.networkSource === "live" ? "live" : "mock",
      snapshot: mockSnapshot,
      previous: null,
      dataSource: "mock",
      connection: "offline_demo",
    });
  },

  updateSettings: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),

  syncScenario: (info, strategy) =>
    set({
      settings: { seed: info.seed, intensity: info.intensity, month: info.month, speed: info.speed, strategy },
    }),

  selectTrain: (id) => set({ selectedTrainId: id }),
}));

/** Back to the empty state (tests). */
export function resetRailStore(): void {
  useRailStore.setState({ ...initial, settings: { ...DEFAULT_SETTINGS } });
}
