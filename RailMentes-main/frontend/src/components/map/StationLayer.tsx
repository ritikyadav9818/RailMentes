import { memo } from "react";

import type { LabelSpec } from "../../utils/labelPlacement";
import type { MapLayout, StationNode } from "../../utils/layout";
import { shortStationName } from "../../utils/labels";

const MONO = "JetBrains Mono Variable, Consolas, monospace";
/** Thick dark outline around the text keeps it readable over tracks and grid. */
const halo = { paintOrder: "stroke", stroke: "#070b10", strokeWidth: 4.5, strokeLinejoin: "round" } as const;

/** Everything inside a station group is drawn in px; --ms (set by the map) scales it with the zoom. */
function Marker({ node }: { node: StationNode }) {
  if (node.isJunction) {
    return (
      <>
        <circle r={26} fill="url(#station-glow)" />
        <circle r={14} fill="#070b10" stroke="#38bdf8" strokeWidth={2.6} />
        <circle r={6.5} fill="#38bdf8" />
      </>
    );
  }
  if (node.freightOnly) return <rect x={-7} y={-7} width={14} height={14} rx={2} fill="#070b10" stroke="#8a9bb0" strokeWidth={2.4} />;
  const major = node.size === 1;
  return <circle r={major ? 9.5 : node.size === 2 ? 7 : 5.5} fill="#070b10" stroke={major ? "#e6eef7" : "#b4c3d4"} strokeWidth={major ? 3 : 2.4} />;
}

function Label({ node, spec }: { node: StationNode; spec: LabelSpec }) {
  const above = spec.side === "above";
  const near = node.isJunction ? 21 : 15;
  const codeY = above ? -(near + 3) : near + 11;
  const nameY = above ? codeY - 15 : codeY + 15;
  return (
    <g pointerEvents="none">
      <text x={0} y={codeY} textAnchor="middle" fontFamily={MONO} fontSize={13} fontWeight={700} fill="#e6eef7" letterSpacing="0.04em" style={halo}>
        {node.code}
      </text>
      {spec.showName && (
        <text x={0} y={nameY} textAnchor="middle" fontSize={11.5} fontWeight={500} fill="#9db0c5" style={halo}>
          {shortStationName(node.name)}
        </text>
      )}
    </g>
  );
}

/**
 * Stations as nodes with labels. Junctions have a double ring, freight-only yards are squares.
 * `labels` says which stations are labelled at the current zoom (see utils/labelPlacement).
 */
export const StationLayer = memo(function StationLayer({ layout, labels }: { layout: MapLayout; labels: Map<string, LabelSpec> }) {
  return (
    <g>
      {layout.stationList.map((s) => {
        const spec = labels.get(s.code);
        return (
          <g key={s.code} data-station={s.code} style={{ transform: `translate(${s.x}px, ${s.y}px) scale(var(--ms))` }}>
            <Marker node={s} />
            {spec && <Label node={s} spec={spec} />}
          </g>
        );
      })}
    </g>
  );
});
