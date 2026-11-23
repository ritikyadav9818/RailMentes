import { memo } from "react";

import type { Conflict, Severity } from "../../api/types";
import { useRailStore } from "../../store/useRailStore";
import type { Point } from "../../utils/interpolate";
import { blockMidpoint, type MapLayout } from "../../utils/layout";

const SEVERITY_COLOR: Record<Severity, string> = {
  low: "#8a9bb0",
  medium: "#38bdf8",
  high: "#f5a524",
  critical: "#f04438",
};

/** A conflict's location is a block id or a station code. */
export function conflictPoint(layout: MapLayout, conflict: Conflict): Point | null {
  const st = layout.stations[conflict.location];
  if (st) return { x: st.x, y: st.y };
  return blockMidpoint(layout, conflict.location);
}

/** Pulsing markers where the detector expects trains to clash. Click selects the first train. */
export const ConflictLayer = memo(function ConflictLayer({ layout, conflicts }: { layout: MapLayout; conflicts: Conflict[] }) {
  const selectTrain = useRailStore((s) => s.selectTrain);
  return (
    <g>
      {conflicts.map((c) => {
        const p = conflictPoint(layout, c);
        if (!p) return null;
        const color = SEVERITY_COLOR[c.severity];
        return (
          <g
            key={c.id}
            style={{ transform: `translate(${p.x}px, ${p.y}px) scale(var(--ms))`, cursor: "pointer" }}
            onClick={() => selectTrain(c.train_ids[0] ?? null)}
          >
            <title>{c.description}</title>
            <circle className="pulse-ring" r={13} fill="none" stroke={color} strokeWidth={2.4} />
            <circle className="pulse-ring pulse-ring-late" r={13} fill="none" stroke={color} strokeWidth={2.4} />
            <circle r={10} fill="#070b10" fillOpacity={0.85} stroke={color} strokeWidth={2.2} />
            <path d="M0 -4.6 V0.8 M0 3.6 V3.7" stroke={color} strokeWidth={2.6} strokeLinecap="round" />
          </g>
        );
      })}
    </g>
  );
});
