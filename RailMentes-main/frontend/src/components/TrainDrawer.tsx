import { AnimatePresence, motion } from "framer-motion";
import { Gauge, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { DelayFactor, FeatureEffect, TrainState } from "../api/types";
import { useExplanation } from "../hooks/useExplanation";
import { useRailStore } from "../store/useRailStore";
import { useUiStore } from "../store/useUiStore";
import { cn } from "../utils/cn";
import { DELAY_LABELS, delayColor, delayLevel, formatDelay } from "../utils/delay";
import { CATEGORY_LABELS, STATUS_LABELS, featureLabel } from "../utils/labels";
import { clockFromScenarioMinute, scenarioStartMinuteOfDay } from "../utils/time";
import { TrainShape } from "./map/TrainShape";
import { PanelCollapseButton, SidePanel } from "./SidePanel";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

/** One horizontal bar: grows right (adds delay, amber/red) or left (saves delay, green) from a centre line. */
function EffectBar({ label, value, effect, max }: { label: string; value?: string; effect: number; max: number }) {
  const width = max > 0 ? (Math.abs(effect) / max) * 50 : 0;
  const positive = effect >= 0;
  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
      <span className="truncate text-xs text-text">
        {label}
        {value && <span className="ml-1.5 font-mono text-[11px] text-muted">{value}</span>}
      </span>
      <span className={cn("whitespace-nowrap text-right font-mono text-xs tabular-nums", positive ? "text-warn" : "text-ok")}>
        {positive ? "+" : ""}
        {effect.toFixed(1)} min
      </span>
      <div className="relative col-span-2 h-2 rounded-full bg-border/60">
        <span className="absolute inset-y-[-2px] left-1/2 w-px bg-muted/50" aria-hidden="true" />
        <motion.span
          className={cn("absolute inset-y-0 rounded-full", positive ? "bg-warn" : "bg-ok")}
          style={positive ? { left: "50%" } : { right: "50%" }}
          initial={{ width: 0 }}
          animate={{ width: `${width}%` }}
          transition={{ duration: 0.35, ease: "easeOut" }}
        />
      </div>
    </li>
  );
}

