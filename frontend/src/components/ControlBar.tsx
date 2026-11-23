import { ChevronDown, Cpu, Pause, Play, RotateCcw, SlidersHorizontal, Zap } from "lucide-react";
import { useState } from "react";

import type { Intensity, StrategyName } from "../api/types";
import { commitSpeed, commitStrategy, pauseSimulation, resetSimulation, startSimulation } from "../store/controls";
import { SPEED_MAX, SPEED_MIN, useRailStore } from "../store/useRailStore";
import { useUiStore } from "../store/useUiStore";
import { DISRUPTION_LABELS, STRATEGY_LABELS } from "../utils/labels";
import { InjectDialog, type InjectKind } from "./InjectDialog";
import { Button } from "./ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Slider } from "./ui/slider";

const INTENSITIES: Intensity[] = ["none", "low", "medium", "high"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const STRATEGIES = Object.keys(STRATEGY_LABELS) as StrategyName[];
const INJECTABLE: InjectKind[] = ["fog", "signal_failure", "block_closure", "late_departure"];

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="micro-label mb-1">{label}</div>
      {children}
    </div>
  );
}

/** Seed, intensity and month: they take effect on the next reset, so they live in a popover. */
function ScenarioPopover({ live }: { live: boolean }) {
  const settings = useRailStore((s) => s.settings);
  const update = useRailStore((s) => s.updateSettings);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" disabled={!live} title="Scenario settings (applied on reset)" aria-label="Scenario settings">
          <SlidersHorizontal className="h-4 w-4" />
          <span className="hidden 2xl:inline">Scenario</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72">
        <p className="mb-3 text-caption text-muted">Applied the next time you press reset.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Seed">
            <input
              type="number"
              aria-label="Seed"
              title="Random seed: the same seed gives the same day"
              value={settings.seed}
              min={0}
              onChange={(e) => update({ seed: Math.max(0, Math.trunc(Number(e.target.value) || 0)) })}
              className="h-8 w-full rounded-md border border-white/10 bg-raised/80 px-2 font-mono text-body text-text transition-colors hover:border-accent/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
            />
          </Field>
          <Field label="Month">
            <Select value={String(settings.month)} onValueChange={(v) => update({ month: Number(v) })}>
              <SelectTrigger className="w-full" aria-label="Month">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MONTHS.map((m, i) => (
                  <SelectItem key={m} value={String(i + 1)}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Disruption intensity" className="col-span-2">
            <Select value={settings.intensity} onValueChange={(v) => update({ intensity: v as Intensity })}>
              <SelectTrigger className="w-full" aria-label="Disruption intensity">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {INTENSITIES.map((i) => (
                  <SelectItem key={i} value={i}>
                    {i === "none" ? "No disruptions" : `${i[0].toUpperCase()}${i.slice(1)}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** Start / pause / reset, speed, strategy, scenario settings and the inject-disruption menu, in one compact row. */
export function ControlBar() {
  const settings = useRailStore((s) => s.settings);
  const update = useRailStore((s) => s.updateSettings);
  const running = useRailStore((s) => s.snapshot?.running ?? false);
  const live = useRailStore((s) => s.dataSource === "live");
  const [busy, setBusy] = useState(false);
  const injectKind = useUiStore((s) => s.injectKind);
  const setInjectKind = useUiStore((s) => s.setInjectKind);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    await fn();
    setBusy(false);
  };
  const off = !live || busy;
  const offlineHint = live ? undefined : "Backend offline: controls are disabled";

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2" title={offlineHint}>
      <div className="flex items-center gap-1.5">
        {running ? (
          <Button variant="outline" className="w-[5.25rem]" disabled={off} onClick={() => void run(pauseSimulation)}>
            <Pause className="h-4 w-4" /> Pause
          </Button>
        ) : (
          <Button variant="default" className="w-[5.25rem]" disabled={off} onClick={() => void run(startSimulation)}>
            <Play className="h-4 w-4" /> Start
          </Button>
        )}
        <Button size="icon" variant="outline" disabled={off} onClick={() => void run(resetSimulation)} aria-label="Reset" title="Reset the day with the scenario settings">
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex w-32 items-center gap-2" title="Simulated minutes per real second">
        <span className="micro-label">Speed</span>
        <Slider
          aria-label="Simulation speed"
          min={SPEED_MIN}
          max={SPEED_MAX}
          step={0.5}
          value={[settings.speed]}
          disabled={!live}
          onValueChange={([v]) => update({ speed: v })}
          onValueCommit={([v]) => void commitSpeed(v)}
        />
        <span className="w-9 text-right font-mono text-caption text-text">{settings.speed}x</span>
      </div>

      <Select
        value={settings.strategy}
        disabled={!live}
        onValueChange={(v) => {
          update({ strategy: v as StrategyName });
          void commitStrategy();
        }}
      >
        <SelectTrigger className="w-48" aria-label="Strategy" title="Control strategy">
          <Cpu className="h-4 w-4 shrink-0 text-accent" />
          <span className="min-w-0 flex-1 truncate text-left">
            <SelectValue />
          </span>
        </SelectTrigger>
        <SelectContent>
          {STRATEGIES.map((s) => (
            <SelectItem key={s} value={s}>
              {STRATEGY_LABELS[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <ScenarioPopover live={live} />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="warn" disabled={!live}>
            <Zap className="h-4 w-4" /> Inject <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>Inject now</DropdownMenuLabel>
          {INJECTABLE.map((k) => (
            <DropdownMenuItem key={k} onSelect={() => setInjectKind(k)}>
              {DISRUPTION_LABELS[k]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <InjectDialog kind={injectKind} onClose={() => setInjectKind(null)} />
    </div>
  );
}
