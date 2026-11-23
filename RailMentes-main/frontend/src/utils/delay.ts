/** Delay buckets used for train colours everywhere in the UI. */

export type DelayLevel = "on_time" | "minor" | "major" | "severe";

/** Upper bounds in minutes (inclusive). Punctuality in the KPIs also uses 5 min. */
export const DELAY_LIMITS = { onTime: 5, minor: 15, major: 30 } as const;

/** Same hex values as the Tailwind tokens ok / warn / major / crit (SVG needs raw colours). */
export const DELAY_COLORS: Record<DelayLevel, string> = {
  on_time: "#34d399",
  minor: "#f5a524",
  major: "#fb7c2d",
  severe: "#f04438",
};

export const DELAY_LABELS: Record<DelayLevel, string> = {
  on_time: "On time",
  minor: "Minor delay",
  major: "Major delay",
  severe: "Severe delay",
};

/** Early trains (negative delay) count as on time. */
export function delayLevel(delayMin: number): DelayLevel {
  if (delayMin <= DELAY_LIMITS.onTime) return "on_time";
  if (delayMin <= DELAY_LIMITS.minor) return "minor";
  if (delayMin <= DELAY_LIMITS.major) return "major";
  return "severe";
}

export function delayColor(delayMin: number): string {
  return DELAY_COLORS[delayLevel(delayMin)];
}

/** "+12 min", "on time", "3 min early" */
export function formatDelay(delayMin: number): string {
  const d = Math.round(delayMin);
  if (d === 0) return "on time";
  return d > 0 ? `+${d} min` : `${-d} min early`;
}
