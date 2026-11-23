import { describe, expect, it } from "vitest";

import { hourFromIso, periodAt, tintAt, tintCss } from "./daylight";

describe("daylight", () => {
  it("reads the hour from an ISO timestamp", () => {
    expect(hourFromIso("2026-01-15T05:30:00")).toBeCloseTo(5.5);
    expect(hourFromIso("2026-01-15T23:15:00+05:30")).toBeCloseTo(23.25);
    expect(hourFromIso("nonsense")).toBe(12);
  });

  it("is strongest at night and faint at noon", () => {
    expect(tintAt(1).alpha).toBeGreaterThan(0.2);
    expect(tintAt(12).alpha).toBeLessThan(0.06);
  });

  it("changes smoothly and wraps around midnight", () => {
    expect(Math.abs(tintAt(23.99).alpha - tintAt(0).alpha)).toBeLessThan(0.01);
    expect(tintAt(7).alpha).toBeGreaterThan(tintAt(12).alpha);
    expect(tintAt(-1).alpha).toBeCloseTo(tintAt(23).alpha);
  });

  it("names the period", () => {
    expect([2, 6, 12, 19, 22].map(periodAt)).toEqual(["night", "dawn", "day", "dusk", "night"]);
  });

  it("makes a CSS colour", () => {
    expect(tintCss(2)).toMatch(/^rgba\(\d+, \d+, \d+, 0\.\d+\)$/);
  });
});
