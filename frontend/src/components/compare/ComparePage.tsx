import { AlertCircle, FileQuestion, RefreshCw } from "lucide-react";
import { useState } from "react";

import type { BenchmarkVariant } from "../../api/types";
import { useBenchmark } from "../../hooks/useBenchmark";
import type { ErrorMode } from "../../utils/benchmark";
import { cn } from "../../utils/cn";
import { Button } from "../ui/button";
import { BenchmarkCharts, StrategyLegend } from "./BenchmarkCharts";
import { BenchmarkTable } from "./BenchmarkTable";
import { CaveatPanel } from "./CaveatPanel";
import { LiveKpis } from "./LiveKpis";

function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { id: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="flex rounded-md border border-white/10 p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={value === o.id}
          onClick={() => onChange(o.id)}
          className={cn(
            "rounded px-2.5 py-1 text-caption font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70",
            value === o.id ? "bg-accent/20 text-accent" : "text-muted hover:text-text",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function BenchmarkSkeleton() {
  return (
    <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3" aria-busy="true" aria-label="Loading benchmark">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-64 animate-pulse rounded-xl bg-white/[0.04]" />
      ))}
    </div>
  );
}

function Benchmark() {
  const [variant, setVariant] = useState<BenchmarkVariant>("ml");
  const [mode, setMode] = useState<ErrorMode>("sd");
  const { state, retry } = useBenchmark(variant);

  return (
    <section className="space-y-3" aria-label="20-seed benchmark">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-title font-semibold text-text">20-seed benchmark</h2>
          <p className="text-caption text-muted">
            Mean over 20 simulated days per cell (seeds 1-20); the bars show the spread across seeds. Saved results from <span className="font-mono">scripts/run_benchmark.py</span>.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented<BenchmarkVariant>
            label="Delay prediction used by the strategies"
            value={variant}
            onChange={setVariant}
            options={[
              { id: "ml", label: "With ML delay model" },
              { id: "persistence", label: "Without (persistence)" },
            ]}
          />
          <Segmented<ErrorMode>
            label="Error bars show"
            value={mode}
            onChange={setMode}
            options={[
              { id: "sd", label: "± 1 SD (spread)" },
              { id: "ci", label: "95% interval of the mean" },
            ]}
          />
        </div>
      </div>
      {state.phase === "loading" ? (
        <BenchmarkSkeleton />
      ) : state.phase === "error" ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4 text-body" role="alert">
          {state.missing ? <FileQuestion className="h-5 w-5 shrink-0 text-warn" aria-hidden="true" /> : <AlertCircle className="h-5 w-5 shrink-0 text-crit" aria-hidden="true" />}
          <span className="min-w-0 flex-1 text-text">{state.message}</span>
          <Button size="sm" onClick={retry}>
            <RefreshCw className="h-3.5 w-3.5" /> Try again
          </Button>
        </div>
      ) : (
        <>
          <p className="text-caption text-muted">
            {state.summary.label}. {state.summary.seeds} seeds per cell. Lower is better for delay; higher for punctuality and throughput.
          </p>
          <StrategyLegend />
          <BenchmarkCharts summary={state.summary} mode={mode} />
          <BenchmarkTable summary={state.summary} />
          <p className="text-caption text-muted">
            ± is one standard deviation across seeds. The bracket is the 95% interval of the mean (t-distribution), a measure of how well the mean is known, not of day-to-day spread. Differences smaller than the spread are not evidence of a real effect.
          </p>
        </>
      )}
    </section>
  );
}

/** Compare tab: caveats first, then the live scenario, then the saved 20-seed benchmark. */
export function ComparePage() {
  return (
    <div className="h-full overflow-y-auto" role="region" aria-label="Strategy comparison">
      <div className="mx-auto max-w-[1700px] space-y-6 p-4">
        <CaveatPanel />
        <LiveKpis />
        <Benchmark />
      </div>
    </div>
  );
}
