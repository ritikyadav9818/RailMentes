import { useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useRef } from "react";

import type { TrainState } from "../../api/types";
import { useRailStore } from "../../store/useRailStore";
import { markerScale, type CameraController } from "../../utils/camera";
import { delayColor, delayLevel } from "../../utils/delay";
import { distance, lerpPoint, shouldSnap, slideDuration, slideProgress, type Point } from "../../utils/interpolate";
import type { MapLayout } from "../../utils/layout";
import { trainTargets } from "../../utils/trainTargets";
import { TrainShape } from "./TrainShape";

const TRAIL_SEGMENTS = 12;
/** A trail point is added after the marker moved this far (map units). */
const TRAIL_STEP = 2.6;
/** A standing train loses one trail point this often (ms), so the trail fades away. */
const TRAIL_DECAY_MS = 130;
/** Moves longer than this (map units) are jumps, not slides. */
const MAX_SLIDE_DISTANCE = 340;

interface Track {
  from: Point;
  to: Point;
  cur: Point;
  startedAt: number;
  duration: number;
  trail: Point[];
  lastDecay: number;
  shown: boolean;
}

interface Dom {
  mover: SVGGElement | null;
  trail: (SVGLineElement | null)[];
}

export interface HoverInfo {
  id: string;
  clientX: number;
  clientY: number;
}

interface Props {
  layout: MapLayout;
  trains: TrainState[];
  tick: number;
  controller: CameraController;
  onHover: (info: HoverInfo | null) => void;
}

/**
 * Train markers. React renders the markers; a requestAnimationFrame loop moves them by writing
 * SVG attributes directly, so 25 trains sliding at 60 fps cost no React re-renders.
 * Each snapshot sets a new target; the marker slides from where it is now to that target over
 * the (smoothed) time between snapshots, so motion is continuous at any simulation speed.
 * Markers are drawn in screen px and scaled by the camera, so they stay readable at any zoom.
 */
