import { describe, expect, it } from "vitest";

import type { BlockInfo, NetworkInfo, StationInfo } from "../api/types";
import { mockNetwork, mockSnapshot } from "../mocks";
import { blockMidpoint, buildSegments, computeLayout, computeLayoutForAspect, findMainLine, trainPoint } from "./layout";
import { affectedBlockIds } from "./disruptions";

const layout = computeLayout(mockNetwork);

describe("buildSegments", () => {
  it("groups blocks per station pair, in numeric order, with running km", () => {
    const blocks: BlockInfo[] = [
      { id: "A-B-2", from_code: "A", to_code: "B", length_km: 4, line: "single", speed_limit_kmph: 80 },
      { id: "A-B-1", from_code: "A", to_code: "B", length_km: 6, line: "single", speed_limit_kmph: 80 },
    ];
    const [seg] = buildSegments(blocks);
    expect(seg.id).toBe("A-B");
    expect(seg.lengthKm).toBe(10);
    expect(seg.blocks.map((b) => [b.id, b.startKm])).toEqual([
      ["A-B-1", 0],
      ["A-B-2", 6],
    ]);
  });

  it("covers every block of the real corridor exactly once", () => {
    const ids = buildSegments(mockNetwork.blocks).flatMap((s) => s.blocks.map((b) => b.id));
    expect(ids.length).toBe(mockNetwork.blocks.length);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("computeLayout on the corridor", () => {
  it("puts the longest path on the main line, left to right, in km proportion", () => {
    expect(layout.mainLine[0]).toBe("SGP");
    expect(layout.mainLine[layout.mainLine.length - 1]).toBe("ARC");
    const xs = layout.mainLine.map((c) => layout.stations[c].x);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
    const ys = new Set(layout.mainLine.map((c) => layout.stations[c].y));
    expect(ys.size).toBe(1);

    const seg = layout.segments.find((s) => s.id === "DVG-KLP");
    expect(seg).toBeDefined();
    const dx = layout.stations.KLP.x - layout.stations.DVG.x;
    expect(dx / (seg?.lengthKm ?? 1)).toBeCloseTo(layout.options.kmScale, 5);
  });

  it("hangs the branch line off its junction and the goods spur on the other side", () => {
    for (const code of ["PTK", "KSG", "TLK"]) {
      expect(layout.stations[code].onMainLine).toBe(false);
      expect(layout.stations[code].y).toBeGreaterThan(layout.stations.VDJ.y);
    }
    expect(layout.stations.PTK.x).toBeGreaterThan(layout.stations.VDJ.x);
    expect(layout.stations.RGY.y).toBeLessThan(layout.stations.RMJ.y);
  });

  it("keeps every station inside the canvas and marks junctions", () => {
    for (const s of layout.stationList) {
      expect(s.x).toBeGreaterThan(0);
      expect(s.x).toBeLessThan(layout.width);
      expect(s.y).toBeGreaterThan(0);
      expect(s.y).toBeLessThan(layout.height);
    }
    expect(layout.stations.VDJ.isJunction).toBe(true);
    expect(layout.stations.RGY.freightOnly).toBe(true);
  });

  it("knows the line type of each segment", () => {
    expect(layout.segments.find((s) => s.id === "BHP-GNK")?.line).toBe("single");
    expect(layout.segments.find((s) => s.id === "SGP-DVG")?.line).toBe("double");
  });

  it("places every block of the mock snapshot", () => {
    for (const b of mockSnapshot.blocks) expect(blockMidpoint(layout, b.block_id)).not.toBeNull();
  });
});

describe("computeLayout is computed from the data, not hard-coded", () => {
  const st = (code: string, is_junction = false): StationInfo => ({ code, name: code, size: 1, platforms: 2, is_junction, freight_only: false });
  const blk = (from: string, to: string, km: number): BlockInfo => ({
    id: `${from}-${to}-1`,
    from_code: from,
    to_code: to,
    length_km: km,
    line: "double",
    speed_limit_kmph: 100,
  });
  // W - X - Y - Z is the longest path, Q hangs off X, R hangs off Y
  const toy: NetworkInfo = {
    disclaimer: "toy",
    stations: [st("W"), st("X", true), st("Y", true), st("Z"), st("Q"), st("R")],
    blocks: [blk("W", "X", 10), blk("X", "Y", 20), blk("Y", "Z", 10), blk("X", "Q", 5), blk("Y", "R", 5)],
  };
  const toyLayout = computeLayout(toy);

  it("finds the main line and alternates the branches", () => {
    expect(toyLayout.mainLine).toEqual(["W", "X", "Y", "Z"]);
    const q = toyLayout.stations.Q;
    const r = toyLayout.stations.R;
    expect(Math.sign(q.y - toyLayout.stations.X.y)).toBe(-Math.sign(r.y - toyLayout.stations.Y.y));
  });

  it("scales the main line to the target width", () => {
    const span = toyLayout.stations.Z.x - toyLayout.stations.W.x;
    expect(span).toBeCloseTo(toyLayout.options.targetWidth, 5);
  });

  it("copes with an empty network", () => {
    const empty = computeLayout({ disclaimer: "", stations: [], blocks: [] });
    expect(empty.stationList).toEqual([]);
    expect(findMainLine([], [])).toEqual([]);
  });
});

describe("trainPoint", () => {
  const seg = layout.segments.find((s) => s.id === "SGP-DVG") as NonNullable<ReturnType<typeof layout.segments.find>>;
  const first = seg.blocks[0];

  it("puts a forward train at the start of its block with offset 0", () => {
    const p = trainPoint(layout, { block_id: first.id, offset_km: 0, direction: "fwd", at_station: null });
    expect(p?.x).toBeCloseTo(seg.a.x, 5);
  });

  it("measures a reverse train's offset from the far end of the block", () => {
    const p = trainPoint(layout, { block_id: first.id, offset_km: 0, direction: "rev", at_station: null });
    const end = seg.a.x + (first.lengthKm / seg.lengthKm) * (seg.b.x - seg.a.x);
    expect(p?.x).toBeCloseTo(end, 5);
  });

  it("moves forward trains to the right and reverse trains to the left as the offset grows", () => {
    const at = (offset_km: number, direction: "fwd" | "rev") =>
      trainPoint(layout, { block_id: first.id, offset_km, direction, at_station: null })?.x ?? NaN;
    expect(at(5, "fwd")).toBeGreaterThan(at(1, "fwd"));
    expect(at(5, "rev")).toBeLessThan(at(1, "rev"));
  });

  it("runs the two directions of a double line on different rails, and one rail on a single line", () => {
    const rails = (id: string) => [
      trainPoint(layout, { block_id: id, offset_km: 2, direction: "fwd", at_station: null })?.y ?? 0,
      trainPoint(layout, { block_id: id, offset_km: 2, direction: "rev", at_station: null })?.y ?? 0,
    ];
    const [f, r] = rails(first.id);
    expect(f).toBeLessThan(r);
    const [sf, sr] = rails("BHP-GNK-1");
    expect(sf).toBeCloseTo(sr, 5);
  });

  it("uses the station node for a train at a station, and null for unknown places", () => {
    const p = trainPoint(layout, { block_id: null, offset_km: 0, direction: null, at_station: "VDJ" });
    expect(p).toEqual({ x: layout.stations.VDJ.x, y: layout.stations.VDJ.y });
    expect(trainPoint(layout, { block_id: "NOPE-1", offset_km: 0, direction: "fwd", at_station: null })).toBeNull();
  });

  it("clamps an offset beyond the block end", () => {
    const p = trainPoint(layout, { block_id: first.id, offset_km: 999, direction: "fwd", at_station: null });
    const end = seg.a.x + (first.lengthKm / seg.lengthKm) * (seg.b.x - seg.a.x);
    expect(p?.x).toBeCloseTo(end, 5);
  });
});

describe("affectedBlockIds", () => {
  it("resolves block ids, station codes and the whole network", () => {
    expect(affectedBlockIds(layout, ["BHP-GNK-1"])).toEqual(["BHP-GNK-1"]);
    expect(affectedBlockIds(layout, [])).toHaveLength(mockNetwork.blocks.length);
    const atStation = affectedBlockIds(layout, ["VDJ"]);
    expect(atStation).toContain("MJG-VDJ-1");
    expect(atStation).toContain("VDJ-PTK-1");
    expect(affectedBlockIds(layout, ["NOWHERE"])).toEqual([]);
  });
});

describe("computeLayoutForAspect", () => {
  const ratio = (l: { width: number; height: number }) => l.width / l.height;

  it("makes the map taller for a squarer canvas, keeping the main line's width", () => {
    const wide = computeLayoutForAspect(mockNetwork, 2.75);
    const square = computeLayoutForAspect(mockNetwork, 1.25);
    expect(ratio(square)).toBeLessThan(ratio(wide));
    expect(square.height).toBeGreaterThan(wide.height);
    expect(Math.abs(square.width - wide.width)).toBeLessThan(wide.width * 0.2);
  });

  it("gets close to the wanted shape", () => {
    expect(ratio(computeLayoutForAspect(mockNetwork, 1.75))).toBeGreaterThan(1.4);
    expect(ratio(computeLayoutForAspect(mockNetwork, 1.75))).toBeLessThan(2.2);
  });

  it("keeps every station and block, and falls back to the default for a bad aspect", () => {
    const stretched = computeLayoutForAspect(mockNetwork, 1.5);
    expect(stretched.stationList).toHaveLength(mockNetwork.stations.length);
    expect(Object.keys(stretched.blocks)).toHaveLength(mockNetwork.blocks.length);
    expect(computeLayoutForAspect(mockNetwork, 0).height).toBe(computeLayout(mockNetwork).height);
  });
});
