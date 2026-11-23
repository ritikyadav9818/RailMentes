/** Human-readable names for enums and model feature names. */
import type { ConflictKind, DisruptionKind, StrategyName, TrainCategory } from "../api/types";

export const STRATEGY_LABELS: Record<StrategyName, string> = {
  no_control: "No control",
  fcfs: "First come, first served",
  priority: "Priority rule",
  cpsat: "CP-SAT optimizer",
};

export const CATEGORY_LABELS: Record<TrainCategory, string> = {
  premium: "Premium",
  express: "Express",
  passenger: "Passenger",
  freight: "Freight",
};

export const DISRUPTION_LABELS: Record<DisruptionKind, string> = {
  fog: "Fog",
  weather_slowdown: "Weather slowdown",
  signal_failure: "Signal failure",
  block_closure: "Block closure",
  maintenance: "Maintenance",
  late_departure: "Late departure",
};

export const CONFLICT_LABELS: Record<ConflictKind, string> = {
  block: "Block conflict",
  platform: "Platform conflict",
  overtaking: "Overtaking",
  single_line_meeting: "Single-line meeting",
};

export const STATUS_LABELS: Record<string, string> = {
  not_started: "Not started",
  running: "Running",
  halted_at_station: "Halted at station",
  waiting_for_signal: "Waiting for signal",
  finished: "Finished",
};

const FEATURE_LABELS: Record<string, string> = {
  // model features (backend/app/ml/features.py)
  train_category: "Train type",
  priority: "Train priority",
  speed_kmph: "Current speed",
  hour: "Hour of day",
  day_of_week: "Day of week",
  month: "Month",
  delay_now: "Current delay",
  delay_last_arrival: "Delay at last station",
  stations_ahead: "Stations left on route",
  next_will_stop: "Next station is a halt",
  sched_to_s1: "Scheduled time to next station",
  sched_to_s2: "Scheduled time to 2nd station",
  sched_to_s3: "Scheduled time to 3rd station",
  dist_to_s1_km: "Distance to next station",
  dist_to_s2_km: "Distance to 2nd station",
  dist_to_s3_km: "Distance to 3rd station",
  trains_in_next_blocks: "Trains in the next blocks",
  opposing_trains_in_next_blocks: "Opposing trains ahead",
  next_hop_single_line: "Single line to next station",
  single_line_blocks_ahead: "Single-line blocks ahead",
  fog_active: "Fog on the route",
  weather_slowdown_active: "Weather slowdown",
  signal_failure_active: "Signal failure",
  closure_active: "Block closure",
  min_speed_factor: "Slowest speed limit ahead",
  // short names used in the mock snapshot
  fog: "Fog",
  upstream_delay: "Delay carried from upstream",
  peak_hour: "Peak hour",
};

/** "trains_in_next_blocks" -> "Trains in the next blocks"; unknown names get a plain fallback. */
export function featureLabel(feature: string): string {
  const known = FEATURE_LABELS[feature];
  if (known) return known;
  const spaced = feature.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** "Vindhyapur Junction" -> "Vindhyapur Jn", "Tilakpur Terminus" -> "Tilakpur Term." */
export function shortStationName(name: string): string {
  return name.replace(/\bJunction\b/, "Jn").replace(/\bTerminus\b/, "Term.").replace(/\bCentral\b/, "Ctl");
}
