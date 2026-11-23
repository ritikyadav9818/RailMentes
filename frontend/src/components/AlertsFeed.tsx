import { AnimatePresence, motion } from "framer-motion";
import { BellRing, CheckCircle2, Undo2 } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import type { Action, Severity } from "../api/types";
import { decideRecommendation } from "../store/controls";
import { useRailStore } from "../store/useRailStore";
import { useUiStore } from "../store/useUiStore";
import { cn } from "../utils/cn";
import { buildFeed, type FeedItem } from "../utils/feed";
import { CONFLICT_LABELS, STRATEGY_LABELS } from "../utils/labels";
import { clockFromScenarioMinute, scenarioStartMinuteOfDay } from "../utils/time";
import { Badge } from "./ui/badge";
import { PanelCollapseButton, SidePanel } from "./SidePanel";
import { Button } from "./ui/button";

const SEVERITY_TONE: Record<Severity, "neutral" | "accent" | "warn" | "crit"> = {
  low: "neutral",
  medium: "accent",
  high: "warn",
  critical: "crit",
};
const SEVERITY_BAR: Record<Severity, string> = {
  low: "bg-muted",
  medium: "bg-accent",
  high: "bg-warn",
  critical: "bg-crit",
};

function actionSummary(a: Action): string {
  return a.kind === "hold"
    ? `Hold ${a.train_id} at ${a.at_station} for ${a.hold_minutes ?? "?"} min`
    : `${a.train_id} yields to ${a.other_train_id ?? "?"} at ${a.at_station}`;
}

function TrainChip({ id }: { id: string }) {
  const selectTrain = useRailStore((s) => s.selectTrain);
  return (
    <button
      type="button"
      onClick={() => selectTrain(id)}
      className="rounded border border-white/10 bg-black/30 px-1.5 py-0.5 font-mono text-caption text-text transition-colors hover:border-accent/60 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
    >
      {id}
    </button>
  );
}

/**
 * One list row. Enter and exit animate the row's height and opacity (no transforms), and the gap is
 * padding inside the row, not a margin between rows, so normal document flow moves the neighbours with the row.
 * There is deliberately no Framer `layout` prop: its transform-based position correction fights a height
 * animation and made cards overlap. A reorder therefore snaps into place instead of gliding.
 */
function FeedRow({ gap, children }: { gap: string; children: ReactNode }) {
  return (
    <motion.li
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0, transition: { duration: 0.18 } }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className={cn("overflow-hidden", gap)}
    >
      {children}
    </motion.li>
  );
}

