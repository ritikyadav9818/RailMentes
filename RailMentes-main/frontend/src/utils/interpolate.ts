/** Maths for smooth train motion between two snapshots. Pure functions, no DOM. */

export interface Point {
  x: number;
  y: number;
}

/** Shortest and longest time we allow one snapshot-to-snapshot slide to take. */
export const MIN_SLIDE_MS = 40;
export const MAX_SLIDE_MS = 2500;
/** If more ticks than this go by between two frames we jump instead of sliding. */
export const MAX_SLIDE_TICKS = 5;

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function lerpPoint(a: Point, b: Point, t: number): Point {
  return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) };
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** Fraction (0..1) of a slide that has elapsed. A zero-length slide is already finished. */
export function slideProgress(now: number, startedAt: number, durationMs: number): number {
  if (durationMs <= 0) return 1;
  return clamp((now - startedAt) / durationMs, 0, 1);
}

/**
 * Smooth the measured time between snapshots (exponential moving average).
 * Gaps outside the allowed range (pause, tab in background) are ignored so one stall
 * does not stretch every later slide.
 */
export function smoothInterval(previousMs: number | null, gapMs: number): number | null {
  if (gapMs < MIN_SLIDE_MS || gapMs > MAX_SLIDE_MS) return previousMs;
  if (previousMs === null) return gapMs;
  return 0.6 * previousMs + 0.4 * gapMs;
}

/** Slide duration to use: the smoothed interval, or a guess from the speed setting, kept in range. */
export function slideDuration(smoothedMs: number | null, ticksPerSecond: number): number {
  const guess = ticksPerSecond > 0 ? 1000 / ticksPerSecond : 1000;
  return clamp(smoothedMs ?? guess, MIN_SLIDE_MS, MAX_SLIDE_MS);
}

/** A reset (tick goes back) or a big jump forward means: place trains directly, no sliding. */
export function shouldSnap(previousTick: number | null, tick: number): boolean {
  if (previousTick === null) return true;
  return tick < previousTick || tick - previousTick > MAX_SLIDE_TICKS;
}
