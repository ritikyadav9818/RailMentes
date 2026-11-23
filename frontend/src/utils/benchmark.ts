/** Maths and table building for the 20-seed benchmark view. */
import type { BenchmarkMetric, BenchmarkRow, BenchmarkSummary, StrategyName } from "../api/types";

export const STRATEGY_ORDER: StrategyName[] = ["no_control", "fcfs", "priority", "cpsat"];
export const INTENSITY_ORDER = ["low", "medium", "high"];

export interface MetricInfo {
  id: BenchmarkMetric;
  label: string;
  unit: string;
  decimals: number;
  /** which direction is better; null = neither (a count of actions) */
  better: "lower" | "higher" | null;
}

export const METRICS: MetricInfo[] = [
  { id: "avg_delay_min", label: "Average delay", unit: "min", decimals: 2, better: "lower" },
  { id: "punctuality_pct", label: "Punctuality (<= 5 min late)", unit: "%", decimals: 1, better: "higher" },
  { id: "throughput_per_hour", label: "Throughput", unit: "trains/h", decimals: 2, better: "higher" },
  { id: "priority_weighted_delay", label: "Priority-weighted delay", unit: "", decimals: 0, better: "lower" },
  { id: "actions_applied", label: "Actions per day", unit: "", decimals: 1, better: null },
];

/** Two-sided 95% t values for 1..30 degrees of freedom; above 30 the normal value 1.96 is close enough. */
const T95 = [
  12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.16, 2.145, 2.131, 2.12, 2.11, 2.101, 2.093,
  2.086, 2.08, 2.074, 2.069, 2.064, 2.06, 2.056, 2.052, 2.048, 2.045, 2.042,
];

export function tValue95(runs: number): number {
  const df = runs - 1;
  if (df < 1) return Number.NaN;
  return df <= T95.length ? T95[df - 1] : 1.96;
}

/** Half width of the 95% interval of the mean: t * SD / sqrt(n). The SD is taken as the sample SD. */
export function ci95HalfWidth(std: number, runs: number): number {
  return runs > 1 ? (tValue95(runs) * std) / Math.sqrt(runs) : Number.NaN;
}

export interface Cell {
  mean: number;
  std: number;
  ciHalf: number;
  /** best value for this intensity and metric (lower / higher as the metric defines) */
  best: boolean;
}

export interface TableRow {
  intensity: string;
  strategy: StrategyName;
  runs: number;
  cells: Record<BenchmarkMetric, Cell>;
}

function intensitiesOf(rows: BenchmarkRow[]): string[] {
  return [...new Set(rows.map((r) => r.intensity))].sort((a, b) => INTENSITY_ORDER.indexOf(a) - INTENSITY_ORDER.indexOf(b));
}

function bestOf(rows: BenchmarkRow[], metric: MetricInfo): number | null {
  if (!metric.better || rows.length === 0) return null;
  const values = rows.map((r) => r.mean[metric.id]);
  return metric.better === "lower" ? Math.min(...values) : Math.max(...values);
}

/** Rows ordered by intensity then strategy, each cell with mean, SD, 95% interval and a best-in-group flag. */
export function buildTable(summary: BenchmarkSummary): TableRow[] {
  const out: TableRow[] = [];
  for (const intensity of intensitiesOf(summary.rows)) {
    const group = summary.rows.filter((r) => r.intensity === intensity);
    for (const strategy of STRATEGY_ORDER) {
      const row = group.find((r) => r.strategy === strategy);
      if (!row) continue;
      const cells = Object.fromEntries(
        METRICS.map((m) => {
          const mean = row.mean[m.id];
          // a metric where every strategy ties (throughput) has no winner
          const tie = group.every((r) => Math.abs(r.mean[m.id] - mean) < 10 ** -(m.decimals + 1));
          return [m.id, { mean, std: row.std[m.id], ciHalf: ci95HalfWidth(row.std[m.id], row.runs), best: !tie && bestOf(group, m) === mean }];
        }),
      ) as Record<BenchmarkMetric, Cell>;
      out.push({ intensity, strategy, runs: row.runs, cells });
    }
  }
  return out;
}

export type ErrorMode = "sd" | "ci";

export interface ChartPoint {
  intensity: string;
  [key: string]: number | string;
}

/** Recharts rows for one metric: one row per intensity; `<strategy>` = mean, `<strategy>_err` = error half width. */
export function chartData(summary: BenchmarkSummary, metric: BenchmarkMetric, mode: ErrorMode): ChartPoint[] {
  return intensitiesOf(summary.rows).map((intensity) => {
    const point: ChartPoint = { intensity };
    for (const row of summary.rows.filter((r) => r.intensity === intensity)) {
      point[row.strategy] = row.mean[metric];
      const err = mode === "sd" ? row.std[metric] : ci95HalfWidth(row.std[metric], row.runs);
      point[`${row.strategy}_err`] = Number.isFinite(err) ? err : 0;
    }
    return point;
  });
}

/** Relative change versus a reference value, in percent (negative = lower); null if the reference is 0. */
export function percentChange(value: number, reference: number): number | null {
  return reference === 0 ? null : ((value - reference) / reference) * 100;
}
