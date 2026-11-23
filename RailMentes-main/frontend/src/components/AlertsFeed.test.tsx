import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Conflict, StateSnapshot } from "../api/types";
import { mockSnapshot } from "../mocks";
import { resetRailStore, useRailStore } from "../store/useRailStore";
import { useUiStore } from "../store/useUiStore";
import { AlertsPanel } from "./AlertsFeed";

function conflict(id: string, severity: Conflict["severity"], time: number): Conflict {
  return {
    id,
    kind: "block",
    severity,
    train_ids: [`${id}-a`, `${id}-b`],
    location: "AAA-BBB-1",
    time_min: time,
    description: `Conflict ${id}`,
  };
}

function setConflicts(conflicts: Conflict[]) {
  const snapshot: StateSnapshot = { ...mockSnapshot, conflicts, recommendations: [] };
  act(() => useRailStore.setState({ snapshot, dataSource: "live" }));
}

function rows() {
  return within(screen.getByLabelText("Alerts and recommendations")).getAllByRole("listitem");
}

beforeEach(() => {
  window.scrollTo = () => {}; // jsdom does not implement it; Framer Motion calls it when measuring heights
  resetRailStore();
  useUiStore.setState({ alertsOpen: true });
});
afterEach(cleanup);

describe("AlertsPanel list layout", () => {
  it("keeps the gap inside each row (padding), so animating rows cannot overlap their neighbours", () => {
    render(<AlertsPanel />);
    setConflicts([conflict("c1", "high", 100), conflict("c2", "low", 120)]);
    const list = rows()[0].parentElement!;
    expect(list.className).not.toMatch(/space-y/);
    for (const row of rows()) {
      expect(row.className).toContain("overflow-hidden");
      expect(row.className).toMatch(/pb-/);
    }
  });

  it("orders cards by severity and follows a reorder without remounting the other cards", () => {
    render(<AlertsPanel />);
    setConflicts([conflict("c1", "low", 100), conflict("c2", "high", 120)]);
    expect(rows().map((r) => r.textContent)).toEqual([expect.stringContaining("Conflict c2"), expect.stringContaining("Conflict c1")]);
    const c1Before = screen.getByText("Conflict c1").closest("li");

    setConflicts([conflict("c1", "critical", 100), conflict("c2", "high", 120)]);
    expect(rows()[0].textContent).toContain("Conflict c1");
    expect(screen.getByText("Conflict c1").closest("li")).toBe(c1Before);
  });

  it("removes a card once its conflict is gone", async () => {
    render(<AlertsPanel />);
    setConflicts([conflict("c1", "high", 100), conflict("c2", "low", 120)]);
    expect(rows()).toHaveLength(2);
    setConflicts([conflict("c2", "low", 120)]);
    await waitFor(() => expect(screen.queryByText("Conflict c1")).toBeNull());
    expect(rows()).toHaveLength(1);
  });
});
