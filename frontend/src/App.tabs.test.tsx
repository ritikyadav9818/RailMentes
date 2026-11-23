import { act, cleanup, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError, api } from "./api/client";
import type { BenchmarkSummary, KpiReport } from "./api/types";
import { mockSnapshot } from "./mocks";
import { resetHistoryStore } from "./store/useHistoryStore";
import { resetRailStore, useRailStore } from "./store/useRailStore";
import { useDemoStore } from "./store/useDemoStore";
import { useUiStore } from "./store/useUiStore";

vi.mock("./api/bootstrap", () => ({ connectLive: () => () => {} }));

// the chart views are loaded lazily (D3, Recharts); the first import can take a moment on a busy machine
configure({ asyncUtilTimeout: 10000 });

const row = (intensity: string, strategy: "no_control" | "fcfs" | "priority" | "cpsat", delay: number) => ({
  intensity,
  strategy,
  runs: 20,
  mean: { avg_delay_min: delay, punctuality_pct: 60, throughput_per_hour: 0.93, priority_weighted_delay: 700, actions_applied: 1 },
  std: { avg_delay_min: 2, punctuality_pct: 5, throughput_per_hour: 0.01, priority_weighted_delay: 150, actions_applied: 1 },
});
const summary: BenchmarkSummary = {
  variant: "ml",
  label: "ML delay model in the loop (headline)",
  source_file: "benchmark_summary.csv",
  seeds: 20,
  disclaimer: "",
  rows: (["no_control", "fcfs", "priority", "cpsat"] as const).map((s, i) => row("low", s, 9 - i)),
};
const kpi = (strategy: "no_control" | "fcfs" | "priority" | "cpsat", delay: number) => ({
  strategy,
  avg_delay_min: delay,
  punctuality_pct: 60,
  throughput_per_hour: 0.93,
  conflicts_avoided: 0,
  prediction_mae_min: null,
  prediction_rmse_min: null,
});
const report: KpiReport = { no_control: kpi("no_control", 10), fcfs: kpi("fcfs", 10), priority: kpi("priority", 9), cpsat: kpi("cpsat", 8) };

// load the two lazy chunks once, up front, so no single test pays for importing D3 and Recharts
beforeAll(async () => {
  await import("./components/compare/ComparePage");
  await import("./components/timedistance/TimeDistanceGraph");
}, 60000);

beforeEach(() => {
  resetRailStore();
  resetHistoryStore();
  useUiStore.setState({ alertsOpen: true, trainOpen: true, tab: "map", paletteOpen: false, helpOpen: false, injectKind: null });
  vi.spyOn(api, "benchmark").mockResolvedValue(summary);
  vi.spyOn(api, "kpis").mockResolvedValue({ status: 200, body: report, retryAfterS: null });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const withMockData = () => {
  render(<App />);
  act(() => useRailStore.getState().showMockData());
};

describe("tabs", () => {
  it("shows the three views as an accessible tab list, with Map selected first", () => {
    withMockData();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Map", "Time-distance", "Compare"]);
    expect(screen.getByRole("tab", { name: "Map" }).getAttribute("aria-selected")).toBe("true");
  });

  it("switches with a click and with the 1 / 2 / 3 keys, keeping the KPI strip", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Time-distance" }));
    expect(await screen.findByRole("region", { name: "Time-distance graph" })).toBeTruthy();
    expect(screen.getByText("Trains finished")).toBeTruthy();
    fireEvent.keyDown(window, { key: "3" });
    expect(await screen.findByRole("region", { name: "Strategy comparison" })).toBeTruthy();
    expect(screen.getByText("Trains finished")).toBeTruthy();
    fireEvent.keyDown(window, { key: "1" });
    expect(screen.getByRole("tab", { name: "Map" }).getAttribute("aria-selected")).toBe("true");
  });

  it("moves between tabs with the arrow keys", () => {
    withMockData();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Map" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Time-distance" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Time-distance" }), { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Map" }).getAttribute("aria-selected")).toBe("true");
  });

  it("keeps the map mounted but hidden on the other tabs", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    await screen.findByRole("region", { name: "Strategy comparison" });
    expect(document.getElementById("panel-map")?.hasAttribute("hidden")).toBe(true);
  });

  it("does not steal the number keys while typing in a field", () => {
    withMockData();
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "3" });
    expect(screen.getByRole("tab", { name: "Map" }).getAttribute("aria-selected")).toBe("true");
    input.remove();
  });
});

describe("time-distance tab", () => {
  it("explains what is drawn, including the recording note and the offset-lane note", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Time-distance" }));
    expect(await screen.findByText("actual path recorded since page load")).toBeTruthy();
    expect(screen.getByText(/Branch stations sit on offset lanes/)).toBeTruthy();
    expect(screen.getByText("Planned")).toBeTruthy();
    expect(screen.getByText("Predicted")).toBeTruthy();
    expect(screen.getByRole("img", { name: /Time-distance graph/ })).toBeTruthy();
  });

  it("switches the colour key between train type and delay", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Time-distance" }));
    expect(await screen.findByText("Freight")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delay" }));
    expect(screen.getByText("Severe delay")).toBeTruthy();
  });
});

