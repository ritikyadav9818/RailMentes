import { describe, expect, it } from "vitest";

import type { BenchmarkMetric, BenchmarkRow, BenchmarkSummary, StrategyName } from "../api/types";
import { METRICS, buildTable, chartData, ci95HalfWidth, percentChange, tValue95 } from "./benchmark";

function row(intensity: string, strategy: StrategyName, delay: number, over: Partial<Record<BenchmarkMetric, number>> = {}): BenchmarkRow {
  const mean = { avg_delay_min: delay, punctuality_pct: 60, throughput_per_hour: 0.93, priority_weighted_delay: delay * 70, actions_applied: 1, ...over };
  const std = { avg_delay_min: 2, punctuality_pct: 5, throughput_per_hour: 0.01, priority_weighted_delay: 150, actions_applied: 1 };
  return { intensity, strategy, runs: 20, mean, std };
}

const summary: BenchmarkSummary = {
  variant: "ml",
  label: "test",
  source_file: "x.csv",
  seeds: 20,
  disclaimer: "",
  rows: [
    // deliberately out of order
    row("medium", "cpsat", 12.6, { punctuality_pct: 59.4 }),
    row("low", "priority", 8.4, { punctuality_pct: 66.2 }),
    row("low", "no_control", 9.5, { punctuality_pct: 66, actions_applied: 0 }),
    row("low", "cpsat", 8.0, { punctuality_pct: 67.4 }),
    row("low", "fcfs", 9.3),
    row("medium", "no_control", 13.9),
  ],
};

describe("95% interval", () => {
  it("uses the t value for the number of seeds", () => {
    expect(tValue95(20)).toBeCloseTo(2.093);
    expect(tValue95(2)).toBeCloseTo(12.706);
    expect(tValue95(500)).toBe(1.96);
    expect(Number.isNaN(tValue95(1))).toBe(true);
  });

  it("is t * sd / sqrt(n)", () => {
    expect(ci95HalfWidth(2.79, 20)).toBeCloseTo((2.093 * 2.79) / Math.sqrt(20), 5);
    expect(Number.isNaN(ci95HalfWidth(2, 1))).toBe(true);
  });
});

describe("buildTable", () => {
  const table = buildTable(summary);

  it("orders rows by intensity, then strategy", () => {
    expect(table.map((r) => `${r.intensity}/${r.strategy}`)).toEqual([
      "low/no_control",
      "low/fcfs",
      "low/priority",
      "low/cpsat",
      "medium/no_control",
      "medium/cpsat",
    ]);
  });

  it("carries mean, sd and the interval for each cell", () => {
    const cell = table[3].cells.avg_delay_min;
    expect(cell.mean).toBe(8.0);
    expect(cell.std).toBe(2);
    expect(cell.ciHalf).toBeCloseTo((2.093 * 2) / Math.sqrt(20), 5);
  });

  it("marks the best value per intensity: lowest delay, highest punctuality", () => {
    const low = table.filter((r) => r.intensity === "low");
    expect(low.filter((r) => r.cells.avg_delay_min.best).map((r) => r.strategy)).toEqual(["cpsat"]);
    expect(low.filter((r) => r.cells.punctuality_pct.best).map((r) => r.strategy)).toEqual(["cpsat"]);
  });

  it("marks no winner where every strategy ties, or for the action count", () => {
    for (const r of table) {
      expect(r.cells.throughput_per_hour.best).toBe(false);
      expect(r.cells.actions_applied.best).toBe(false);
    }
  });

  it("has a cell for every metric", () => {
    for (const r of table) for (const m of METRICS) expect(r.cells[m.id]).toBeDefined();
  });
});

describe("chartData", () => {
  it("makes one row per intensity with a mean and an error per strategy", () => {
    const sd = chartData(summary, "avg_delay_min", "sd");
    expect(sd.map((p) => p.intensity)).toEqual(["low", "medium"]);
    expect(sd[0].cpsat).toBe(8.0);
    expect(sd[0].cpsat_err).toBe(2);
  });

  it("switches the error between SD and the 95% interval of the mean", () => {
    const ci = chartData(summary, "avg_delay_min", "ci");
    expect(ci[0].cpsat_err).toBeCloseTo((2.093 * 2) / Math.sqrt(20), 5);
    expect(ci[0].cpsat_err).toBeLessThan(2);
  });

  it("leaves out strategies that have no row", () => {
    expect(chartData(summary, "avg_delay_min", "sd")[1].fcfs).toBeUndefined();
  });
});

describe("percentChange", () => {
  it("is relative to the reference", () => {
    expect(percentChange(8, 10)).toBeCloseTo(-20);
    expect(percentChange(12, 10)).toBeCloseTo(20);
    expect(percentChange(5, 0)).toBeNull();
  });
});
