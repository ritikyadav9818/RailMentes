/**
 * Polling for GET /kpis. The backend answers 202 + Retry-After while the four strategy runs are
 * computed in the background, then 200 with the report. This module never leaves the caller without
 * a state: every step reports "loading", "computing" (with progress) or "error".
 */
import type { KpiProgress, KpiReport } from "../api/types";

export type KpiPollState =
  | { phase: "loading" }
  | { phase: "computing"; done: number; total: number; doneNames: string[]; waitedS: number }
  | { phase: "ready"; report: KpiReport }
  | { phase: "error"; message: string; status: number | null };

export interface KpiResponse {
  status: number;
  body: KpiReport | KpiProgress;
  retryAfterS: number | null;
}

export const MIN_RETRY_S = 1;
export const MAX_RETRY_S = 10;
export const DEFAULT_RETRY_S = 2;
/** Give up (with a message and a retry button) after this long. */
export const MAX_WAIT_S = 420;

/** Seconds to wait before the next poll: the Retry-After header, else the body's hint, kept within sane limits. */
export function retryDelayS(headerS: number | null, body: Partial<KpiProgress> | null): number {
  const raw = headerS ?? body?.retry_after_s ?? DEFAULT_RETRY_S;
  return Math.min(MAX_RETRY_S, Math.max(MIN_RETRY_S, raw));
}

export function isProgress(body: KpiReport | KpiProgress): body is KpiProgress {
  return (body as KpiProgress).status === "computing";
}

export interface PollOptions {
  fetchKpis: (signal: AbortSignal) => Promise<KpiResponse>;
  onState: (state: KpiPollState) => void;
  signal: AbortSignal;
  /** injectable for tests */
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

export function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const stop = () => {
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", stop);
      resolve();
    }, ms);
    signal.addEventListener("abort", stop, { once: true });
  });
}

function messageOf(error: unknown): { message: string; status: number | null } {
  const status = typeof (error as { status?: unknown })?.status === "number" ? (error as { status: number }).status : null;
  const message = error instanceof Error ? error.message : "Could not load the KPIs";
  return { message: status === 0 ? "Cannot reach the backend" : message, status };
}

/** Poll until the report is ready, an error happens, the time limit passes or the signal aborts. */
export async function pollKpis({ fetchKpis, onState, signal, sleep = abortableSleep }: PollOptions): Promise<void> {
  let waitedS = 0;
  onState({ phase: "loading" });
  while (!signal.aborted) {
    let response: KpiResponse;
    try {
      response = await fetchKpis(signal);
    } catch (error) {
      if (signal.aborted) return;
      onState({ phase: "error", ...messageOf(error) });
      return;
    }
    if (signal.aborted) return;
    if (response.status !== 202 || !isProgress(response.body)) {
      onState({ phase: "ready", report: response.body as KpiReport });
      return;
    }
    const progress = response.body;
    onState({ phase: "computing", done: progress.done.length, total: progress.total, doneNames: progress.done, waitedS });
    if (waitedS >= MAX_WAIT_S) {
      onState({ phase: "error", message: "The comparison is taking much longer than expected.", status: null });
      return;
    }
    const delay = retryDelayS(response.retryAfterS, progress);
    await sleep(delay * 1000, signal);
    waitedS += delay;
  }
}
