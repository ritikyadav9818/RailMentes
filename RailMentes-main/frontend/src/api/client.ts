/** Typed REST client for the RailMentes backend (see docs/API.md). */
import { API_URL } from "./config";
import type {
  Action,
  ActionQueued,
  BenchmarkSummary,
  BenchmarkVariant,
  DecisionRequest,
  DecisionResult,
  Disruption,
  DisruptionKind,
  Intensity,
  KpiProgress,
  KpiReport,
  NetworkInfo,
  RecommendationDecision,
  ScenarioInfo,
  StateSnapshot,
  StrategyName,
  TrainExplanation,
} from "./types";

/** Error with the HTTP status (0 = backend unreachable) and the backend's plain-language detail. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI sends {"detail": "text"} or {"detail": [{loc, msg}, ...]}. */
export function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const msgs = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : ""));
      const joined = msgs.filter(Boolean).join("; ");
      if (joined) return joined;
    }
  }
  return fallback;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Result of a request: the HTTP status, the parsed body and the Retry-After header (seconds) if present. */
export interface RawResponse<T> {
  status: number;
  body: T;
  retryAfterS: number | null;
}

async function requestRaw<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<RawResponse<T>> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Cannot reach the backend");
  }
  const text = await res.text();
  const json: unknown = text ? safeParse(text) : null;
  if (!res.ok) throw new ApiError(res.status, detailMessage(json, `${res.status} ${res.statusText}`));
  const retry = Number(res.headers.get("Retry-After"));
  return { status: res.status, body: json as T, retryAfterS: Number.isFinite(retry) && retry > 0 ? retry : null };
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return (await requestRaw<T>(method, path, body, signal)).body;
}

export interface StartBody {
  seed?: number;
  strategy?: StrategyName;
  speed?: number;
}

export interface ResetBody {
  seed?: number;
  intensity?: Intensity;
  month?: number;
}

export interface DisruptionBody {
  kind: DisruptionKind;
  duration_min: number;
  target_ids: string[];
  speed_factor?: number;
  description?: string;
}

export const api = {
  network: (signal?: AbortSignal) => request<NetworkInfo>("GET", "/network", undefined, signal),
  state: (signal?: AbortSignal) => request<StateSnapshot>("GET", "/state", undefined, signal),
  scenario: (signal?: AbortSignal) => request<ScenarioInfo>("GET", "/scenario", undefined, signal),
  start: (body: StartBody = {}) => request<StateSnapshot>("POST", "/scenario/start", body),
  pause: () => request<StateSnapshot>("POST", "/scenario/pause"),
  reset: (body: ResetBody = {}) => request<StateSnapshot>("POST", "/scenario/reset", body),
  setSpeed: (speed: number) => request<{ speed: number }>("POST", "/scenario/speed", { speed }),
  manualAction: (action: Action) => request<ActionQueued>("POST", "/actions", { action }),
  decide: (recommendationId: string, decision: RecommendationDecision) =>
    request<DecisionResult>("POST", "/actions", {
      recommendation_id: recommendationId,
      decision,
    } satisfies DecisionRequest),
  /** 200: `body` is a KpiReport. 202: still computing, `body` is a KpiProgress. */
  kpis: (signal?: AbortSignal) => requestRaw<KpiReport | KpiProgress>("GET", "/kpis", undefined, signal),
  benchmark: (variant: BenchmarkVariant = "ml", signal?: AbortSignal) =>
    request<BenchmarkSummary>("GET", `/benchmark/summary?variant=${variant}`, undefined, signal),
  inject: (body: DisruptionBody) => request<Disruption>("POST", "/disruptions", body),
  explanation: (trainId: string, horizon = 1, top = 5, signal?: AbortSignal) =>
    request<TrainExplanation>(
      "GET",
      `/trains/${encodeURIComponent(trainId)}/explanation?horizon=${horizon}&top=${top}`,
      undefined,
      signal,
    ),
};