export function TrainsLayer({ layout, trains, tick, controller, onHover }: Props) {
  const reduced = useReducedMotion() ?? false;
  const selectedId = useRailStore((s) => s.selectedTrainId);
  const selectTrain = useRailStore((s) => s.selectTrain);

  const tracks = useRef(new Map<string, Track>());
  const doms = useRef(new Map<string, Dom>());
  const lastTick = useRef<number | null>(null);
  const lastLayout = useRef(layout);
  const reducedRef = useRef(reduced);
  reducedRef.current = reduced;

  const visible = useMemo(() => trains.filter((t) => t.position !== null), [trains]);

  // a new snapshot: set new slide targets
  useEffect(() => {
    const store = useRailStore.getState();
    const now = performance.now();
    const targets = trainTargets(layout, trains);
    // a new layout (window resized to another shape) moves every station, so place trains directly
    const snap = shouldSnap(lastTick.current, tick) || lastLayout.current !== layout;
    lastLayout.current = layout;
    lastTick.current = tick;
    const duration = slideDuration(store.intervalMs, store.settings.speed);

    for (const id of [...tracks.current.keys()]) if (!targets.has(id)) tracks.current.delete(id);
    for (const [id, target] of targets) {
      const tr = tracks.current.get(id);
      if (!tr || snap || distance(tr.cur, target) > MAX_SLIDE_DISTANCE) {
        tracks.current.set(id, { from: target, to: target, cur: target, startedAt: now, duration: 0, trail: [], lastDecay: now, shown: false });
      } else {
        tr.from = tr.cur;
        tr.to = target;
        tr.startedAt = now;
        tr.duration = duration;
      }
    }
  }, [layout, trains, tick]);

  // the frame loop
  useEffect(() => {
    let raf = 0;
    const frame = (now: number) => {
      const scale = markerScale(controller.cam.k, controller.fitK).toFixed(5);
      for (const [id, tr] of tracks.current) {
        const dom = doms.current.get(id);
        if (!dom?.mover) continue;
        tr.cur = lerpPoint(tr.from, tr.to, slideProgress(now, tr.startedAt, tr.duration));
        dom.mover.setAttribute("transform", `translate(${tr.cur.x.toFixed(2)} ${tr.cur.y.toFixed(2)}) scale(${scale})`);
        if (!tr.shown) {
          dom.mover.setAttribute("visibility", "visible");
          dom.mover.style.opacity = "1";
          tr.shown = true;
        }
        updateTrail(tr, dom, now, reducedRef.current);
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [controller]);

  return (
    <g>
      {visible.map((train) => {
        const color = delayColor(train.delay_min);
        const level = delayLevel(train.delay_min);
        const selected = train.id === selectedId;
        const dom: Dom = doms.current.get(train.id) ?? { mover: null, trail: [] };
        doms.current.set(train.id, dom);
        return (
          <g key={train.id}>
            {!reduced && (
              <g pointerEvents="none" stroke={color} strokeLinecap="round" style={{ strokeWidth: "calc(var(--ms) * 6px)" }}>
                {Array.from({ length: TRAIL_SEGMENTS }, (_, i) => (
                  <line key={i} ref={(el) => void (dom.trail[i] = el)} strokeOpacity={0} />
                ))}
              </g>
            )}
            <g
              ref={(el) => void (dom.mover = el)}
              className="train-marker"
              data-train-id={train.id}
              visibility="hidden"
              style={{ cursor: "pointer", opacity: 0, transition: "opacity 0.6s ease" }}
              onClick={() => selectTrain(selected ? null : train.id)}
              onPointerEnter={(e) => onHover({ id: train.id, clientX: e.clientX, clientY: e.clientY })}
              onPointerMove={(e) => onHover({ id: train.id, clientX: e.clientX, clientY: e.clientY })}
              onPointerLeave={() => onHover(null)}
            >
              {!reduced && <circle r={30} fill={`url(#glow-${level})`} pointerEvents="none" />}
              {selected && (
                <>
                  <circle r={19} fill="none" stroke="#38bdf8" strokeWidth={2} />
                  <circle className="select-pulse" r={19} fill="none" stroke="#38bdf8" strokeWidth={2.4} pointerEvents="none" />
                </>
              )}
              <g className="train-body">
                <TrainShape category={train.category} color={color} />
              </g>
              <circle r={19} fill="transparent" />
              {selected && (
                <text
                  y={-26}
                  textAnchor="middle"
                  fontFamily="JetBrains Mono Variable, Consolas, monospace"
                  fontSize={13}
                  fontWeight={700}
                  fill="#38bdf8"
                  pointerEvents="none"
                  style={{ paintOrder: "stroke", stroke: "#070b10", strokeWidth: 4.5, strokeLinejoin: "round" }}
                >
                  {train.id}
                </text>
              )}
            </g>
          </g>
        );
      })}
    </g>
  );
}

/** Keep a short list of recent positions and draw it as fading segments. */
function updateTrail(tr: Track, dom: Dom, now: number, reduced: boolean): void {
  if (reduced) return;
  const last = tr.trail[tr.trail.length - 1];
  if (!last || distance(last, tr.cur) >= TRAIL_STEP) {
    tr.trail.push(tr.cur);
    if (tr.trail.length > TRAIL_SEGMENTS) tr.trail.shift();
    tr.lastDecay = now;
  } else if (tr.trail.length > 0 && now - tr.lastDecay > TRAIL_DECAY_MS) {
    tr.trail.shift();
    tr.lastDecay = now;
  }
  const pts = [...tr.trail, tr.cur];
  for (let i = 0; i < TRAIL_SEGMENTS; i++) {
    const line = dom.trail[i];
    if (!line) continue;
    const a = pts[i];
    const b = pts[i + 1];
    if (!a || !b || pts.length < 3) {
      line.setAttribute("stroke-opacity", "0");
      continue;
    }
    line.setAttribute("x1", a.x.toFixed(2));
    line.setAttribute("y1", a.y.toFixed(2));
    line.setAttribute("x2", b.x.toFixed(2));
    line.setAttribute("y2", b.y.toFixed(2));
    line.setAttribute("stroke-opacity", ((0.5 * (i + 1)) / pts.length).toFixed(2));
  }
}
