import { motion } from "framer-motion";
import { Target, Timer, TrainFront, type LucideIcon } from "lucide-react";

import { useRailStore } from "../store/useRailStore";
import { delayColor } from "../utils/delay";
import { STRATEGY_LABELS } from "../utils/labels";
import { AnimatedNumber } from "./AnimatedNumber";

interface KpiProps {
  label: string;
  value: number;
  decimals?: number;
  unit?: string;
  color?: string;
  hint?: string;
  icon: LucideIcon;
  index: number;
}

function Kpi({ label, value, decimals = 0, unit, color, hint, icon: Icon, index }: KpiProps) {
  return (
    <motion.div
      className="glass-strong pointer-events-auto flex items-center gap-2.5 rounded-xl py-1.5 pl-2.5 pr-3.5"
      title={hint}
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.35 + index * 0.07, type: "spring", stiffness: 340, damping: 30 }}
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.05] text-muted">
        <Icon className="h-4 w-4" />
      </span>
      <div>
        <div className="micro-label leading-none">{label}</div>
        <div className="mt-1 flex items-baseline gap-1 leading-none">
          <AnimatedNumber value={value} decimals={decimals} className="font-mono text-display font-semibold text-text" />
          {unit && <span className="font-mono text-caption text-muted">{unit}</span>}
        </div>
      </div>
      {color && <span className="ml-1 h-6 w-1 rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}99` }} aria-hidden="true" />}
    </motion.div>
  );
}

/** Live average delay, punctuality and trains finished, as glass chips floating over the map. */
export function KpiStrip() {
  const snapshot = useRailStore((s) => s.snapshot);
  if (!snapshot) {
    return (
      <div className="flex gap-2" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-[52px] w-40 animate-pulse rounded-xl bg-white/5" />
        ))}
      </div>
    );
  }
  const { kpis, trains } = snapshot;
  const finished = trains.filter((t) => t.status === "finished").length;
  return (
    <div className="flex gap-2">
      <Kpi index={0} icon={Timer} label="Average delay" value={kpis.avg_delay_min} decimals={1} unit="min" color={delayColor(kpis.avg_delay_min)} hint="Average delay of all trains; early trains count as 0" />
      <Kpi index={1} icon={Target} label="Punctuality" value={kpis.punctuality_pct} unit="%" hint="Share of trains at most 5 min late" />
      <Kpi index={2} icon={TrainFront} label="Trains finished" value={finished} unit={`of ${trains.length}`} hint={`Strategy: ${STRATEGY_LABELS[snapshot.strategy]}`} />
    </div>
  );
}
