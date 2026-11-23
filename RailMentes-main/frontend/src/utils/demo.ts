/**
 * The guided demo: one fixed scenario and the captions that go with it.
 *
 * Seed 222, January, medium disruptions, CP-SAT. Chosen by scanning seeds 201-232 (see docs/PROGRESS.md):
 * fog from simulated minute 32, a single-line meeting flagged around minute 171, a recommendation around
 * minute 306, and a day where CP-SAT lowers average delay by about 24% against no control. It is the best of 32 seeds, so it
 * shows the mechanism clearly; it is NOT a typical day (the 20-seed benchmark says 2-5% over the priority rule).
 */
import type { Intensity, StateSnapshot, StrategyName } from "../api/types";

export const DEMO_SCENARIO: { seed: number; intensity: Intensity; month: number; strategy: StrategyName; speed: number } = {
  seed: 222,
  intensity: "medium",
  month: 1,
  strategy: "cpsat",
  speed: 10,
};

/** Speed after the first conflict: slow enough that pausing on the recommendation takes effect within a tick. */
export const DEMO_SLOW_SPEED = 4;

export type DemoEvent = "fog" | "conflict" | "recommendation" | "applied" | "finished";
export type DemoStep = "intro" | DemoEvent;

export interface DemoCaption {
  title: string;
  body: string;
}

export const DEMO_CAPTIONS: Record<DemoStep, DemoCaption> = {
  intro: {
    title: "Guided demo: a foggy January day",
    body: "Synthetic corridor, seed 222, medium disruptions, CP-SAT optimizer. Watch the map; the captions follow what happens.",
  },
  fog: {
    title: "1. Fog sets in",
    body: "Trains in the foggy sections slow down. Delay starts to build, and slow trains hold up faster ones behind them.",
  },
  conflict: {
    title: "2. A conflict is predicted on the single line",
    body: "Two trains would meet on a single track. The red marker and the alert appear before it happens, using the delay model's predicted times.",
  },
  recommendation: {
    title: "3. The optimizer recommends a decision",
    body: "Paused so you can read it. The alert panel shows the action, the reason and the estimated saving (a prediction that overstates the real gain). Press Apply, then Start to resume.",
  },
  applied: {
    title: "4. Applied",
    body: "The lower-priority train now waits at the station and the more important one runs through. Resume and watch the effect build up.",
  },
  finished: {
    title: "5. The day is over: compare the strategies",
    body: "Open the Compare tab to see average delay, punctuality and the other KPIs for no control, FCFS, priority and CP-SAT on this same day.",
  },
};

export interface DemoState {
  active: boolean;
  seen: DemoEvent[];
  current: DemoStep;
}

/** True if the snapshot holds a recommendation the controller can still apply. */
export function hasProposal(snapshot: StateSnapshot): boolean {
  return snapshot.recommendations.some((r) => r.status === "proposed");
}

export const DEMO_IDLE: DemoState = { active: false, seen: [], current: "intro" };

const ORDER: DemoEvent[] = ["fog", "conflict", "recommendation", "applied", "finished"];

/** Which events are visible in this snapshot. */
export function eventsIn(snapshot: StateSnapshot): Set<DemoEvent> {
  const out = new Set<DemoEvent>();
  if (snapshot.disruptions.some((d) => d.kind === "fog")) out.add("fog");
  if (snapshot.conflicts.some((c) => c.kind === "single_line_meeting")) out.add("conflict");
  if (hasProposal(snapshot)) out.add("recommendation");
  if (snapshot.recommendations.some((r) => r.status === "applied")) out.add("applied");
  if (snapshot.trains.length > 0 && snapshot.trains.every((t) => t.status === "finished")) out.add("finished");
  return out;
}

/** Forget that an event was shown, so its caption can come back (the recommendation vanished before it could be used). */
export function rearm(state: DemoState, event: DemoEvent): DemoState {
  const seen = state.seen.filter((e) => e !== event);
  const last = seen.length > 0 ? seen[seen.length - 1] : "intro";
  return { ...state, seen, current: state.current === event ? last : state.current };
}

/** Fold a snapshot into the demo: the caption moves to the latest event that has not been shown yet. */
export function advanceDemo(state: DemoState, snapshot: StateSnapshot): DemoState {
  if (!state.active) return state;
  const now = eventsIn(snapshot);
  const fresh = ORDER.filter((e) => now.has(e) && !state.seen.includes(e));
  if (fresh.length === 0) return state;
  return { ...state, seen: [...state.seen, ...fresh], current: fresh[fresh.length - 1] };
}
