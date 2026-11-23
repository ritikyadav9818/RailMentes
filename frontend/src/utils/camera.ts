/**
 * Pan / zoom camera for the map. Pure maths plus a small controller; no DOM, no React.
 * A world point (wx, wy) is drawn at screen (wx * k + x, wy * k + y).
 * The controller keeps a `target` camera and eases the current one towards it, so wheel zoom and
 * fit-to-screen glide instead of jumping, while dragging moves both at once (no lag under the hand).
 */

export interface Camera {
  x: number;
  y: number;
  /** screen px per world unit */
  k: number;
}

export interface Size {
  w: number;
  h: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** Screen px kept free on each side by overlays (KPI chips, toolbar ...). */
export interface Insets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** Zoom limits relative to the fitted zoom. */
export const REL_MIN = 0.6;
export const REL_MAX = 8;
/** Share of the distance still left after one second of easing (smaller = snappier). */
const EASE_LEFT_PER_SEC = 0.0004;
/** Stop easing when closer than this (px, and relative zoom). */
const EPS_PX = 0.15;
const EPS_K = 0.0005;

export function clampNumber(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** The camera that shows `bounds` as large as possible inside `size` minus `insets`, centred. */
export function fitCamera(bounds: Bounds, size: Size, insets: Insets): Camera {
  const availW = Math.max(1, size.w - insets.left - insets.right);
  const availH = Math.max(1, size.h - insets.top - insets.bottom);
  const bw = Math.max(1, bounds.maxX - bounds.minX);
  const bh = Math.max(1, bounds.maxY - bounds.minY);
  const k = Math.min(availW / bw, availH / bh);
  return {
    k,
    x: insets.left + (availW - bw * k) / 2 - bounds.minX * k,
    y: insets.top + (availH - bh * k) / 2 - bounds.minY * k,
  };
}

/** Zoom by `factor` keeping the world point under screen (sx, sy) fixed. `k` stays inside [kMin, kMax]. */
export function zoomAt(cam: Camera, factor: number, sx: number, sy: number, kMin: number, kMax: number): Camera {
  const k = clampNumber(cam.k * factor, kMin, kMax);
  const f = k / cam.k;
  return { k, x: sx - (sx - cam.x) * f, y: sy - (sy - cam.y) * f };
}

/** Keep at least `keep` px of the world box on screen so the map can never be lost. */
export function clampPan(cam: Camera, bounds: Bounds, size: Size, keep = 120): Camera {
  const left = bounds.minX * cam.k + cam.x;
  const right = bounds.maxX * cam.k + cam.x;
  const top = bounds.minY * cam.k + cam.y;
  const bottom = bounds.maxY * cam.k + cam.y;
  let { x, y } = cam;
  if (right < keep) x += keep - right;
  if (left > size.w - keep) x -= left - (size.w - keep);
  if (bottom < keep) y += keep - bottom;
  if (top > size.h - keep) y -= top - (size.h - keep);
  return { ...cam, x, y };
}

/** The part of the world that is on screen. */
export function visibleWorld(cam: Camera, size: Size): Bounds {
  return { minX: -cam.x / cam.k, minY: -cam.y / cam.k, maxX: (size.w - cam.x) / cam.k, maxY: (size.h - cam.y) / cam.k };
}

export function sameCamera(a: Camera, b: Camera): boolean {
  return Math.abs(a.x - b.x) < EPS_PX && Math.abs(a.y - b.y) < EPS_PX && Math.abs(a.k / b.k - 1) < EPS_K;
}

/** Move `cur` towards `target` for a frame of `dtSec`. Frame-rate independent. */
export function easeCamera(cur: Camera, target: Camera, dtSec: number): Camera {
  const a = 1 - Math.pow(EASE_LEFT_PER_SEC, clampNumber(dtSec, 0, 0.1));
  const next = {
    x: cur.x + (target.x - cur.x) * a,
    y: cur.y + (target.y - cur.y) * a,
    // zoom eases in log space so zooming in and out feel the same
    k: cur.k * Math.pow(target.k / cur.k, a),
  };
  return sameCamera(next, target) ? { ...target } : next;
}

/** Level of detail from the zoom relative to the fitted zoom. */
export function zoomTier(rel: number): 1 | 2 | 3 {
  if (rel >= 2.4) return 3;
  if (rel >= 1.5) return 2;
  return 1;
}

/**
 * World-to-screen factor for markers and strokes: apparent size grows like rel^0.33, slower than
 * the map itself, so things stay readable zoomed out and do not balloon zoomed in.
 * Multiply by a size in px to get a size in world units.
 */
/** How fast markers and text grow with the zoom (1 = like the map, 0 = never). */
export const SIZE_GROWTH = 0.33;

export function markerScale(k: number, fitK: number): number {
  return Math.pow(k / fitK, SIZE_GROWTH) / k;
}

type Listener = (cam: Camera, size: Size, fitK: number) => void;

/** Holds the camera state for one map. The React side subscribes and drives `tick` from a frame loop. */
export class CameraController {
  cam: Camera = { x: 0, y: 0, k: 1 };
  target: Camera = { x: 0, y: 0, k: 1 };
  size: Size = { w: 0, h: 0 };
  /** zoom of the fitted view; 1 until the first fit */
  fitK = 1;
  /** true while the view is the fitted one (a resize then refits) */
  autoFit = true;
  private listeners = new Set<Listener>();

  constructor(
    public bounds: Bounds,
    public insets: Insets,
  ) {}

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.cam, this.size, this.fitK);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    for (const fn of this.listeners) fn(this.cam, this.size, this.fitK);
  }