function Card({ item, startMinute }: { item: FeedItem; startMinute: number }) {
  const [busy, setBusy] = useState(false);
  const live = useRailStore((s) => s.dataSource === "live");
  const rec = item.recommendation;
  const conflict = item.conflicts[0];
  const open = rec !== null && (rec.status === "proposed" || rec.status === "undone");

  const decide = async (decision: "apply" | "ignore" | "undo") => {
    if (!rec) return;
    setBusy(true);
    await decideRecommendation(rec, decision);
    setBusy(false);
  };

  return (
    <FeedRow gap="pb-3">
      <div
        className={cn("relative overflow-hidden rounded-lg border border-white/[0.08] bg-white/[0.035] p-3 pl-4 transition-colors hover:border-white/20", rec && !open && "opacity-70")}
      >
      <span className={cn("absolute inset-y-0 left-0 w-1", SEVERITY_BAR[item.severity])} aria-hidden="true" />
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEVERITY_TONE[item.severity]}>{item.severity.toUpperCase()}</Badge>
        {conflict && <span className="text-xs font-medium text-text">{CONFLICT_LABELS[conflict.kind]}</span>}
        {conflict && (
          <span className="ml-auto font-mono text-[11px] text-muted">
            {conflict.location} · {clockFromScenarioMinute(conflict.time_min, startMinute)}
          </span>
        )}
      </div>

      {conflict && <p className="mt-1.5 text-[13px] leading-snug text-text/90">{conflict.description}</p>}
      {item.conflicts.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted">Trains</span>
          {[...new Set(item.conflicts.flatMap((c) => c.train_ids))].map((id) => (
            <TrainChip key={id} id={id} />
          ))}
        </div>
      )}

      {rec ? (
        <div className="mt-2.5 rounded-md border border-white/[0.07] bg-black/25 p-2.5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-accent">{STRATEGY_LABELS[rec.strategy]}</span>
            {rec.expected_delay_saved_min > 0 && (
              <Badge tone="ok" className="ml-auto">
                saves ~{rec.expected_delay_saved_min.toFixed(1)} min
              </Badge>
            )}
          </div>
          <p className="mt-1 font-mono text-xs font-medium text-text">{actionSummary(rec.action)}</p>
          <p className="mt-1 text-xs leading-snug text-muted">{rec.action.reason}</p>
          <div className="mt-2.5 flex items-center gap-2">
            {open ? (
              <>
                <Button size="sm" variant="default" disabled={busy || !live} onClick={() => void decide("apply")}>
                  Apply
                </Button>
                <Button size="sm" variant="ghost" disabled={busy || !live} onClick={() => void decide("ignore")}>
                  Ignore
                </Button>
              </>
            ) : (
              <>
                <Badge tone={rec.status === "applied" ? "ok" : "neutral"}>{rec.status}</Badge>
                {rec.status === "ignored" && (
                  <Button size="sm" variant="ghost" disabled={busy || !live} onClick={() => void decide("undo")}>
                    <Undo2 className="h-3 w-3" /> Undo
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-muted">No recommendation from the current strategy.</p>
      )}
      </div>
    </FeedRow>
  );
}

function Handled({ item }: { item: FeedItem }) {
  const rec = item.recommendation;
  if (!rec) return null;
  return (
    <FeedRow gap="pb-1.5">
      <div className="flex items-center gap-2 text-xs text-muted">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate font-mono">{actionSummary(rec.action)}</span>
        <Badge tone={rec.status === "applied" ? "ok" : "neutral"} className="ml-auto shrink-0">
          {rec.status}
        </Badge>
      </div>
    </FeedRow>
  );
}

function useFeed() {
  const snapshot = useRailStore((s) => s.snapshot);
  return useMemo(() => (snapshot ? buildFeed(snapshot.conflicts, snapshot.recommendations) : null), [snapshot]);
}

function FeedBody() {
  const snapshot = useRailStore((s) => s.snapshot);
  const live = useRailStore((s) => s.dataSource === "live");
  const feed = useFeed();
  const startMinute = snapshot ? scenarioStartMinuteOfDay(snapshot.sim_time, snapshot.tick) : 0;

  if (!feed || !snapshot) {
    return (
      <div className="space-y-3" aria-busy="true">
        {[0, 1].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-lg bg-white/5" />
        ))}
      </div>
    );
  }
  return (
    <>
      {feed.active.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-10 text-center text-body text-muted">
          <CheckCircle2 className="h-6 w-6 text-ok" />
          <p>No conflicts expected in the next 60 minutes.</p>
          {!snapshot.running && <p className="text-caption">Press Start to run the simulation.</p>}
        </div>
      )}
      <ul>
        <AnimatePresence initial={false}>
          {feed.active.map((item) => (
            <Card key={item.key} item={item} startMinute={startMinute} />
          ))}
        </AnimatePresence>
      </ul>
      {feed.handled.length > 0 && (
        <div className="mt-5">
          <h3 className="micro-label mb-2">Recently handled</h3>
          <ul>
            <AnimatePresence initial={false}>
              {feed.handled.map((item) => (
                <Handled key={item.key} item={item} />
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
      {!live && <p className="mt-4 text-caption text-muted">Demo data: Apply and Ignore need the live backend.</p>}
    </>
  );
}

/** Left side panel: conflicts the detector expects, with the strategy's recommendation and Apply / Ignore. */
export function AlertsPanel() {
  const open = useUiStore((s) => s.alertsOpen);
  const toggle = useUiStore((s) => s.toggleAlerts);
  const feed = useFeed();
  const count = feed?.active.length ?? 0;

  return (
    <SidePanel
      side="left"
      open={open}
      growIn={false}
      width={320}
      icon={BellRing}
      label="alerts panel"
      ariaLabel="Alerts and recommendations"
      railTitle="Alerts"
      shortcut="["
      onToggle={toggle}
      railBadge={
        count > 0 ? (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-warn px-1 font-mono text-micro font-bold tracking-normal text-bg">{count}</span>
        ) : null
      }
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.08] py-2.5 pl-3.5 pr-2">
        <h2 className="whitespace-nowrap pl-0.5 text-body font-semibold">Alerts &amp; recommendations</h2>
        {feed && (
          <Badge tone={count > 0 ? "warn" : "neutral"} className="ml-auto whitespace-nowrap">
            {count} open
          </Badge>
        )}
        <PanelCollapseButton side="left" onToggle={toggle} shortcut="[" label="alerts panel" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <FeedBody />
      </div>
    </SidePanel>
  );
}
