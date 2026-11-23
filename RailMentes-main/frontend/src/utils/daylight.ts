/** Day / night tint for the map, driven by the simulation clock. Pure functions. */

export type DayPeriod = "night" | "dawn" | "day" | "dusk";

interface Key {
  hour: number;
  rgb: [number, number, number];
  alpha: number;
}

/** Tint at fixed hours; in between it is interpolated. Night is a deep blue, dawn and dusk a warm wash. */
const KEYS: Key[] = [
  { hour: 0, rgb: [22, 44, 120], alpha: 0.26 },
  { hour: 4.5, rgb: [22, 44, 120], alpha: 0.24 },
  { hour: 6, rgb: [255, 150, 80], alpha: 0.1 },
  { hour: 8, rgb: [150, 190, 235], alpha: 0.035 },
  { hour: 16, rgb: [150, 190, 235], alpha: 0.035 },
  { hour: 18.5, rgb: [255, 130, 70], alpha: 0.11 },
  { hour: 20.5, rgb: [40, 52, 135], alpha: 0.2 },
  { hour: 22, rgb: [22, 44, 120], alpha: 0.26 },
  { hour: 24, rgb: [22, 44, 120], alpha: 0.26 },
];

/** Hour of day (0 to 24, fractional) from an ISO timestamp such as "2026-01-15T05:30:00". */
export function hourFromIso(iso: string): number {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? Number(m[1]) + Number(m[2]) / 60 : 12;
}

export function tintAt(hour: number): { rgb: [number, number, number]; alpha: number } {
  const h = ((hour % 24) + 24) % 24;
  const next = KEYS.findIndex((k) => k.hour >= h);
  const b = KEYS[Math.max(next, 1)];
  const a = KEYS[Math.max(next, 1) - 1];
  const t = b.hour === a.hour ? 0 : (h - a.hour) / (b.hour - a.hour);
  const mix = (x: number, y: number) => x + (y - x) * t;
  return {
    rgb: [Math.round(mix(a.rgb[0], b.rgb[0])), Math.round(mix(a.rgb[1], b.rgb[1])), Math.round(mix(a.rgb[2], b.rgb[2]))],
    alpha: mix(a.alpha, b.alpha),
  };
}

export function tintCss(hour: number): string {
  const { rgb, alpha } = tintAt(hour);
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha.toFixed(3)})`;
}

export function periodAt(hour: number): DayPeriod {
  const h = ((hour % 24) + 24) % 24;
  if (h >= 21 || h < 5) return "night";
  if (h < 8) return "dawn";
  if (h < 17.5) return "day";
  return "dusk";
}
