import { AlertCircle, Loader2, RefreshCw, WifiOff } from "lucide-react";

import type { KpiReport, StrategyName } from "../../api/types";
import { useLiveKpis } from "../../hooks/useLiveKpis";
import { useRailStore } from "../../store/useRailStore";
import { percentChange, STRATEGY_ORDER } from "../../utils/benchmark";
import { cn } from "../../utils/cn";
import { STRATEGY_LABELS } from "../../utils/labels";
import { Button } from "../ui/button";
import { STRATEGY_COLORS } from "./strategyColors";

function Skeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="Loading KPIs">
      {STRATEGY_ORDER.map((s) => (
        <div key={s} className="h-36 animate-pulse rounded-xl bg-white/[0.04]" />
      ))}
    </div>
  );
}

function Computing({ done, total, names, waitedS }: { done: number; total: number; names: string[]; waitedS: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/[0.06] p-4" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-body text-text">
        <Loader2 className="h-4 w-4 animate-spin text-accent" aria-hidden="true" />
        Simulating the full day under each strategy in the background ({done} of {total} done)
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Strategies finished">
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${Math.max(6, pct)}%` }} />
      </div>
      <p className="mt-2 text-caption text-muted">
        {names.length > 0 ? `Finished: ${names.map((n) => STRATEGY_LABELS[n as StrategyName] ?? n).join(", ")}. ` : ""}
        This takes about 10 seconds without the delay model and 1-2 minutes with it; waited {waitedS} s so far. The live simulation is not slowed.
      </p>
    </div>
  );
}

function Cards({ report, current }: { report: KpiReport; current: StrategyName | null }) {
  const base = report.no_control;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {STRATEGY_ORDER.map((s) => {
        const k = report[s];
        if (!k) return null;
        const change = base && s !== "no_control" ? percentChange(k.avg_delay_min, base.avg_delay_min) : null;
        return (
          <article
            key={s}
            className={cn("rounded-xl border bg-panel/70 p-3", current === s ? "border-accent/60 shadow-glow" : "border-white/[0.08]")}
            aria-label={`${STRATEGY_LABELS[s]} KPIs`}
          >
            <header className="flex items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-body font-medium text-text">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: STRATEGY_COLORS[s] }} aria-hidden="true" />
                {STRATEGY_LABELS[s]}
              </h3>
              {current === s && <span className="micro-label text-accent">running</span>}
            </header>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="font-mono text-display font-semibold text-text">{k.avg_delay_min.toFixed(1)}</span>
              <span className="font-mono text-caption text-muted">min avg delay</span>
            </div>
            <div className="h-5 text-caption" aria-live="off">
              {change !== null && (
                <span className={cn("font-mono", change < -0.05 ? "text-ok" : change > 0.05 ? "text-crit" : "text-muted")}>
                  {change > 0 ? "+" : ""}
                  {change.toFixed(1)}% vs no control
                </span>
              )}
            </div>
            <dl className="mt-1 grid grid-cols-3 gap-1 text-caption">
              <div>
                <dt className="text-muted">Punctual</dt>
                <dd className="font-mono text-text">{k.punctuality_pct.toFixed(0)}%</dd>
              </div>
              <div>
                <dt className="text-muted">Trains/h</dt>
                <dd className="font-mono text-text">{k.throughput_per_hour.toFixed(2)}</dd>
              </div>
              <div>
                <dt className="text-muted">Avoided</dt>
                <dd className="font-mono text-text" title="Real waits avoided versus no control">
                  {k.conflicts_avoided}
                </dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

/** Full-day KPIs of all four strategies for the scenario that is loaded now (GET /kpis, polled while it computes). */
export function LiveKpis() {
  const live = useRailStore((s) => s.dataSource === "live");
  const settings = useRailStore((s) => s.settings);
  const current = useRailStore((s) => s.snapshot?.strategy ?? null);
  const { state, retry } = useLiveKpis(live);

  return (
    <section className="space-y-3" aria-label="Live KPIs for the current scenario">
      <div>
        <h2 className="text-title font-semibold text-text">This scenario, all four strategies</h2>
        <p className="text-caption text-muted">
          Seed {settings.seed}, {settings.intensity === "none" ? "no" : settings.intensity} random disruptions. Each strategy ran the same full day headless, applying every recommendation it made.
        </p>
      </div>
      {!live ? (
        <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4 text-body text-muted" role="status">
          <WifiOff className="h-5 w-5 shrink-0" aria-hidden="true" />
          The backend is offline, so there is no live comparison. Start it (see the README) and this fills in by itself.
        </div>
      ) : state.phase === "loading" ? (
        <Skeleton />
      ) : state.phase === "computing" ? (
        <Computing done={state.done} total={state.total} names={state.doneNames} waitedS={state.waitedS} />
      ) : state.phase === "error" ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-crit/40 bg-crit/[0.07] p-4 text-body" role="alert">
          <AlertCircle className="h-5 w-5 shrink-0 text-crit" aria-hidden="true" />
          <span className="min-w-0 flex-1 text-text">{state.message}</span>
          <Button size="sm" onClick={retry}>
            <RefreshCw className="h-3.5 w-3.5" /> Try again
          </Button>
        </div>
      ) : (
        <Cards report={state.report} current={current} />
      )}
    </section>
  );
}
