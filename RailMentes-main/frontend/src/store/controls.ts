/** Control actions: each one calls the backend and reports the outcome as a toast. */
import { toast } from "sonner";

import { ApiError, api, type DisruptionBody } from "../api/client";
import type { Recommendation, RecommendationDecision, StrategyName } from "../api/types";
import { DEMO_SCENARIO } from "../utils/demo";
import { DISRUPTION_LABELS, STRATEGY_LABELS } from "../utils/labels";
import { useDemoStore } from "./useDemoStore";
import { useHistoryStore } from "./useHistoryStore";
import { useRailStore } from "./useRailStore";
import { useUiStore } from "./useUiStore";

const STRATEGY_CYCLE: StrategyName[] = ["no_control", "fcfs", "priority", "cpsat"];

function describe(err: unknown): string {
  if (err instanceof ApiError) return err.status === 0 ? "Backend not reachable" : err.message;
  return err instanceof Error ? err.message : "Something went wrong";
}

/** Run a request, toast a failure, return whether it worked. */
async function attempt(label: string, run: () => Promise<unknown>): Promise<boolean> {
  try {
    await run();
    return true;
  } catch (err) {
    toast.error(label, { description: describe(err) });
    return false;
  }
}

export function startSimulation(): Promise<boolean> {
  const { settings } = useRailStore.getState();
  return attempt("Could not start", () => api.start({ strategy: settings.strategy, speed: settings.speed }));
}

export function pauseSimulation(): Promise<boolean> {
  return attempt("Could not pause", () => api.pause());
}

export async function resetSimulation(): Promise<boolean> {
  useDemoStore.getState().end();
  const { settings } = useRailStore.getState();
  const ok = await attempt("Could not reset", () =>
    api.reset({ seed: settings.seed, intensity: settings.intensity, month: settings.month }),
  );
  if (ok) toast.success("Scenario reset", { description: `Seed ${settings.seed}, ${settings.intensity} disruptions` });
  return ok;
}

/** Called when the speed slider is released. */
export function commitSpeed(speed: number): Promise<boolean> {
  return attempt("Could not change speed", () => api.setSpeed(speed));
}

/** Switching strategy mid-run is done through start (the backend keeps the run going). */
export function commitStrategy(): Promise<boolean> {
  const { snapshot, settings } = useRailStore.getState();
  if (!snapshot?.running) return Promise.resolve(true); // takes effect on the next start
  return attempt("Could not change strategy", () => api.start({ strategy: settings.strategy }));
}

/** Strategy to replay with when none is chosen: the next one in the list after the current one. */
export function nextStrategy(current: StrategyName): StrategyName {
  const i = STRATEGY_CYCLE.indexOf(current);
  return STRATEGY_CYCLE[(i + 1) % STRATEGY_CYCLE.length];
}

/**
 * Same seed, intensity and month, a different strategy: reset the day, then run it again. The earlier run's
 * KPI trace is kept so the dashboard can show the two side by side at the same time of day.
 */
export async function replaySameScenario(strategy: StrategyName): Promise<boolean> {
  useDemoStore.getState().end();
  let info;
  try {
    info = await api.scenario(); // the backend's own seed / intensity / month, not what the popover shows
  } catch (err) {
    toast.error("Could not replay", { description: describe(err) });
    return false;
  }
  useHistoryStore.getState().armReplay();
  const reset = await attempt("Could not replay", () => api.reset({ seed: info.seed, intensity: info.intensity, month: info.month }));
  if (!reset) return false;
  const store = useRailStore.getState();
  store.syncScenario(info, strategy);
  const started = await attempt("Could not start the replay", () => api.start({ strategy, speed: store.settings.speed }));
  if (started) toast.success("Replaying the same day", { description: `Seed ${info.seed}, ${info.intensity} disruptions, ${STRATEGY_LABELS[strategy]}` });
  return started;
}

/** Load the demo scenario, start it at demo speed and switch the captions on. */
export async function startGuidedDemo(): Promise<boolean> {
  const demo = DEMO_SCENARIO;
  useDemoStore.getState().end();
  const reset = await attempt("Could not load the demo", () => api.reset({ seed: demo.seed, intensity: demo.intensity, month: demo.month }));
  if (!reset) return false;
  const store = useRailStore.getState();
  store.updateSettings({ seed: demo.seed, intensity: demo.intensity, month: demo.month, strategy: demo.strategy, speed: demo.speed });
  useUiStore.getState().setTab("map");
  useDemoStore.getState().begin();
  return attempt("Could not start the demo", () => api.start({ strategy: demo.strategy, speed: demo.speed }));
}

export async function injectDisruption(body: DisruptionBody): Promise<boolean> {
  try {
    const d = await api.inject(body);
    toast.success(`${DISRUPTION_LABELS[d.kind]} injected`, { description: d.description || d.id });
    return true;
  } catch (err) {
    toast.error("Could not inject disruption", { description: describe(err) });
    return false;
  }
}

/** Apply or ignore a recommendation. Ignore offers an undo; an applied action cannot be undone. */
export async function decideRecommendation(rec: Recommendation, decision: RecommendationDecision): Promise<boolean> {
  try {
    await api.decide(rec.id, decision);
  } catch (err) {
    toast.error(decision === "apply" ? "Could not apply" : "Could not update", { description: describe(err) });
    return false;
  }
  if (decision === "apply") {
    toast.success("Applied", { description: `${rec.action.reason.slice(0, 90)}. Applied actions cannot be undone.` });
  } else if (decision === "ignore") {
    toast("Recommendation ignored", {
      duration: 6000,
      action: { label: "Undo", onClick: () => void decideRecommendation(rec, "undo") },
    });
  } else {
    toast.success("Restored", { description: "The recommendation is open again." });
  }
  return true;
}
