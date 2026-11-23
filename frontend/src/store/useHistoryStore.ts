/**
 * What the dashboard remembers about the current run since the page was loaded: each train's recorded
 * path (for the time-distance graph), the disruptions and conflicts seen, and the KPI trace used to
 * compare a replay with the run before it. The backend sends only the present moment, so history lives here.
 */
import { create } from "zustand";

import type { Conflict, Disruption, NetworkInfo, StateSnapshot, StrategyName } from "../api/types";
import { scenarioStartMinuteOfDay } from "../utils/time";
import { buildAxis, updateTracks, type DistanceAxis, type TrainTrack } from "../utils/timeDistance";
import type { DataSource } from "./useRailStore";

export interface KpiPoint {
  t: number;
  avgDelay: number;
  punctuality: number;
}

/** The run before a replay, for a same-time-of-day comparison. */
export interface Baseline {
  strategy: StrategyName;
  trace: KpiPoint[];
}

export interface HistoryState {
  /** increases whenever the run restarts (reset, replay, switch from demo data to live) */
  runId: number;
  axis: DistanceAxis | null;
  tracks: Map<string, TrainTrack>;
  /** every disruption seen, by id (the snapshot lists only active ones) */
  disruptions: Map<string, Disruption>;
  /** every conflict seen, by id; `activeConflicts` are in the latest snapshot */
  conflicts: Map<string, Conflict>;
  activeConflicts: Set<string>;
  tick: number;
  startMinuteOfDay: number;
  strategy: StrategyName | null;
  source: DataSource;
  kpiTrace: KpiPoint[];
  baseline: Baseline | null;
  pendingBaseline: Baseline | null;

  ingest: (snapshot: StateSnapshot, network: NetworkInfo, source: DataSource) => void;
  /** Remember the current run so the next restart is shown against it. */
  armReplay: () => void;
  dismissBaseline: () => void;
}

const empty = {
  runId: 0,
  axis: null,
  tracks: new Map<string, TrainTrack>(),
  disruptions: new Map<string, Disruption>(),
  conflicts: new Map<string, Conflict>(),
  activeConflicts: new Set<string>(),
  tick: -1,
  startMinuteOfDay: 0,
  strategy: null,
  source: "none" as DataSource,
  kpiTrace: [] as KpiPoint[],
  baseline: null,
  pendingBaseline: null,
};

export const useHistoryStore = create<HistoryState>()((set, get) => ({
  ...empty,

  ingest: (snapshot, network, source) => {
    const s = get();
    const restarted = s.tick >= 0 && (snapshot.tick < s.tick || source !== s.source);
    const base = restarted
      ? {
          runId: s.runId + 1,
          tracks: new Map<string, TrainTrack>(),
          disruptions: new Map<string, Disruption>(),
          conflicts: new Map<string, Conflict>(),
          kpiTrace: [] as KpiPoint[],
          baseline: s.pendingBaseline,
          pendingBaseline: null,
        }
      : s;
    // the distance axis only depends on the network
    const axis = s.axis && s.axis.stations.length === network.stations.length ? s.axis : buildAxis(network);
    if (!restarted && snapshot.tick === s.tick && s.tracks.size > 0) {
      // repeated frame (pause, injected disruption): refresh what can change without a new tick
      const disruptions = new Map(base.disruptions);
      for (const d of snapshot.disruptions) disruptions.set(d.id, d);
      set({ disruptions, ...conflictState(base.conflicts, snapshot) });
      return;
    }
    const disruptions = new Map(base.disruptions);
    for (const d of snapshot.disruptions) disruptions.set(d.id, d);
    const kpiTrace =
      snapshot.tick > (base.kpiTrace.at(-1)?.t ?? -1)
        ? [...base.kpiTrace, { t: snapshot.tick, avgDelay: snapshot.kpis.avg_delay_min, punctuality: snapshot.kpis.punctuality_pct }]
        : base.kpiTrace;
    set({
      runId: base.runId,
      axis,
      tracks: updateTracks(base.tracks, snapshot, axis),
      disruptions,
      ...conflictState(base.conflicts, snapshot),
      tick: snapshot.tick,
      startMinuteOfDay: scenarioStartMinuteOfDay(snapshot.sim_time, snapshot.tick),
      strategy: snapshot.strategy,
      source,
      kpiTrace,
      baseline: base.baseline,
      pendingBaseline: base.pendingBaseline,
    });
  },

  armReplay: () => {
    const s = get();
    if (s.strategy) set({ pendingBaseline: { strategy: s.strategy, trace: s.kpiTrace } });
  },

  dismissBaseline: () => set({ baseline: null }),
}));

function conflictState(known: Map<string, Conflict>, snapshot: StateSnapshot) {
  const conflicts = new Map(known);
  for (const c of snapshot.conflicts) conflicts.set(c.id, c);
  return { conflicts, activeConflicts: new Set(snapshot.conflicts.map((c) => c.id)) };
}

/** The baseline's KPI at the same tick as `t` (last sample not after it). */
export function baselineAt(baseline: Baseline | null, t: number): KpiPoint | null {
  if (!baseline) return null;
  let found: KpiPoint | null = null;
  for (const p of baseline.trace) {
    if (p.t > t) break;
    found = p;
  }
  return found;
}

/** Back to the empty state (tests). */
export function resetHistoryStore(): void {
  useHistoryStore.setState({
    ...empty,
    tracks: new Map(),
    disruptions: new Map(),
    conflicts: new Map(),
    activeConflicts: new Set(),
    kpiTrace: [],
  });
}
