import { motion } from "framer-motion";
import { ChevronDown, CircleHelp, Command, Repeat, Sparkles, X } from "lucide-react";
import { useRef } from "react";

import { replaySameScenario, startGuidedDemo } from "../store/controls";
import { baselineAt, useHistoryStore } from "../store/useHistoryStore";
import { useRailStore } from "../store/useRailStore";
import { TABS, useUiStore, type Tab } from "../store/useUiStore";
import { cn } from "../utils/cn";
import { STRATEGIES } from "../utils/commands";
import { STRATEGY_LABELS } from "../utils/labels";
import { Button } from "./ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "./ui/dropdown-menu";

/** Stable ids so tabs and panels can point at each other. */
export const tabId = (t: Tab) => `tab-${t}`;
export const panelId = (t: Tab) => `panel-${t}`;

function Tabs() {
  const tab = useUiStore((s) => s.tab);
  const setTab = useUiStore((s) => s.setTab);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    const move = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!move) return;
    e.preventDefault();
    const next = TABS[(index + move + TABS.length) % TABS.length];
    setTab(next.id);
    refs.current[next.id]?.focus();
  };

  return (
    <div role="tablist" aria-label="Views" className="glass flex rounded-lg p-0.5">
      {TABS.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[t.id] = el;
          }}
          id={tabId(t.id)}
          role="tab"
          type="button"
          aria-selected={tab === t.id}
          aria-controls={panelId(t.id)}
          tabIndex={tab === t.id ? 0 : -1}
          onClick={() => setTab(t.id)}
          onKeyDown={(e) => onKeyDown(e, i)}
          title={`${t.label} ( ${t.key} )`}
          className={cn(
            "relative rounded-md px-3.5 py-1.5 text-body font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70",
            tab === t.id ? "text-text" : "text-muted hover:text-text",
          )}
        >
          {tab === t.id && <motion.span layoutId="tab-pill" className="absolute inset-0 rounded-md bg-accent/15 ring-1 ring-accent/40" transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
          <span className="relative">{t.label}</span>
        </button>
      ))}
    </div>
  );
}

/** Reset with the same seed, intensity and month and run a different strategy. */
function ReplayMenu() {
  const live = useRailStore((s) => s.dataSource === "live");
  const current = useRailStore((s) => s.snapshot?.strategy ?? "no_control");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={!live} title="Reset to the same day and run another strategy" aria-label="Replay same scenario">
          <Repeat className="h-4 w-4" />
          <span className="hidden xl:inline">Replay same day</span>
          <ChevronDown className="h-3.5 w-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Same seed and disruptions, with ...</DropdownMenuLabel>
        {STRATEGIES.filter((s) => s !== current).map((s) => (
          <DropdownMenuItem key={s} onSelect={() => void replaySameScenario(s)}>
            {STRATEGY_LABELS[s]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** After a replay: the earlier run's KPI at the same time of day next to the current one. */
function ReplayBanner() {
  const baseline = useHistoryStore((s) => s.baseline);
  const tick = useHistoryStore((s) => s.tick);
  const nowKpi = useHistoryStore((s) => s.kpiTrace.at(-1) ?? null);
  const strategy = useHistoryStore((s) => s.strategy);
  const dismiss = useHistoryStore((s) => s.dismissBaseline);
  if (!baseline || !strategy) return null;
  const before = baselineAt(baseline, tick);
  const delta = before && nowKpi ? nowKpi.avgDelay - before.avgDelay : null;
  return (
    <div className="glass flex min-w-0 items-center gap-2 rounded-lg px-3 py-1.5 text-caption" role="status" aria-label="Replay comparison">
      <Repeat className="h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
      <span className="min-w-0 truncate text-muted">
        Replay: <span className="text-text">{STRATEGY_LABELS[baseline.strategy]}</span> then <span className="text-text">{STRATEGY_LABELS[strategy]}</span>.
        {before && nowKpi ? (
          <>
            {" "}
            Average delay at this time of day: <span className="font-mono text-text">{before.avgDelay.toFixed(1)}</span> min before,{" "}
            <span className="font-mono text-text">{nowKpi.avgDelay.toFixed(1)}</span> now
            {delta !== null && Math.abs(delta) >= 0.05 && (
              <span className={cn("ml-1 font-mono", delta < 0 ? "text-ok" : "text-crit")}>
                ({delta > 0 ? "+" : ""}
                {delta.toFixed(1)})
              </span>
            )}
            .
          </>
        ) : (
          " The comparison appears as the day advances."
        )}
      </span>
      <button type="button" onClick={dismiss} aria-label="Dismiss replay comparison" className="rounded p-0.5 text-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/** Second row under the header: the three views, the replay comparison and the quick-action buttons. */
export function TabBar() {
  const live = useRailStore((s) => s.dataSource === "live");
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const setHelpOpen = useUiStore((s) => s.setHelpOpen);
  return (
    <div className="mx-2 mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
      <Tabs />
      <ReplayBanner />
      <div className="ml-auto flex items-center gap-1.5">
        <ReplayMenu />
        <Button variant="outline" disabled={!live} onClick={() => void startGuidedDemo()} title="Load a fixed scenario with captions" aria-label="Guided demo">
          <Sparkles className="h-4 w-4 text-accent" />
          <span className="hidden xl:inline">Guided demo</span>
        </Button>
        <Button variant="outline" onClick={() => setPaletteOpen(true)} title="Command palette ( Ctrl+K )" aria-label="Open command palette">
          <Command className="h-4 w-4" />
          <kbd className="hidden font-mono text-micro tracking-normal text-muted xl:inline">Ctrl K</kbd>
        </Button>
        <Button size="icon" variant="ghost" onClick={() => setHelpOpen(true)} title="Keyboard shortcuts ( ? )" aria-label="Keyboard shortcuts">
          <CircleHelp className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
