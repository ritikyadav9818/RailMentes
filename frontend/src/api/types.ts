/**
 * API types. Mirror of backend/app/models/schemas.py: keep them in sync by hand.
 * Times are simulation minutes since scenario start (== ticks) unless noted.
 * All data is synthetic.
 */

// ---- enums (as string unions) ----
export const TRAIN_CATEGORIES = ["premium", "express", "passenger", "freight"] as const;
export type TrainCategory = (typeof TRAIN_CATEGORIES)[number];

export const TRAIN_STATUSES = [
  "not_started",
  "running",
  "halted_at_station",
  "waiting_for_signal",
  "finished",
] as const;
export type TrainStatus = (typeof TRAIN_STATUSES)[number];

export const SEVERITIES = ["low", "medium", "high", "critical"] as const;
export type Severity = (typeof SEVERITIES)[number];

export const CONFLICT_KINDS = ["block", "platform", "overtaking", "single_line_meeting"] as const;
export type ConflictKind = (typeof CONFLICT_KINDS)[number];

export const DISRUPTION_KINDS = [
  "fog",
  "weather_slowdown",
  "signal_failure",
  "block_closure",
  "late_departure",
  "maintenance",
] as const;
export type DisruptionKind = (typeof DISRUPTION_KINDS)[number];

export type ActionKind = "hold" | "precedence";
export type RecommendationStatus = "proposed" | "applied" | "ignored" | "undone";
export type StrategyName = "no_control" | "fcfs" | "priority" | "cpsat";
export type LineType = "single" | "double";
export type Direction = "fwd" | "rev";

// ---- static network (GET /network) ----
export interface StationInfo {
  code: string;
  name: string;
  size: 1 | 2 | 3;
  platforms: number;
  is_junction: boolean;
  freight_only: boolean;
}

export interface BlockInfo {
  id: string;
  from_code: string;
  to_code: string;
  length_km: number;
  line: LineType;
  speed_limit_kmph: number;
}

export interface NetworkInfo {
  disclaimer: string;
  stations: StationInfo[];
  blocks: BlockInfo[];
}

// ---- live state ----
/** Exactly one of block_id / at_station is non-null. */
export interface Position {
  block_id: string | null;
  /** km covered in this block, in the train's travel direction */
  offset_km: number;
  direction: Direction | null;
  at_station: string | null;
}

export interface StationStop {
  station: string;
  will_stop: boolean;
  scheduled_min: number;
  predicted_min: number;
}

export interface DelayFactor {
  feature: string;
  /** positive adds delay, negative reduces it */
  contribution_min: number;
}

export interface TrainState {
  id: string;
  name: string;
  category: TrainCategory;
  priority: number;
  /** null while not_started or finished */
  position: Position | null;
  speed_kmph: number;
  delay_min: number;
  status: TrainStatus;
  next_stations: StationStop[];
  delay_factors: DelayFactor[];
}

export interface BlockOccupancy {
  block_id: string;
  train_id: string | null;
  direction: Direction | null;
  closed: boolean;
}

export interface Disruption {
  id: string;
  kind: DisruptionKind;
  start_tick: number;
  end_tick: number;
  /** block ids or station codes; empty = whole network */
  target_ids: string[];
  /** 1 = no effect, 0 = fully blocked */
  speed_factor: number;
  description: string;
}

export interface Conflict {
  id: string;
  kind: ConflictKind;
  severity: Severity;
  train_ids: string[];
  location: string;
  time_min: number;
  description: string;
}

export interface Action {
  kind: ActionKind;
  /** the train that is held / that yields */
  train_id: string;
  at_station: string;
  /** HOLD only */
  hold_minutes: number | null;
  /** PRECEDENCE only: the train that goes first */
  other_train_id: string | null;
  reason: string;
}

export interface Recommendation {
  id: string;
  strategy: StrategyName;
  action: Action;
  conflict_ids: string[];
  expected_delay_saved_min: number;
  status: RecommendationStatus;
}

export interface KPI {
  strategy: StrategyName;
  avg_delay_min: number;
  punctuality_pct: number;
  throughput_per_hour: number;
  conflicts_avoided: number;
  prediction_mae_min: number | null;
  prediction_rmse_min: number | null;
}

