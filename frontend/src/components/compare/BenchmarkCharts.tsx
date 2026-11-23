import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BenchmarkMetric, BenchmarkSummary } from "../../api/types";
import { METRICS, STRATEGY_ORDER, chartData, type ErrorMode, type MetricInfo } from "../../utils/benchmark";
import { STRATEGY_LABELS } from "../../utils/labels";
import { STRATEGY_COLORS } from "./strategyColors";

const AXIS = { fill: "#8a9bb0", fontSize: 11 };

function MetricChart({ summary, metric, mode }: { summary: BenchmarkSummary; metric: MetricInfo; mode: ErrorMode }) {
  const data = chartData(summary, metric.id as BenchmarkMetric, mode);
  const hint = metric.better === "lower" ? "lower is better" : metric.better === "higher" ? "higher is better" : "count, not good or bad";
  return (
    <figure className="rounded-xl border border-white/[0.08] bg-panel/70 p-3" aria-label={`${metric.label} by strategy and disruption intensity`}>
      <figcaption className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-body font-medium text-text">
          {metric.label}
          {metric.unit && <span className="ml-1 font-mono text-caption text-muted">{metric.unit}</span>}
        </span>
        <span className="text-caption text-muted">{hint}</span>
      </figcaption>
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="#ffffff" strokeOpacity={0.07} />
            <XAxis dataKey="intensity" tick={AXIS} tickLine={false} axisLine={{ stroke: "#ffffff", strokeOpacity: 0.15 }} tickFormatter={(v: string) => `${v} disruption`} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={46} tickFormatter={(v: number) => String(Math.round(v * 100) / 100)} />
            <Tooltip
              cursor={{ fill: "#ffffff", fillOpacity: 0.05 }}
              contentStyle={{ background: "#0f161f", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#dbe4ee" }}
              formatter={(value, name, item) => {
                const err = (item?.payload as Record<string, number> | undefined)?.[`${String(item?.dataKey)}_err`] ?? 0;
                return [`${Number(value).toFixed(metric.decimals)} ± ${Number(err).toFixed(metric.decimals)}`, STRATEGY_LABELS[name as keyof typeof STRATEGY_LABELS] ?? String(name)];
              }}
            />
            {STRATEGY_ORDER.map((s) => (
              <Bar key={s} dataKey={s} fill={STRATEGY_COLORS[s]} radius={[3, 3, 0, 0]} isAnimationActive={false} name={s}>
                <ErrorBar dataKey={`${s}_err`} width={4} strokeWidth={1.4} stroke="#dbe4ee" />
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/** Colour key shared by all the charts. */
export function StrategyLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-caption text-muted" aria-label="Strategies">
      {STRATEGY_ORDER.map((s) => (
        <li key={s} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: STRATEGY_COLORS[s] }} aria-hidden="true" />
          {STRATEGY_LABELS[s]}
        </li>
      ))}
    </ul>
  );
}

/** One small bar chart per KPI: mean per strategy, grouped by disruption intensity, with error bars. */
export function BenchmarkCharts({ summary, mode }: { summary: BenchmarkSummary; mode: ErrorMode }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
      {METRICS.map((m) => (
        <MetricChart key={m.id} summary={summary} metric={m} mode={mode} />
      ))}
    </div>
  );
}
