import { Fragment } from "react";

import type { BenchmarkSummary } from "../../api/types";
import { METRICS, buildTable } from "../../utils/benchmark";
import { cn } from "../../utils/cn";
import { STRATEGY_LABELS } from "../../utils/labels";
import { STRATEGY_COLORS } from "./strategyColors";

/** Mean ± SD for every strategy and intensity, with the 95% interval of the mean underneath. Best value per group in bold. */
export function BenchmarkTable({ summary }: { summary: BenchmarkSummary }) {
  const rows = buildTable(summary);
  let lastIntensity = "";
  return (
    <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-panel/70">
      <table className="w-full min-w-[56rem] border-collapse text-body">
        <caption className="sr-only">Benchmark: mean and standard deviation over {summary.seeds} seeds</caption>
        <thead>
          <tr className="border-b border-white/10 text-left">
            <th scope="col" className="micro-label px-3 py-2">
              Strategy
            </th>
            {METRICS.map((m) => (
              <th key={m.id} scope="col" className="micro-label px-3 py-2 text-right">
                {m.label}
                {m.unit && <span className="ml-1 normal-case tracking-normal">({m.unit})</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const heading = row.intensity !== lastIntensity;
            lastIntensity = row.intensity;
            return (
              <Fragment key={`${row.intensity}-${row.strategy}`}>
                {heading && (
                  <tr className="bg-white/[0.03]">
                    <th scope="colgroup" colSpan={METRICS.length + 1} className="micro-label px-3 py-1.5 text-left text-accent">
                      {row.intensity} disruption intensity · {row.runs} seeds
                    </th>
                  </tr>
                )}
                <tr className="border-b border-white/[0.05] last:border-0">
                  <th scope="row" className="px-3 py-1.5 text-left font-medium text-text">
                    <span className="mr-2 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: STRATEGY_COLORS[row.strategy] }} aria-hidden="true" />
                    {STRATEGY_LABELS[row.strategy]}
                  </th>
                  {METRICS.map((m) => {
                    const c = row.cells[m.id];
                    return (
                      <td key={m.id} className={cn("px-3 py-1.5 text-right font-mono tabular-nums", c.best ? "font-semibold text-ok" : "text-text")}>
                        <div>
                          {c.mean.toFixed(m.decimals)} <span className="text-muted">± {c.std.toFixed(m.decimals)}</span>
                        </div>
                        <div className="text-caption font-normal text-muted" title="95% interval of the mean (t-distribution)">
                          {Number.isFinite(c.ciHalf)
                            ? `[${(c.mean - c.ciHalf).toFixed(m.decimals)}, ${(c.mean + c.ciHalf).toFixed(m.decimals)}]`
                            : "n/a"}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