  /** New container size. Fitted views refit; a user view keeps the world point at the centre. */
  setSize(size: Size): void {
    if (size.w <= 0 || size.h <= 0) return;
    const first = this.size.w === 0;
    const dx = (size.w - this.size.w) / 2;
    const dy = (size.h - this.size.h) / 2;
    this.size = size;
    if (first || this.autoFit) {
      this.fit(!first);
      return;
    }
    this.cam = { ...this.cam, x: this.cam.x + dx, y: this.cam.y + dy };
    this.target = { ...this.target, x: this.target.x + dx, y: this.target.y + dy };
    this.emit();
  }

  /** Fit the whole corridor. `animate` = ease there, otherwise jump. */
  fit(animate = true): void {
    const fitted = fitCamera(this.bounds, this.size, this.insets);
    this.fitK = fitted.k;
    this.target = fitted;
    this.autoFit = true;
    if (!animate) this.cam = { ...fitted };
    this.emit();
  }

  zoomBy(factor: number, sx = this.size.w / 2, sy = this.size.h / 2): void {
    this.autoFit = false;
    const next = zoomAt(this.target, factor, sx, sy, this.fitK * REL_MIN, this.fitK * REL_MAX);
    this.target = clampPan(next, this.bounds, this.size);
  }

  /** Drag: the map follows the pointer exactly, so the easing is cancelled. */
  panBy(dx: number, dy: number): void {
    this.autoFit = false;
    this.target = clampPan({ ...this.target, x: this.target.x + dx, y: this.target.y + dy }, this.bounds, this.size);
    this.cam = { ...this.target };
    this.emit();
  }

  /** Centre the view on a world point (minimap click). */
  centerOn(wx: number, wy: number): void {
    this.autoFit = false;
    const centred = { k: this.target.k, x: this.size.w / 2 - wx * this.target.k, y: this.size.h / 2 - wy * this.target.k };
    this.target = clampPan(centred, this.bounds, this.size);
  }

  get moving(): boolean {
    return !sameCamera(this.cam, this.target);
  }

  /** Advance the easing (`instant` jumps). Returns true while the camera is still moving. */
  tick(dtSec: number, instant = false): boolean {
    if (!this.moving) return false;
    this.cam = instant ? { ...this.target } : easeCamera(this.cam, this.target, dtSec);
    this.emit();
    return this.moving;
  }

  /** Zoom relative to the fitted view (1 = fitted). */
  get rel(): number {
    return this.cam.k / this.fitK;
  }
}