describe("compare tab", () => {
  it("leads with the caveats", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    const caveats = await screen.findByRole("complementary", { name: "How to read these results" });
    expect(within(caveats).getByText(/Synthetic data, simulation only/)).toBeTruthy();
    expect(within(caveats).getByText(/gains are modest/)).toBeTruthy();
    expect(within(caveats).getByText(/prediction, not a result/)).toBeTruthy();
    expect(within(caveats).getByText(/0\.4 \/ 0\.7 \/ 0\.5 min/)).toBeTruthy();
  });

  it("shows the benchmark table once the summary arrives", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(await screen.findByRole("table")).toBeTruthy();
    expect(screen.getByText("CP-SAT optimizer", { selector: "th" })).toBeTruthy();
    expect(api.benchmark).toHaveBeenCalledWith("ml", expect.anything());
  });

  it("asks for the persistence variant when chosen", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Without (persistence)" }));
    await waitFor(() => expect(api.benchmark).toHaveBeenLastCalledWith("persistence", expect.anything()));
  });

  it("says plainly when the benchmark file is missing, and can retry", async () => {
    vi.spyOn(api, "benchmark").mockRejectedValue(new ApiError(404, "Benchmark results not found (benchmark_summary.csv). Run scripts/run_benchmark.py to create them."));
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    const alert = await screen.findByText(/Benchmark results not found/);
    expect(alert).toBeTruthy();
    expect(screen.getByRole("button", { name: /Try again/ })).toBeTruthy();
  });

  it("says the live comparison needs the backend while offline", async () => {
    withMockData();
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(await screen.findByText(/The backend is offline/)).toBeTruthy();
    expect(api.kpis).not.toHaveBeenCalled();
  });

  it("shows live KPIs for all four strategies when the backend is live", async () => {
    render(<App />);
    act(() => {
      useRailStore.getState().applySnapshot(mockSnapshot, "live");
    });
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(await screen.findByRole("article", { name: "CP-SAT optimizer KPIs" })).toBeTruthy();
    expect(screen.getByRole("article", { name: "No control KPIs" })).toBeTruthy();
    expect(screen.getByText("-20.0% vs no control")).toBeTruthy();
  });

  it("shows a progress state while the backend is still computing", async () => {
    vi.spyOn(api, "kpis").mockResolvedValue({
      status: 202,
      retryAfterS: 2,
      body: { status: "computing", done: ["no_control", "fcfs"], total: 4, retry_after_s: 2 },
    });
    render(<App />);
    act(() => {
      useRailStore.getState().applySnapshot(mockSnapshot, "live");
    });
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(await screen.findByText(/2 of 4 done/)).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Strategies finished" }).getAttribute("aria-valuenow")).toBe("2");
  });

  it("shows the error and a retry button when the KPIs fail", async () => {
    vi.spyOn(api, "kpis").mockRejectedValue(new ApiError(503, "A KPI worker crashed"));
    render(<App />);
    act(() => {
      useRailStore.getState().applySnapshot(mockSnapshot, "live");
    });
    fireEvent.click(screen.getByRole("tab", { name: "Compare" }));
    expect(await screen.findByText("A KPI worker crashed")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Try again/ }).length).toBeGreaterThan(0);
  });
});

describe("command palette and help", () => {
  it("opens with Ctrl+K, filters, and runs the chosen command with Enter", () => {
    withMockData();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const box = screen.getByRole("combobox", { name: "Type a command" });
    fireEvent.change(box, { target: { value: "compare" } });
    expect(screen.getByRole("option", { name: /Go to Compare strategies/ })).toBeTruthy();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(useUiStore.getState().tab).toBe("compare");
    expect(useUiStore.getState().paletteOpen).toBe(false);
  });

  it("moves the selection with the arrow keys", () => {
    withMockData();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const box = screen.getByRole("combobox", { name: "Type a command" });
    fireEvent.change(box, { target: { value: "go to" } });
    expect(screen.getAllByRole("option")[0].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(useUiStore.getState().tab).not.toBe("map");
  });

  it("does not run a disabled command (backend offline) and says why", () => {
    withMockData();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const box = screen.getByRole("combobox", { name: "Type a command" });
    fireEvent.change(box, { target: { value: "inject fog" } });
    const option = screen.getByRole("option", { name: /Inject disruption: Fog/ });
    expect(option.getAttribute("aria-disabled")).toBe("true");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(useUiStore.getState().injectKind).toBeNull();
  });

  it("shows an empty state when nothing matches", () => {
    withMockData();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByRole("combobox", { name: "Type a command" }), { target: { value: "zzzzqq" } });
    expect(screen.getByText(/No command matches/)).toBeTruthy();
  });

  it("opens the shortcut help with ? and lists the palette shortcut", () => {
    withMockData();
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeTruthy();
    expect(screen.getByText("Open the command palette")).toBeTruthy();
  });
});