function Why({ train, live }: { train: TrainState; live: boolean }) {
  const [horizon, setHorizon] = useState(1);
  const stops = train.next_stations;
  const nextStation = stops[horizon - 1]?.station ?? stops[0]?.station ?? null;
  // the backend refuses trains that are off the line or have too few stations left; do not ask
  const askable = live && train.position !== null && stops.length >= horizon;
  const { state, reload } = useExplanation(train.id, horizon, nextStation, askable);

  const horizons = Math.min(3, stops.length);
  const effects: { label: string; value?: string; effect: number }[] =
    state.status === "ready"
      ? state.data.factors.map((f: FeatureEffect) => ({
          label: featureLabel(f.feature),
          value: f.value === null ? undefined : String(f.value),
          effect: f.effect_min,
        }))
      : train.delay_factors.map((f: DelayFactor) => ({ label: featureLabel(f.feature), effect: f.contribution_min }));
  const max = Math.max(0, ...effects.map((e) => Math.abs(e.effect)));

  return (
    <section aria-label="Why is this train late">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Why late?</h3>
        {live && (
          <Button size="icon" variant="ghost" className="ml-auto h-6 w-6" onClick={reload} aria-label="Refresh explanation">
            <RefreshCw className={cn("h-3 w-3", state.status === "loading" && "animate-spin")} />
          </Button>
        )}
      </div>

      {live && horizons > 1 && (
        <div className="mt-2 inline-flex rounded-md border border-border p-0.5" role="group" aria-label="Prediction horizon">
          {Array.from({ length: horizons }, (_, i) => i + 1).map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHorizon(h)}
              aria-pressed={horizon === h}
              className={cn(
                "rounded px-2 py-0.5 font-mono text-[11px] transition-colors",
                horizon === h ? "bg-accent/15 text-accent" : "text-muted hover:text-text",
              )}
            >
              {stops[h - 1]?.station ?? `+${h}`}
            </button>
          ))}
        </div>
      )}

      <div className="mt-3">
        {state.status === "loading" && (
          <div className="space-y-3" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-7 animate-pulse rounded bg-panel" />
            ))}
          </div>
        )}
        {state.status === "error" && (
          <p className="rounded-md border border-white/[0.07] bg-black/25 p-3 text-xs text-muted">
            {state.code === 503
              ? "The delay model is not loaded, so there is nothing to explain. Train it with scripts/train_model.py."
              : state.code === 400
                ? "This train is not on the line yet, or has no stations left to predict."
                : state.message}
          </p>
        )}
        {(state.status === "ready" || state.status === "idle") && (
          <>
            {effects.length > 0 ? (
              <ul className="space-y-3">
                {effects.map((e) => (
                  <EffectBar key={e.label} {...e} max={max} />
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted">No delay factors for this train right now.</p>
            )}
            {state.status === "ready" ? (
              <p className="mt-3 rounded-md border border-white/[0.07] bg-black/25 p-2.5 font-mono text-[11px] leading-relaxed text-muted">
                {state.data.station}: now {formatDelay(state.data.current_delay_min)} {" -> "}
                predicted {formatDelay(state.data.predicted_delay_min)}
                <br />
                = current {state.data.current_delay_min.toFixed(1)} + trend {state.data.expected_change_min.toFixed(1)} + factors{" "}
                {state.data.factors.reduce((a, f) => a + f.effect_min, 0).toFixed(1)} + other {state.data.other_effect_min.toFixed(1)}
                <br />
                <span className="text-muted/70">source: {state.data.model_source}</span>
              </p>
            ) : (
              <p className="mt-3 text-[11px] text-muted">{live ? "" : "Sample factors from the demo frame."}</p>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-white/[0.07] bg-black/25 px-2.5 py-1.5">
      <div className="micro-label">{label}</div>
      <div className="mt-0.5 text-body">{children}</div>
    </div>
  );
}

function PanelBody({ train }: { train: TrainState }) {
  const snapshot = useRailStore((s) => s.snapshot);
  const network = useRailStore((s) => s.network);
  const live = useRailStore((s) => s.dataSource === "live");
  const select = useRailStore((s) => s.selectTrain);
  const toggleOpen = useUiStore((s) => s.toggleTrain);
  const names = new Map(network?.stations.map((s) => [s.code, s.name]));
  const start = snapshot ? scenarioStartMinuteOfDay(snapshot.sim_time, snapshot.tick) : 0;
  const color = delayColor(train.delay_min);
  const pos = train.position;
  const where = pos?.at_station
    ? `At ${pos.at_station}`
    : pos?.block_id
      ? `On ${pos.block_id} (${pos.offset_km.toFixed(1)} km in)`
      : train.status === "finished"
        ? "Journey finished"
        : "Not on the line yet";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start gap-3 border-b border-white/[0.08] py-3 pl-4 pr-2">
        <svg width="30" height="30" viewBox="-14 -14 28 28" className="mt-0.5 shrink-0" aria-hidden="true">
          <TrainShape category={train.category} color={color} />
        </svg>
        <div className="min-w-0">
          <h2 className="font-mono text-title font-semibold leading-tight">{train.id}</h2>
          <p className="truncate text-body text-muted">{train.name}</p>
        </div>
        <div className="ml-auto flex items-center">
          <PanelCollapseButton side="right" onToggle={toggleOpen} shortcut="]" label="train panel" />
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => select(null)} aria-label="Close train details" title="Close ( Esc )">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Delay">
            <span className="font-mono font-semibold" style={{ color }}>
              {formatDelay(train.delay_min)}
            </span>
            {delayLevel(train.delay_min) !== "on_time" && (
              <span className="block text-caption text-muted">{DELAY_LABELS[delayLevel(train.delay_min)]}</span>
            )}
          </Stat>
          <Stat label="Status">{STATUS_LABELS[train.status] ?? train.status}</Stat>
          <Stat label="Type">
            {CATEGORY_LABELS[train.category]} <span className="text-muted">· priority {train.priority}</span>
          </Stat>
          <Stat label="Speed">
            <span className="inline-flex items-center gap-1 font-mono">
              <Gauge className="h-3.5 w-3.5 text-muted" />
              {Math.round(train.speed_kmph)} km/h
            </span>
          </Stat>
        </div>
        <p className="font-mono text-xs text-muted">{where}</p>

        <section aria-label="Route">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Next stations</h3>
          {train.next_stations.length === 0 ? (
            <p className="text-xs text-muted">No stations left on this train's route.</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="pb-1 font-medium">Station</th>
                  <th className="pb-1 text-right font-medium">Sched.</th>
                  <th className="pb-1 text-right font-medium">Pred.</th>
                  <th className="pb-1 text-right font-medium">Late</th>
                </tr>
              </thead>
              <tbody>
                {train.next_stations.map((stop) => {
                  const diff = stop.predicted_min - stop.scheduled_min;
                  return (
                    <tr key={stop.station} className="border-t border-white/[0.06]">
                      <td className="py-1.5">
                        <span className="font-mono font-semibold">{stop.station}</span>
                        <span className="ml-1.5 text-muted">{names.get(stop.station)}</span>
                        {!stop.will_stop && <Badge className="ml-1.5">pass</Badge>}
                      </td>
                      <td className="py-1.5 text-right font-mono tabular-nums text-muted">{clockFromScenarioMinute(stop.scheduled_min, start)}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{clockFromScenarioMinute(stop.predicted_min, start)}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums" style={{ color: delayColor(diff) }}>
                        {diff > 0 ? `+${Math.round(diff)}` : Math.round(diff)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <Why key={train.id} train={train} live={live} />
      </div>
    </div>
  );
}

/** Right side panel for the selected train. Esc or the close button dismisses it; the chevron collapses it to a rail. */
export function TrainDrawer() {
  const selectedId = useRailStore((s) => s.selectedTrainId);
  const train = useRailStore((s) => s.snapshot?.trains.find((t) => t.id === selectedId));
  const select = useRailStore((s) => s.selectTrain);
  const open = useUiStore((s) => s.trainOpen);
  const setOpen = useUiStore((s) => s.setTrainOpen);
  const toggle = useUiStore((s) => s.toggleTrain);

  // picking a train always shows its details, even if the panel was collapsed before
  useEffect(() => {
    if (selectedId) setOpen(true);
  }, [selectedId, setOpen]);

  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && select(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, select]);

  return (
    <AnimatePresence>
      {selectedId && (
        <SidePanel
          key="train-panel"
          side="right"
          open={open}
          width={324}
          icon={Gauge}
          label="train panel"
          ariaLabel={`Train ${selectedId}`}
          railTitle={selectedId}
          shortcut="]"
          onToggle={toggle}
          railExtra={
            train ? (
              <svg width="22" height="22" viewBox="-14 -14 28 28" aria-hidden="true">
                <TrainShape category={train.category} color={delayColor(train.delay_min)} />
              </svg>
            ) : null
          }
        >
          {train ? (
            <PanelBody train={train} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-body text-muted">
              <p>
                Train <span className="font-mono text-text">{selectedId}</span> is not in the current frame.
              </p>
              <Button size="sm" onClick={() => select(null)}>
                Close
              </Button>
            </div>
          )}
        </SidePanel>
      )}
    </AnimatePresence>
  );
}
