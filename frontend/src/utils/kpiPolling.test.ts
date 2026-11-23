import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { KpiProgress, KpiReport } from "../api/types";
import { MAX_RETRY_S, MAX_WAIT_S, MIN_RETRY_S, pollKpis, retryDelayS, type KpiPollState, type KpiResponse } from "./kpiPolling";

const computing = (done: string[], retry: number | null = 2): KpiResponse => ({
  status: 202,
  retryAfterS: retry,
  body: { status: "computing", done, total: 4, retry_after_s: 2 } as KpiProgress,
});
const ready: KpiResponse = {
  status: 200,
  retryAfterS: null,
  body: { no_control: { strategy: "no_control", avg_delay_min: 10, punctuality_pct: 50, throughput_per_hour: 1, conflicts_avoided: 0, prediction_mae_min: null, prediction_rmse_min: null } } as KpiReport,
};

function harness(responses: (KpiResponse | Error)[]) {
  const states: KpiPollState[] = [];
  const sleeps: number[] = [];
  const abort = new AbortController();
  const queue = [...responses];
  const fetchKpis = vi.fn(async () => {
    const next = queue.shift();
    if (!next) throw new Error("no more responses");
    if (next instanceof Error) throw next;
    return next;
  });
  const sleep = vi.fn(async (ms: number) => {
    sleeps.push(ms);
  });
  const run = () => pollKpis({ fetchKpis, onState: (s) => states.push(s), signal: abort.signal, sleep });
  return { states, sleeps, abort, fetchKpis, sleep, run };
}

describe("retryDelayS", () => {
  it("prefers the Retry-After header, then the body hint, then 2 s", () => {
    expect(retryDelayS(3, { retry_after_s: 7 })).toBe(3);
    expect(retryDelayS(null, { retry_after_s: 7 })).toBe(7);
    expect(retryDelayS(null, null)).toBe(2);
  });

  it("keeps the wait within sane limits so the screen never freezes or hammers the server", () => {
    expect(retryDelayS(0.01, null)).toBe(MIN_RETRY_S);
    expect(retryDelayS(9999, null)).toBe(MAX_RETRY_S);
  });
});

describe("pollKpis", () => {
  it("reports loading, then each computing step with progress, then ready", async () => {
    const h = harness([computing([]), computing(["no_control", "fcfs"]), ready]);
    await h.run();
    expect(h.states.map((s) => s.phase)).toEqual(["loading", "computing", "computing", "ready"]);
    const second = h.states[2];
    expect(second.phase === "computing" && second.done).toBe(2);
    expect(second.phase === "computing" && second.total).toBe(4);
    expect(h.fetchKpis).toHaveBeenCalledTimes(3);
  });

  it("waits by Retry-After between polls and counts the waiting time", async () => {
    const h = harness([computing([], 3), computing([], 5), ready]);
    await h.run();
    expect(h.sleeps).toEqual([3000, 5000]);
    const last = h.states.filter((s) => s.phase === "computing").at(-1);
    expect(last?.phase === "computing" && last.waitedS).toBe(3);
  });

  it("is ready straight away on a 200", async () => {
    const h = harness([ready]);
    await h.run();
    expect(h.states.map((s) => s.phase)).toEqual(["loading", "ready"]);
    expect(h.sleep).not.toHaveBeenCalled();
  });

  it("shows the backend's message on a 503 and stops polling", async () => {
    const h = harness([computing([]), new ApiError(503, "A KPI worker crashed")]);
    await h.run();
    const last = h.states.at(-1);
    expect(last).toEqual({ phase: "error", message: "A KPI worker crashed", status: 503 });
    expect(h.fetchKpis).toHaveBeenCalledTimes(2);
  });

  it("says so when the backend cannot be reached", async () => {
    const h = harness([new ApiError(0, "Cannot reach the backend")]);
    await h.run();
    expect(h.states.at(-1)).toMatchObject({ phase: "error", message: "Cannot reach the backend", status: 0 });
  });

  it("stops quietly when aborted, without a late state", async () => {
    const h = harness([computing([]), ready]);
    h.sleep.mockImplementation(async () => h.abort.abort());
    await h.run();
    expect(h.states.map((s) => s.phase)).toEqual(["loading", "computing"]);
    expect(h.fetchKpis).toHaveBeenCalledTimes(1);
  });

  it("gives up with a message instead of waiting for ever", async () => {
    const many = Array.from({ length: 200 }, () => computing([], 10));
    const h = harness(many);
    await h.run();
    const last = h.states.at(-1);
    expect(last?.phase).toBe("error");
    expect(h.fetchKpis.mock.calls.length * MAX_RETRY_S).toBeGreaterThanOrEqual(MAX_WAIT_S);
  });
});