describe("guided demo captions", () => {
  beforeEach(() => useDemoStore.getState().end());
  afterEach(() => useDemoStore.getState().end());

  it("follows the events, opens the alerts panel and pauses once when the recommendation appears", async () => {
    const pause = vi.spyOn(api, "pause").mockResolvedValue(mockSnapshot);
    render(<App />);
    act(() => useRailStore.getState().applySnapshot({ ...mockSnapshot, running: false, disruptions: [], conflicts: [], recommendations: [] }, "live"));
    act(() => useUiStore.setState({ alertsOpen: false }));
    act(() => useDemoStore.getState().begin());
    expect(screen.getByText(/Guided demo: a foggy January day/)).toBeTruthy();

    const fog = { ...mockSnapshot.disruptions[0], kind: "fog" as const };
    act(() => useRailStore.getState().applySnapshot({ ...mockSnapshot, running: true, disruptions: [fog], conflicts: [], recommendations: [] }, "live"));
    expect(await screen.findByText("1. Fog sets in")).toBeTruthy();

    const proposed = { ...mockSnapshot.recommendations[0], status: "proposed" as const };
    act(() => useRailStore.getState().applySnapshot({ ...mockSnapshot, running: true, disruptions: [fog], conflicts: [], recommendations: [proposed] }, "live"));
    expect(await screen.findByText("3. The optimizer recommends a decision")).toBeTruthy();
    await waitFor(() => expect(pause).toHaveBeenCalledTimes(1));
    expect(useUiStore.getState().alertsOpen).toBe(true);
  });

  it("slows down after the conflict, and carries on if the recommendation has gone by the time it paused", async () => {
    const pause = vi.spyOn(api, "pause").mockResolvedValue(mockSnapshot);
    const start = vi.spyOn(api, "start").mockResolvedValue(mockSnapshot);
    const speed = vi.spyOn(api, "setSpeed").mockResolvedValue({ speed: 4 });
    render(<App />);
    const quiet = { ...mockSnapshot, running: true, disruptions: [], conflicts: [], recommendations: [] };
    act(() => useRailStore.getState().applySnapshot(quiet, "live"));
    act(() => useDemoStore.getState().begin());

    const meeting = { ...mockSnapshot.conflicts[0], kind: "single_line_meeting" as const };
    act(() => useRailStore.getState().applySnapshot({ ...quiet, conflicts: [meeting] }, "live"));
    await waitFor(() => expect(speed).toHaveBeenCalledWith(4));

    const proposed = { ...mockSnapshot.recommendations[0], status: "proposed" as const };
    act(() => useRailStore.getState().applySnapshot({ ...quiet, conflicts: [meeting], recommendations: [proposed] }, "live"));
    await waitFor(() => expect(pause).toHaveBeenCalledTimes(1));

    // the pause arrives, and the recommendation is already gone
    act(() => useRailStore.getState().applySnapshot({ ...quiet, running: false, conflicts: [meeting], recommendations: [] }, "live"));
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(useDemoStore.getState().seen).not.toContain("recommendation");

    // the next recommendation is paused on again
    act(() => useRailStore.getState().applySnapshot({ ...quiet, conflicts: [meeting], recommendations: [proposed] }, "live"));
    await waitFor(() => expect(pause).toHaveBeenCalledTimes(2));
  });

  it("keeps the pause when the recommendation is still there", async () => {
    const pause = vi.spyOn(api, "pause").mockResolvedValue(mockSnapshot);
    const start = vi.spyOn(api, "start").mockResolvedValue(mockSnapshot);
    render(<App />);
    const quiet = { ...mockSnapshot, running: true, disruptions: [], conflicts: [], recommendations: [] };
    act(() => useRailStore.getState().applySnapshot(quiet, "live"));
    act(() => useDemoStore.getState().begin());
    const proposed = { ...mockSnapshot.recommendations[0], status: "proposed" as const };
    act(() => useRailStore.getState().applySnapshot({ ...quiet, recommendations: [proposed] }, "live"));
    await waitFor(() => expect(pause).toHaveBeenCalledTimes(1));
    act(() => useRailStore.getState().applySnapshot({ ...quiet, running: false, recommendations: [proposed] }, "live"));
    await new Promise((r) => setTimeout(r, 50));
    expect(start).not.toHaveBeenCalled();
  });

  it("can be ended with the close button", () => {
    render(<App />);
    act(() => useRailStore.getState().applySnapshot(mockSnapshot, "live"));
    act(() => useDemoStore.getState().begin());
    fireEvent.click(screen.getByRole("button", { name: "End the guided demo" }));
    expect(useDemoStore.getState().active).toBe(false);
  });
});
