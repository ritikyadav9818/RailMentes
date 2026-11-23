import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Clock, CloudFog, CloudRain, OctagonX, TrafficCone, type LucideIcon } from "lucide-react";

import type { DisruptionKind } from "../api/types";
import { useRailStore } from "../store/useRailStore";
import { DISRUPTION_LABELS } from "../utils/labels";

const ICONS: Record<DisruptionKind, LucideIcon> = {
  fog: CloudFog,
  weather_slowdown: CloudRain,
  signal_failure: TrafficCone,
  block_closure: OctagonX,
  maintenance: OctagonX,
  late_departure: Clock,
};

/** Chips shown before the rest collapse into "+N more". */
const MAX_CHIPS = 2;

/** Active disruptions with the minutes they still have to run, as chips floating over the map. */
export function DisruptionStrip() {
  const snapshot = useRailStore((s) => s.snapshot);
  if (!snapshot) return null;
  const { disruptions, tick } = snapshot;
  const shown = disruptions.slice(0, MAX_CHIPS);
  return (
    <div className="pointer-events-auto flex max-w-full flex-nowrap items-start gap-2" aria-label="Active disruptions" role="group">
      {disruptions.length === 0 && (
        <span className="glass flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-caption text-muted">
          <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> No active disruptions
        </span>
      )}
      <AnimatePresence initial={false}>
        {shown.map((d) => {
          const Icon = ICONS[d.kind];
          const left = Math.max(0, d.end_tick - tick);
          const where = d.target_ids.length === 0 ? "whole network" : d.target_ids.slice(0, 2).join(", ") + (d.target_ids.length > 2 ? ` +${d.target_ids.length - 2}` : "");
          return (
            <motion.span
              key={d.id}
              layout
              initial={{ opacity: 0, scale: 0.9, y: -8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9 }}
              title={d.description}
              className="glass-strong flex min-w-0 shrink items-center gap-2 whitespace-nowrap rounded-full border-warn/40 py-1.5 pl-2.5 pr-3 text-caption text-warn"
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              <span className="font-medium">{DISRUPTION_LABELS[d.kind]}</span>
              <span className="max-w-[7rem] truncate font-mono text-warn/70">{where}</span>
              <span className="font-mono text-warn/70" title="Minutes until it ends">{left} min</span>
            </motion.span>
          );
        })}
      </AnimatePresence>
      {disruptions.length > MAX_CHIPS && (
        <span className="glass flex shrink-0 items-center rounded-full px-3 py-1.5 font-mono text-caption text-warn" title={disruptions.slice(MAX_CHIPS).map((d) => d.description).join("\n")}>
          +{disruptions.length - MAX_CHIPS} more
        </span>
      )}
    </div>
  );
}
