import { describe, expect, it } from "vitest";

import { CONFLICT_KINDS, SEVERITIES, TRAIN_CATEGORIES, TRAIN_STATUSES } from "../api/types";
import { mockSnapshot } from "./index";

describe("mock snapshot", () => {
  it("uses only known enum values", () => {
    for (const t of mockSnapshot.trains) {
      expect(TRAIN_CATEGORIES).toContain(t.category);
      expect(TRAIN_STATUSES).toContain(t.status);
    }
    for (const c of mockSnapshot.conflicts) {
      expect(SEVERITIES).toContain(c.severity);
      expect(CONFLICT_KINDS).toContain(c.kind);
    }
  });

  it("has consistent references", () => {
    const trainIds = new Set(mockSnapshot.trains.map((t) => t.id));
    const conflictIds = new Set(mockSnapshot.conflicts.map((c) => c.id));
    for (const c of mockSnapshot.conflicts) c.train_ids.forEach((id) => expect(trainIds).toContain(id));
    for (const r of mockSnapshot.recommendations) {
      r.conflict_ids.forEach((id) => expect(conflictIds).toContain(id));
    }
  });

  it("positions have exactly one of block_id / at_station", () => {
    for (const t of mockSnapshot.trains) {
      if (t.position) expect((t.position.block_id === null) !== (t.position.at_station === null)).toBe(true);
    }
  });
});
