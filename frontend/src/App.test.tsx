import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { mockNetwork, mockSnapshot } from "./mocks";
import { resetRailStore, useRailStore } from "./store/useRailStore";
import { useUiStore } from "./store/useUiStore";

// the real connection is not wanted here; the store is filled by hand
vi.mock("./api/bootstrap", () => ({ connectLive: () => () => {} }));

// jsdom is narrow, so the alerts panel would start collapsed; the tests want it open
beforeEach(() => {
  resetRailStore();
  useUiStore.setState({ alertsOpen: true, trainOpen: true });
});
afterEach(cleanup);

describe("App", () => {
  it("shows the project name, the synthetic-data notice and a loading state before any data", () => {
    render(<App />);
    expect(screen.getByText("RailMentes")).toBeTruthy();
    expect(screen.getByText("Synthetic data")).toBeTruthy();
    expect(screen.getByText(/Connecting to the control centre/)).toBeTruthy();
  });

  it("shows the offline-demo badge, KPIs and the alert feed from the mock snapshot", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    expect(screen.getByText("Offline demo data")).toBeTruthy();
    expect(screen.getByText("Average delay")).toBeTruthy();
    expect(screen.getByText(mockSnapshot.kpis.avg_delay_min.toFixed(1))).toBeTruthy();
    expect(screen.getByText("Alerts & recommendations")).toBeTruthy();
    // the map stays hidden until it has a measured size, which jsdom never gives it
    expect(screen.getByLabelText(/Schematic map/)).toBeTruthy();
    // major stations and junctions are labelled at the default zoom; every station has a marker
    for (const s of mockNetwork.stations.filter((x) => x.size === 1 || x.is_junction)) expect(screen.getAllByText(s.code).length).toBeGreaterThan(0);
    for (const s of mockNetwork.stations) expect(document.querySelector(`[data-station="${s.code}"]`)).toBeTruthy();
  });

  it("disables the controls while the backend is offline", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    expect((screen.getByRole("button", { name: /Start|Pause/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("opens the train drawer for the selected train", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    act(() => useRailStore.getState().selectTrain(mockSnapshot.trains[0].id));
    expect(screen.getByRole("complementary", { name: `Train ${mockSnapshot.trains[0].id}` })).toBeTruthy();
    expect(screen.getByText("Next stations")).toBeTruthy();
    expect(screen.getByText("Why late?")).toBeTruthy();
  });
});

describe("side panels", () => {
  it("collapses and expands the alerts panel with the button and the [ key, and remembers it", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    fireEvent.click(screen.getByRole("button", { name: "Collapse alerts panel" }));
    expect(useUiStore.getState().alertsOpen).toBe(false);
    expect(screen.queryByText("Alerts & recommendations")).toBeNull();
    fireEvent.keyDown(window, { key: "[" });
    expect(useUiStore.getState().alertsOpen).toBe(true);
    expect(JSON.parse(localStorage.getItem("railmentes.ui.v1") ?? "{}").alertsOpen).toBe(true);
  });

  it("collapses the train panel to a rail and opens it again when a train is picked", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    act(() => useRailStore.getState().selectTrain(mockSnapshot.trains[0].id));
    fireEvent.keyDown(window, { key: "]" });
    expect(useUiStore.getState().trainOpen).toBe(false);
    expect(screen.queryByText("Next stations")).toBeNull();
    act(() => useRailStore.getState().selectTrain(mockSnapshot.trains[1].id));
    expect(useUiStore.getState().trainOpen).toBe(true);
  });

  it("ignores panel shortcuts while typing in a field", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "[" });
    expect(useUiStore.getState().alertsOpen).toBe(true);
    input.remove();
  });

  it("shows the map toolbar and minimap", () => {
    render(<App />);
    act(() => useRailStore.getState().showMockData());
    expect(screen.getByRole("button", { name: "Fit to screen" })).toBeTruthy();
    expect(screen.getByRole("img", { name: /Minimap/ })).toBeTruthy();
  });
});
