import { describe, expect, it } from "vitest";

import {
  MAX_SLIDE_MS,
  MIN_SLIDE_MS,
  clamp,
  distance,
  lerp,
  lerpPoint,
  shouldSnap,
  slideDuration,
  slideProgress,
  smoothInterval,
} from "./interpolate";

describe("lerp", () => {
  it("returns the ends at t = 0 and t = 1 and the middle at 0.5", () => {
    expect(lerp(10, 20, 0)).toBe(10);
    expect(lerp(10, 20, 1)).toBe(20);
    expect(lerp(10, 20, 0.5)).toBe(15);
  });

  it("interpolates points per axis", () => {
    expect(lerpPoint({ x: 0, y: 10 }, { x: 100, y: 0 }, 0.25)).toEqual({ x: 25, y: 7.5 });
  });

  it("measures distance", () => {
    expect(distance({ x: 0, y: 0 }, { x: 3, y: 4 })).toBe(5);
  });
});

describe("slideProgress", () => {
  it("runs from 0 to 1 over the duration and then stays at 1", () => {
    expect(slideProgress(1000, 1000, 500)).toBe(0);
    expect(slideProgress(1250, 1000, 500)).toBe(0.5);
    expect(slideProgress(1500, 1000, 500)).toBe(1);
    expect(slideProgress(9000, 1000, 500)).toBe(1);
  });

  it("never goes negative and treats a zero duration as finished", () => {
    expect(slideProgress(900, 1000, 500)).toBe(0);
    expect(slideProgress(1000, 1000, 0)).toBe(1);
  });
});

describe("a train sliding between two snapshots", () => {
  it("moves at constant speed and restarts from where the marker is", () => {
    const a = { x: 0, y: 0 };
    const b = { x: 100, y: 0 };
    const mid = lerpPoint(a, b, slideProgress(1100, 1000, 200));
    expect(mid.x).toBe(50);
    // next snapshot arrives half-way: the slide starts from the current position, no jump
    const c = { x: 160, y: 0 };
    const restarted = lerpPoint(mid, c, slideProgress(1100, 1100, 200));
    expect(restarted).toEqual(mid);
  });
});

describe("smoothInterval", () => {
  it("starts with the first measurement and then averages", () => {
    expect(smoothInterval(null, 100)).toBe(100);
    expect(smoothInterval(100, 200)).toBeCloseTo(140);
  });

  it("ignores stalls (pause, background tab) and silly values", () => {
    expect(smoothInterval(100, 60_000)).toBe(100);
    expect(smoothInterval(100, 1)).toBe(100);
    expect(smoothInterval(null, 60_000)).toBeNull();
  });
});

describe("slideDuration", () => {
  it("uses the measured interval when there is one", () => {
    expect(slideDuration(123, 5)).toBe(123);
  });

  it("falls back to the speed setting: 1000 ms divided by ticks per second", () => {
    expect(slideDuration(null, 4)).toBe(250);
    expect(slideDuration(null, 0.5)).toBe(2000);
  });

  it("stays within the allowed range at every speed from 0.5 to 20", () => {
    for (const speed of [0.5, 1, 5, 20, 1000]) {
      const d = slideDuration(null, speed);
      expect(d).toBeGreaterThanOrEqual(MIN_SLIDE_MS);
      expect(d).toBeLessThanOrEqual(MAX_SLIDE_MS);
    }
    expect(clamp(5, 0, 1)).toBe(1);
  });
});

describe("shouldSnap", () => {
  it("snaps on the first frame, on reset (tick goes back) and on big jumps", () => {
    expect(shouldSnap(null, 10)).toBe(true);
    expect(shouldSnap(50, 3)).toBe(true);
    expect(shouldSnap(10, 40)).toBe(true);
  });

  it("slides for the next tick or a repeated one", () => {
    expect(shouldSnap(10, 11)).toBe(false);
    expect(shouldSnap(10, 10)).toBe(false);
    expect(shouldSnap(10, 15)).toBe(false);
  });
});
