import { Moon, Sun, Sunrise, Sunset, type LucideIcon } from "lucide-react";

import { useRailStore } from "../store/useRailStore";
import { hourFromIso, periodAt, type DayPeriod } from "../utils/daylight";
import { clockFromIso, dateFromIso, dayProgress } from "../utils/time";

const PERIOD: Record<DayPeriod, { icon: LucideIcon; label: string; color: string }> = {
  night: { icon: Moon, label: "Night", color: "text-indigo-300" },
  dawn: { icon: Sunrise, label: "Dawn", color: "text-amber-300" },
  day: { icon: Sun, label: "Day", color: "text-amber-200" },
  dusk: { icon: Sunset, label: "Dusk", color: "text-orange-300" },
};

/** Simulation clock with the progress of the simulated day underneath. */
export function SimClock() {
  const snapshot = useRailStore((s) => s.snapshot);
  if (!snapshot) return <div className="h-8 w-[9.25rem] animate-pulse rounded-md bg-white/5" />;
  const progress = dayProgress(snapshot.tick);
  const period = PERIOD[periodAt(hourFromIso(snapshot.sim_time))];
  const Icon = period.icon;
  return (
    <div className="flex items-center gap-2.5" title={`Simulation clock. Tick ${snapshot.tick} of a 1440-minute day (${period.label})`}>
      <Icon className={`h-4 w-4 shrink-0 ${period.color}`} aria-label={period.label} />
      <div className="w-[7.25rem]">
        <div className="flex items-baseline gap-2 whitespace-nowrap">
          <span className="font-mono text-title font-semibold leading-none text-text">{clockFromIso(snapshot.sim_time, true)}</span>
        </div>
        <div className="mt-0.5 whitespace-nowrap font-mono text-micro leading-none tracking-normal text-muted">{dateFromIso(snapshot.sim_time)}</div>
        <div
          className="mt-1 h-[3px] overflow-hidden rounded-full bg-white/10"
          role="progressbar"
          aria-label="Day progress"
          aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="h-full rounded-full bg-gradient-to-r from-accent/60 to-accent transition-[width] duration-500 ease-out" style={{ width: `${progress * 100}%` }} />
        </div>
      </div>
    </div>
  );
}
