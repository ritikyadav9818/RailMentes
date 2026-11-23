import { describe, expect, it } from "vitest";

import { CameraController, clampPan, easeCamera, fitCamera, markerScale, zoomAt, zoomTier, type Bounds, type Insets } from "./camera";

const bounds: Bounds = { minX: 0, minY: 0, maxX: 1000, maxY: 400 };
const none: Insets = { top: 0, right: 0, bottom: 0, left: 0 };

describe("fitCamera", () => {
  it("fits the limiting side and centres the other", () => {
    const cam = fitCamera(bounds, { w: 1000, h: 1000 }, none);
    expect(cam.k).toBe(1);
    expect(cam.x).toBe(0);
    expect(cam.y).toBe(300); // (1000 - 400) / 2
  });

  it("keeps the insets free", () => {
    const cam = fitCamera(bounds, { w: 1200, h: 600 }, { top: 100, right: 100, bottom: 100, left: 100 });
    expect(cam.k).toBe(1);
    expect(cam.x).toBeGreaterThanOrEqual(100);
    expect(1000 * cam.k + cam.x).toBeLessThanOrEqual(1100);
    expect(cam.y).toBeGreaterThanOrEqual(100);
    expect(400 * cam.k + cam.y).toBeLessThanOrEqual(500);
  });
});

describe("zoomAt", () => {
  it("keeps the world point under the cursor fixed", () => {
    const cam = { x: 40, y: 10, k: 1 };
    const next = zoomAt(cam, 2, 300, 200, 0.1, 10);
    const before = { x: (300 - cam.x) / cam.k, y: (200 - cam.y) / cam.k };
    const after = { x: (300 - next.x) / next.k, y: (200 - next.y) / next.k };
    expect(after.x).toBeCloseTo(before.x);
    expect(after.y).toBeCloseTo(before.y);
    expect(next.k).toBe(2);
  });

  it("respects the zoom limits", () => {
    expect(zoomAt({ x: 0, y: 0, k: 1 }, 100, 0, 0, 0.5, 4).k).toBe(4);
    expect(zoomAt({ x: 0, y: 0, k: 1 }, 0.001, 0, 0, 0.5, 4).k).toBe(0.5);
  });
});

describe("clampPan", () => {
  it("never lets the map leave the screen", () => {
    const far = clampPan({ x: -5000, y: 5000, k: 1 }, bounds, { w: 800, h: 600 }, 100);
    expect(1000 * far.k + far.x).toBeGreaterThanOrEqual(100);
    expect(far.y).toBeLessThanOrEqual(500);
  });

  it("leaves a sensible view alone", () => {
    const cam = { x: 20, y: 30, k: 1 };
    expect(clampPan(cam, bounds, { w: 800, h: 600 })).toEqual(cam);
  });
});

describe("easeCamera", () => {
  it("moves towards the target and lands on it", () => {
    const target = { x: 100, y: 50, k: 2 };
    let cam = { x: 0, y: 0, k: 1 };
    const first = easeCamera(cam, target, 1 / 60);
    expect(first.x).toBeGreaterThan(0);
    expect(first.x).toBeLessThan(100);
    for (let i = 0; i < 200; i++) cam = easeCamera(cam, target, 1 / 60);
    expect(cam).toEqual(target);
  });

  it("is frame-rate independent", () => {
    const target = { x: 100, y: 0, k: 1 };
    let a = { x: 0, y: 0, k: 1 };
    let b = { x: 0, y: 0, k: 1 };
    for (let i = 0; i < 30; i++) a = easeCamera(a, target, 1 / 60);
    for (let i = 0; i < 60; i++) b = easeCamera(b, target, 1 / 120);
    expect(a.x).toBeCloseTo(b.x, 3);
  });
});

describe("zoomTier and markerScale", () => {
  it("reveals more detail as the user zooms in", () => {
    expect(zoomTier(1)).toBe(1);
    expect(zoomTier(1.6)).toBe(2);
    expect(zoomTier(3)).toBe(3);
  });

  it("makes things grow slower than the map", () => {
    const fit = markerScale(1, 1) * 1; // apparent size = scale * k
    const zoomed = markerScale(4, 1) * 4;
    expect(fit).toBe(1);
    expect(zoomed).toBeGreaterThan(1);
    expect(zoomed).toBeLessThan(4);
  });
});

describe("CameraController", () => {
  const make = () => {
    const c = new CameraController(bounds, none);
    c.setSize({ w: 1000, h: 800 });
    return c;
  };

  it("starts fitted and jumps to the fit on the first size", () => {
    const c = make();
    expect(c.cam).toEqual(c.target);
    expect(c.rel).toBe(1);
    expect(c.autoFit).toBe(true);
  });

  it("zooms with easing and stops at the target", () => {
    const c = make();
    c.zoomBy(2, 500, 400);
    expect(c.autoFit).toBe(false);
    expect(c.moving).toBe(true);
    let frames = 0;
    while (c.tick(1 / 60) && frames < 500) frames++;
    expect(frames).toBeLessThan(500);
    expect(c.rel).toBeCloseTo(2);
  });

  it("limits zoom relative to the fit", () => {
    const c = make();
    for (let i = 0; i < 20; i++) c.zoomBy(2);
    c.tick(1, true);
    expect(c.rel).toBeCloseTo(8);
  });

  it("drag moves the map at once and fit brings it back", () => {
    const c = make();
    const before = { ...c.cam };
    c.panBy(30, -10);
    expect(c.cam.x).toBe(before.x + 30);
    expect(c.cam.y).toBe(before.y - 10);
    c.fit(false);
    expect(c.cam).toEqual(before);
    expect(c.autoFit).toBe(true);
  });

  it("refits on resize while fitted, keeps the view centre otherwise", () => {
    const c = make();
    c.setSize({ w: 1200, h: 800 });
    expect(c.autoFit).toBe(true);
    c.zoomBy(2);
    c.tick(1, true);
    const centre = { x: (600 - c.cam.x) / c.cam.k, y: (400 - c.cam.y) / c.cam.k };
    c.setSize({ w: 1000, h: 800 });
    const after = { x: (500 - c.cam.x) / c.cam.k, y: (400 - c.cam.y) / c.cam.k };
    expect(after.x).toBeCloseTo(centre.x);
    expect(after.y).toBeCloseTo(centre.y);
  });

  it("centres on a world point", () => {
    const c = make();
    c.zoomBy(2);
    c.centerOn(250, 100);
    c.tick(1, true);
    expect(250 * c.cam.k + c.cam.x).toBeCloseTo(500);
    expect(100 * c.cam.k + c.cam.y).toBeCloseTo(400);
  });

  it("notifies subscribers until they unsubscribe", () => {
    const c = make();
    let calls = 0;
    const off = c.subscribe(() => calls++);
    expect(calls).toBe(1);
    c.panBy(5, 5);
    expect(calls).toBe(2);
    off();
    c.panBy(5, 5);
    expect(calls).toBe(2);
  });
});
