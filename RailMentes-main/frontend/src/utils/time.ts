/** Clock helpers. Scenario time is in minutes since scenario start (== ticks). */

export const MINUTES_PER_DAY = 1440;

const pad = (n: number): string => String(n).padStart(2, "0");

/** "08:15" from an ISO datetime such as "2026-01-15T08:15:00" (no timezone maths). */
export function clockFromIso(iso: string, withSeconds = false): string {
  const m = /T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(iso);
  if (!m) return "--:--";
  return withSeconds ? `${m[1]}:${m[2]}:${m[3] ?? "00"}` : `${m[1]}:${m[2]}`;
}

/** Minutes-of-day for the scenario start, derived from one snapshot (sim_time minus tick). */
export function scenarioStartMinuteOfDay(simTime: string, tick: number): number {
  const m = /T(\d{2}):(\d{2})/.exec(simTime);
  if (!m) return 0;
  return Number(m[1]) * 60 + Number(m[2]) - tick;
}

/** Wall-clock "HH:MM" for a scenario minute, given the start minute-of-day. */
export function clockFromScenarioMinute(minute: number, startMinuteOfDay: number): string {
  const total = Math.round(startMinuteOfDay + minute);
  const wrapped = ((total % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  return `${pad(Math.floor(wrapped / 60))}:${pad(wrapped % 60)}`;
}

/** Fraction of the simulated day that has passed, 0..1. */
export function dayProgress(tick: number): number {
  return Math.min(1, Math.max(0, tick / MINUTES_PER_DAY));
}

export function dateFromIso(iso: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(iso);
  return m ? m[1] : "";
}