export interface StateSnapshot {
  tick: number;
  /** ISO datetime, display only */
  sim_time: string;
  running: boolean;
  strategy: StrategyName;
  trains: TrainState[];
  /** only occupied or closed blocks */
  blocks: BlockOccupancy[];
  disruptions: Disruption[];
  conflicts: Conflict[];
  recommendations: Recommendation[];
  kpis: KPI;
}

// ---- GET /kpis ----
/** Only strategies that are implemented appear (today: all four). Sent with HTTP 200 once ready. */
export type KpiReport = Partial<Record<StrategyName, KPI>>;

/**
 * Body of the HTTP 202 answer of GET /kpis and GET /kpis/detail while the background job is running.
 * The response also has a `Retry-After` header (seconds). Poll until the status is 200.
 */
export interface KpiProgress {
  status: "computing";
  /** strategies that are finished */
  done: StrategyName[];
  total: number;
  retry_after_s: number;
}

// ---- GET /kpis/detail ----
/** Full KPI set of one headless run to the end of the day. */
export interface RunKpis {
  strategy: StrategyName;
  /** tick the last train finished */
  end_tick: number;
  trains_total: number;
  trains_finished: number;
  avg_delay_min: number;
  punctuality_pct: number;
  throughput_per_hour: number;
  /** sum of train priority x delay (min) */
  priority_weighted_delay: number;
  /** distinct conflicts the detector flagged during the run */
  conflicts_detected: number;
  /** holds and precedences applied */
  actions_applied: number;
  /** real waits (>= 3 min) of a train for a block held by another train */
  blocking_events: number;
}
export type KpiDetailReport = Partial<Record<StrategyName, RunKpis>>;

// ---- GET /benchmark/summary ----
export type BenchmarkVariant = "ml" | "persistence";
export type BenchmarkMetric = "avg_delay_min" | "punctuality_pct" | "throughput_per_hour" | "priority_weighted_delay" | "actions_applied";

/** One strategy at one intensity: mean and standard deviation over `runs` seeds. */
export interface BenchmarkRow {
  intensity: string;
  strategy: StrategyName;
  runs: number;
  mean: Record<BenchmarkMetric, number>;
  std: Record<BenchmarkMetric, number>;
}

export interface BenchmarkSummary {
  variant: BenchmarkVariant;
  label: string;
  source_file: string;
  seeds: number;
  rows: BenchmarkRow[];
  disclaimer: string;
}

// ---- scenario control ----
export type Intensity = "none" | "low" | "medium" | "high";

/** GET /scenario */
export interface ScenarioInfo {
  seed: number;
  intensity: Intensity;
  month: number;
  /** ticks (simulated minutes) per real second, 0.5 to 20 */
  speed: number;
  running: boolean;
  tick: number;
  finished: boolean;
}

/** One feature's push on a prediction (SHAP), in minutes. */
export interface FeatureEffect {
  feature: string;
  value: number | string | null;
  /** minutes added to the delay (negative = reduces it) */
  effect_min: number;
}

/** GET /trains/{id}/explanation: predicted = current + expected_change + sum(effects) + other */
export interface TrainExplanation {
  train_id: string;
  station: string;
  /** 1 = next station, 2 = the one after, 3 */
  horizon: number;
  model_source: string;
  current_delay_min: number;
  expected_change_min: number;
  predicted_delay_min: number;
  factors: FeatureEffect[];
  other_effect_min: number;
}

/** POST /actions (decision form) request body */
export type RecommendationDecision = "apply" | "ignore" | "undo";
export interface DecisionRequest {
  recommendation_id: string;
  decision: RecommendationDecision;
}

/** POST /actions (decision form) response; 404 unknown/expired id, 409 already decided or no longer valid */
export interface DecisionResult {
  status: RecommendationStatus;
  recommendation_id: string;
}

/** POST /actions (manual form) response */
export interface ActionQueued {
  status: "queued";
  applies_at_tick: number;
}

// ---- WebSocket /ws/state (server -> client) ----
export type WsMessage =
  | { type: "hello"; seq: number; data: { protocol: 1; server_time: string } }
  | { type: "snapshot"; seq: number; data: StateSnapshot }
  | { type: "error"; seq: number; data: { code: string; message: string } };
