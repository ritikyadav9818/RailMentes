import { describe, expect, it } from "vitest";

import type { NetworkInfo } from "../api/types";
import mock from "../mocks/network.json";
import { placeLabels, tierOf } from "./labelPlacement";
import { computeLayout } from "./layout";

const layout = computeLayout(mock as unknown as NetworkInfo);

describe("placeLabels", () => {
  it("shows only major stations and junctions at the default zoom", () => {
    const labels = placeLabels(layout, 1, 1);
    for (const code of labels.keys()) expect(tierOf(layout.stations[code])).toBe(1);
    for (const s of layout.stationList.filter((x) => tierOf(x) === 1)) expect(labels.has(s.code)).toBe(true);
  });

  it("reveals more labels as the tier rises", () => {
    const t1 = placeLabels(layout, 1, 1).size;
    const t2 = placeLabels(layout, 2, 2).size;
    const t3 = placeLabels(layout, 3, 3).size;
    expect(t2).toBeGreaterThan(t1);
    expect(t3).toBeGreaterThanOrEqual(t2);
  });

  it("never lets two labels overlap on the same side when zoomed in", () => {
    const k = 3;
    const labels = [...placeLabels(layout, k, 3).values()];
    for (let i = 0; i < labels.length; i++) {
      for (let j = i + 1; j < labels.length; j++) {
        if (labels[i].side !== labels[j].side) continue;
        const a = layout.stations[labels[i].code];
        const b = layout.stations[labels[j].code];
        const clash = Math.abs(a.x - b.x) * k < 40 && Math.abs(a.y - b.y) * k < 30;
        expect(clash).toBe(false);
      }
    }
  });

  it("alternates neighbouring main-line labels above and below", () => {
    const labels = placeLabels(layout, 2, 3);
    const sides = layout.mainLine.filter((c) => labels.has(c) && !layout.stations[c].isJunction).map((c) => labels.get(c)?.side);
    expect(new Set(sides).size).toBe(2);
  });

  it("keeps a label off the side a branch leaves towards", () => {
    const labels = placeLabels(layout, 2, 3);
    for (const s of layout.stationList.filter((x) => x.isJunction)) {
      const side = labels.get(s.code)?.side;
      for (const seg of layout.segments.filter((g) => g.from === s.code || g.to === s.code)) {
        const other = layout.stations[seg.from === s.code ? seg.to : seg.from];
        const dy = other.y - s.y;
        if (Math.abs(dy) > Math.abs(other.x - s.x) * 0.45) expect(side).not.toBe(dy > 0 ? "below" : "above");
      }
    }
  });
});
