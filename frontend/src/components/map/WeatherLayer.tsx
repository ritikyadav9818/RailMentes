import { memo } from "react";

import type { Disruption } from "../../api/types";
import { affectedBlockIds, isWeather } from "../../utils/disruptions";
import { blockSpan, type MapLayout } from "../../utils/layout";

/** Soft drifting fog over the stretches hit by fog or weather slowdowns (static with reduced motion). */
export const WeatherLayer = memo(function WeatherLayer({ layout, disruptions }: { layout: MapLayout; disruptions: Disruption[] }) {
  const blobs = new Map<string, { cx: number; cy: number; rx: number; ry: number; opacity: number }>();
  for (const d of disruptions.filter(isWeather)) {
    // the lower the allowed speed, the thicker the fog
    const opacity = Math.min(1, 0.45 + (1 - d.speed_factor) * 0.9);
    for (const id of affectedBlockIds(layout, d.target_ids)) {
      const span = blockSpan(layout, id);
      if (!span) continue;
      const len = Math.hypot(span.b.x - span.a.x, span.b.y - span.a.y);
      const prev = blobs.get(id);
      if (prev && prev.opacity >= opacity) continue;
      blobs.set(id, { cx: (span.a.x + span.b.x) / 2, cy: (span.a.y + span.b.y) / 2, rx: len * 0.85 + 24, ry: 52, opacity });
    }
  }

  return (
    <g pointerEvents="none" aria-hidden="true">
      {[...blobs.entries()].map(([id, b], i) => (
        <ellipse
          key={id}
          className="fog-blob"
          cx={b.cx}
          cy={b.cy}
          rx={b.rx}
          ry={b.ry}
          fill="url(#fog-blob)"
          opacity={b.opacity}
          style={{ animationDelay: `${-(i % 7) * 0.9}s`, animationDuration: `${6 + (i % 5)}s` }}
        />
      ))}
    </g>
  );
});
