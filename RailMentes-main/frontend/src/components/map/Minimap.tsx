import { memo, useEffect, useMemo, useRef } from "react";

import type { Conflict, TrainState } from "../../api/types";
import { visibleWorld, type CameraController } from "../../utils/camera";
import { delayColor } from "../../utils/delay";
import type { MapLayout } from "../../utils/layout";
import { trainTargets } from "../../utils/trainTargets";
import { conflictPoint } from "./ConflictLayer";

const WIDTH = 188;
const MAX_HEIGHT = 80;
const PAD = 36;

interface Props {
  layout: MapLayout;
  controller: CameraController;
  trains: TrainState[];
  conflicts: Conflict[];
}

/** The whole corridor in miniature with the part currently on screen outlined. Click or drag to move the view. */
export const Minimap = memo(function Minimap({ layout, controller, trains, conflicts }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const box = useRef<SVGRectElement>(null);
  const dragging = useRef(false);

  const vb = { x: -PAD, y: -PAD, w: layout.width + PAD * 2, h: layout.height + PAD * 2 };
  const height = Math.min(MAX_HEIGHT, Math.max(48, Math.round((WIDTH * vb.h) / vb.w)));
  const points = useMemo(() => trainTargets(layout, trains), [layout, trains]);

  useEffect(
    () =>
      controller.subscribe((cam, size) => {
        const el = box.current;
        if (!el || size.w === 0) return;
        const v = visibleWorld(cam, size);
        el.setAttribute("x", String(v.minX));
        el.setAttribute("y", String(v.minY));
        el.setAttribute("width", String(v.maxX - v.minX));
        el.setAttribute("height", String(v.maxY - v.minY));
      }),
    [controller],
  );

  const moveTo = (e: React.PointerEvent) => {
    const r = svg.current?.getBoundingClientRect();
    if (!r) return;
    controller.centerOn(vb.x + ((e.clientX - r.left) / r.width) * vb.w, vb.y + ((e.clientY - r.top) / r.height) * vb.h);
  };

  return (
    <svg
      ref={svg}
      width={WIDTH}
      height={height}
      viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
      preserveAspectRatio="none"
      className="glass-strong cursor-crosshair overflow-hidden rounded-lg"
      role="img"
      aria-label="Minimap of the whole corridor. Click to move the view."
      onPointerDown={(e) => {
        dragging.current = true;
        e.currentTarget.setPointerCapture(e.pointerId);
        moveTo(e);
      }}
      onPointerMove={(e) => dragging.current && moveTo(e)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      <g strokeLinecap="round">
        {layout.segments.map((s) => (
          <line
            key={s.id}
            x1={s.a.x}
            y1={s.a.y}
            x2={s.b.x}
            y2={s.b.y}
            stroke={s.line === "double" ? "#5a7392" : "#46607e"}
            strokeWidth={s.line === "double" ? 2.2 : 1.6}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </g>
      {layout.stationList.map((s) => (
        <circle key={s.code} cx={s.x} cy={s.y} r={s.size === 1 || s.isJunction ? 17 : 11} fill="#c9d6e4" fillOpacity={s.size === 1 || s.isJunction ? 0.9 : 0.5} />
      ))}
      {conflicts.map((c) => {
        const p = conflictPoint(layout, c);
        return p ? <circle key={c.id} cx={p.x} cy={p.y} r={22} fill="none" stroke={c.severity === "critical" ? "#f04438" : "#f5a524"} strokeWidth={1.6} vectorEffect="non-scaling-stroke" /> : null;
      })}
      {[...points.entries()].map(([id, p]) => {
        const t = trains.find((x) => x.id === id);
        return <circle key={id} cx={p.x} cy={p.y} r={15} fill={t ? delayColor(t.delay_min) : "#8a9bb0"} />;
      })}
      <rect ref={box} fill="#38bdf8" fillOpacity={0.1} stroke="#38bdf8" strokeWidth={1.4} vectorEffect="non-scaling-stroke" pointerEvents="none" />
    </svg>
  );
});
