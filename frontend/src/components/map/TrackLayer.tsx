import { memo } from "react";

import type { BlockOccupancy, Disruption } from "../../api/types";
import { affectedBlockIds } from "../../utils/disruptions";
import { blockSpan, railShift, segmentDirection, type LayoutSegment, type MapLayout } from "../../utils/layout";

const RAIL = "#4a627d";
const RAIL_SINGLE = "#5f7b9b";
const CASING = "#05080c";
const ACCENT = "#38bdf8";

/** Stroke widths are px at the fitted zoom times --ms (set by the map), so lines thicken gently when zooming in. */
const px = (n: number): string => `calc(var(--ms) * ${n}px)`;

interface Props {
  layout: MapLayout;
  blocks: BlockOccupancy[];
  disruptions: Disruption[];
  /** block id -> true if the train in it runs against the segment direction */
  reverse: Map<string, boolean>;
}

function Segment({ layout, segment }: { layout: MapLayout; segment: LayoutSegment }) {
  const { a, b } = segment;
  if (segment.line === "single") {
    // one thick rail on a dark casing
    return (
      <g strokeLinecap="round">
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={CASING} style={{ strokeWidth: px(13) }} />
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={RAIL_SINGLE} style={{ strokeWidth: px(6) }} />
      </g>
    );
  }
  // two parallel rails on one casing
  const up = railShift(layout, segment, a, -1);
  const up2 = railShift(layout, segment, b, -1);
  const down = railShift(layout, segment, a, 1);
  const down2 = railShift(layout, segment, b, 1);
  return (
    <g strokeLinecap="round">
      <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={CASING} style={{ strokeWidth: px(24) }} />
      <g stroke={RAIL}>
        <line x1={up.x} y1={up.y} x2={up2.x} y2={up2.y} style={{ strokeWidth: px(3.6) }} />
        <line x1={down.x} y1={down.y} x2={down2.x} y2={down2.y} style={{ strokeWidth: px(3.6) }} />
      </g>
    </g>
  );
}

/** Corner points of a rectangle of half-width `w` around one block (for hatching). */
function blockBox(layout: MapLayout, blockId: string, w: number): string | null {
  const span = blockSpan(layout, blockId);
  const hit = layout.blocks[blockId];
  if (!span || !hit) return null;
  const d = segmentDirection(hit.segment);
  const n = { x: -d.y * w, y: d.x * w };
  const pts = [
    [span.a.x + n.x, span.a.y + n.y],
    [span.b.x + n.x, span.b.y + n.y],
    [span.b.x - n.x, span.b.y - n.y],
    [span.a.x - n.x, span.a.y - n.y],
  ];
  return pts.map((p) => p.join(",")).join(" ");
}

/** Tracks, block boundary ticks and the occupied / closed / signal-failure overlays. */
export const TrackLayer = memo(function TrackLayer({ layout, blocks, disruptions, reverse }: Props) {
  const occupied = new Set(blocks.filter((b) => b.train_id !== null && !b.closed).map((b) => b.block_id));
  const closed = blocks.filter((b) => b.closed).map((b) => b.block_id);
  const signalBlocks = new Set(
    disruptions.filter((d) => d.kind === "signal_failure").flatMap((d) => affectedBlockIds(layout, d.target_ids)),
  );

  return (
    <g>
      {layout.segments.map((s) => (
        <Segment key={s.id} layout={layout} segment={s} />
      ))}

      {/* block boundaries */}
      {layout.segments.flatMap((s) =>
        s.blocks.slice(1).map((blk) => {
          const span = blockSpan(layout, blk.id);
          if (!span) return null;
          const d = segmentDirection(s);
          const half = s.line === "double" ? 15 : 10;
          return (
            <line
              key={blk.id}
              x1={span.a.x - d.y * half}
              y1={span.a.y + d.x * half}
              x2={span.a.x + d.y * half}
              y2={span.a.y - d.x * half}
              stroke="#33465c"
              style={{ strokeWidth: px(1.4) }}
            />
          );
        }),
      )}

      {/* occupied blocks: a soft halo and dashes that flow the way the train is going */}
      {[...occupied].map((id) => {
        const span = blockSpan(layout, id);
        if (!span) return null;
        const [from, to] = reverse.get(id) ? [span.b, span.a] : [span.a, span.b];
        return (
          <g key={`occ-${id}`} strokeLinecap="round">
            <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={ACCENT} strokeOpacity={0.22} style={{ strokeWidth: px(16) }} />
            <line
              className="flow"
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={ACCENT}
              strokeOpacity={0.95}
              strokeDasharray="7 13"
              style={{ strokeWidth: px(3) }}
            />
          </g>
        );
      })}

      {/* signal failures: dashed amber */}
      {[...signalBlocks].map((id) => {
        const span = blockSpan(layout, id);
        if (!span) return null;
        return (
          <line
            key={`sig-${id}`}
            x1={span.a.x}
            y1={span.a.y}
            x2={span.b.x}
            y2={span.b.y}
            stroke="#f5a524"
            strokeDasharray="6 7"
            strokeOpacity={0.9}
            style={{ strokeWidth: px(5) }}
          />
        );
      })}

      {/* closed blocks: hatched */}
      {closed.map((id) => {
        const box = blockBox(layout, id, 15);
        return box ? (
          <polygon key={`closed-${id}`} points={box} fill="url(#hatch)" stroke="#f04438" strokeOpacity={0.85} style={{ strokeWidth: px(1.4) }} />
        ) : null;
      })}
    </g>
  );
});
