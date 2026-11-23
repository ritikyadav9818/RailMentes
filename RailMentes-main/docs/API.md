# RailMentes API contract

Source of truth: [`backend/app/models/schemas.py`](../backend/app/models/schemas.py) (shared data) and
[`backend/app/api/requests.py`](../backend/app/api/requests.py) (request bodies).
TypeScript mirror: [`frontend/src/api/types.ts`](../frontend/src/api/types.ts).
A full example frame: [`frontend/src/mocks/snapshot.json`](../frontend/src/mocks/snapshot.json).
Interactive docs while the server runs: <http://127.0.0.1:8000/docs>.

Conventions
- Base URL `http://127.0.0.1:8000`, JSON everywhere. CORS allows `http://localhost:5173` (and `http://127.0.0.1:5173`). All data is synthetic.
- Time is in **simulation minutes since scenario start** (= ticks). `sim_time` is the same instant as an ISO datetime, for display only.
- Optional values are always sent as explicit `null` (never omitted).
- Errors are `{"detail": ...}`: `400` a valid request the simulation refuses (e.g. unknown train; the message says why), `404` unknown id, `409` wrong state (scenario already finished), `422` malformed body (FastAPI lists the offending fields).
- One scenario is active at a time. Requests are processed in order; changes become visible in the next snapshot.

## REST

### `GET /health`
`{"status": "ok"}`.

### `GET /network`
Static network, fetched once. Returns `NetworkInfo`.
```json
{
  "disclaimer": "Fictional network inspired by Indian railways; not real data.",
  "stations": [
    {"code": "VDJ", "name": "Vindhyapur Junction", "size": 1, "platforms": 6, "is_junction": true, "freight_only": false}
  ],
  "blocks": [
    {"id": "BHP-GNK-1", "from_code": "BHP", "to_code": "GNK", "length_km": 10.67, "line": "single", "speed_limit_kmph": 100}
  ]
}
```

### `GET /state`
Current `StateSnapshot` (same object as one WebSocket frame; see `snapshot.json` for a complete example).
Abridged:
```json
{
  "tick": 135, "sim_time": "2026-01-15T08:15:00", "running": true, "strategy": "no_control",
  "trains": [{"id": "22401", "category": "express", "priority": 3, "delay_min": 12, "status": "running",
              "position": {"block_id": "BHP-GNK-1", "offset_km": 5.2, "direction": "fwd", "at_station": null}, "...": "..."}],
  "blocks": [{"block_id": "BHP-GNK-1", "train_id": "22401", "direction": "fwd", "closed": false}],
  "disruptions": [], "conflicts": [], "recommendations": [],
  "kpis": {"strategy": "no_control", "avg_delay_min": 8.4, "punctuality_pct": 62.0, "throughput_per_hour": 5.5,
           "conflicts_avoided": 0, "prediction_mae_min": null, "prediction_rmse_min": null}
}
```
Notes: `blocks` has one row per claimed block (a double line can hold one train per direction) plus closed free blocks. `position` is `null` for trains that have not started or have finished. Offsets are measured in the train's direction of travel.

### `GET /scenario`
Current configuration and progress (`ScenarioInfo`):
`{"seed": 42, "intensity": "none", "month": 1, "speed": 1.0, "running": false, "tick": 0, "finished": false}`.

### `POST /scenario/start`
Start (or resume) the simulation; calling it while running is harmless.
Request (every field optional, body may be omitted): `{"seed": 42, "strategy": "no_control", "speed": 5.0}`.
- `seed`: a different seed rebuilds the scenario at tick 0 first (keeping intensity and month).
- `strategy`: `no_control`, `fcfs`, `priority` or `cpsat` (the CP-SAT optimizer; it was called `ai_optimizer` in the first draft of the contract, which is now rejected with `422`). The chosen strategy stays selected across resets and fills `recommendations` in every snapshot (see below). It only *recommends*: nothing is applied until the controller applies it (`POST /actions`).
- `speed`: ticks (simulated minutes) per real second, **0.5 to 20** (default 1.0). Outside the range: `422`.

Response: `StateSnapshot` with `running: true`. `409` if the scenario has already finished (reset first).
The simulation stops by itself when every train has finished its route.

### `POST /scenario/pause`
No body. Response: `StateSnapshot` with `running: false`; state is kept, `start` resumes.

### `POST /scenario/reset`
Rebuild the scenario at tick 0, paused. Same settings give an identical run.
Request (all optional; missing fields keep their current value): `{"seed": 42, "intensity": "medium", "month": 11}`.
- `intensity`: `none | low | medium | high` (amount of random disruptions).
- `month`: 1-12; sets the date in snapshots and how likely fog is (Nov-Feb: mostly fog).

Response: `StateSnapshot` at tick 0.

### `POST /scenario/speed`
`{"speed": 10}` -> `{"speed": 10.0}`. Takes effect from the next tick; works while running or paused (0.5 to 20, else `422`).

### `POST /actions`
Two request forms (sending both, or neither, is a `422`).

1. Manual control action (hold or precedence), validated against the running simulation:
```json
{"action": {"kind": "hold", "train_id": "22401", "at_station": "GNK", "hold_minutes": 6, "reason": "Let freight clear"}}
{"action": {"kind": "precedence", "train_id": "22401", "at_station": "GNK", "other_train_id": "12951", "reason": "Premium goes first"}}
```
Response `{"status": "queued", "applies_at_tick": 136}`: the engine applies it at the start of the next tick.
`400` with a plain-language `detail` if the train is unknown, does not call at that station, has already left it, or yields to itself. `hold` needs `hold_minutes`, `precedence` needs `other_train_id` (else `422`).

2. Decision on a recommendation: `{"recommendation_id": "r-001", "decision": "apply"}` (`apply | ignore | undo`). The ids come from `recommendations` in the snapshot.
   - `apply`: queues the recommendation's action (same as form 1). Response `{"status": "applied", "recommendation_id": "r-001"}`.
   - `ignore`: the recommendation stays in the list with status `ignored` and is not proposed again. `undo` turns an ignored one back into `proposed`; an applied action cannot be undone (`400`).
   - `404` unknown id (also when the conflict has gone away and the recommendation expired); `409` already decided, or the train has moved on so the action is no longer valid.

### `POST /disruptions`
Inject a manual disruption now (for the dashboard's inject button). Returns the `Disruption` with status `201`.
```json
{"kind": "fog", "duration_min": 45, "target_ids": [], "speed_factor": 0.6, "description": "optional"}
```
`kind`: `fog | weather_slowdown | signal_failure | block_closure | maintenance | late_departure`. `speed_factor` defaults per kind (fog 0.6, weather 0.8, signal 0.3, closures 0). `target_ids`: block ids or station codes (`[]` = whole network); `late_departure` takes one train id that has not left yet, with `duration_min` as the lateness. Manual disruptions are numbered `m-001`, `m-002`, ...
`400` for unknown targets or rules broken (closures need a target and factor 0), `422` for malformed fields. Connected WebSocket clients get a snapshot immediately.

### `GET /kpis`
`KPI` per implemented strategy (`no_control`, `fcfs`, `priority`, `cpsat`) for the current scenario, each run headless to the end of the day with the same timetable and disruptions. The runs happen in **background worker processes**, so the call never blocks (see "Status while computing" below):
```json
{"no_control": {"strategy": "no_control", "avg_delay_min": 10.96, "punctuality_pct": 48.0, "throughput_per_hour": 0.93,
                "conflicts_avoided": 0, "prediction_mae_min": null, "prediction_rmse_min": null},
 "fcfs": {"...": "..."}, "priority": {"strategy": "priority", "avg_delay_min": 10.52, "...": "...", "conflicts_avoided": 5}}
```
- `avg_delay_min`: mean delay, early trains count as 0. `punctuality_pct`: trains at most 5 min late. `throughput_per_hour`: trains finished per simulated hour.
- `conflicts_avoided` = how many fewer real "train waited >= 3 min for a block held by another train" events the strategy had than no control (never negative; 0 for no control).
- `prediction_mae_min` / `prediction_rmse_min` stay `null` here (model errors are in `docs/RESULTS.md`).
- The runs use the generated scenario for the current seed/intensity/month (manual disruptions injected later are not included) and the delay model if one is loaded. Cached per seed/intensity/month. The numbers are computed by background workers: the server starts the job when it starts and after every `reset` / new seed (and on the first request if nobody started it). Cached per seed/intensity/month; once ready, calls are instant and the `200` body is unchanged.

**Status while computing.** Until all four strategies are finished the answer is `202 Accepted` with a `Retry-After: 2` header (seconds) and this body, so the UI can show a spinner and poll:
```json
{"status": "computing", "done": ["no_control", "fcfs"], "total": 4, "retry_after_s": 2}
```
`503` with a `detail` message if a worker crashed (the next call starts the job again). `GET /kpis/detail` behaves the same way. Typical time to ready: about 10 s without the ML model, about 1-2 min with it. A full day under `cpsat` is roughly 8-20 s of CPU on its own worker; the live simulation is not slowed.

### `GET /kpis/detail`
Same runs, full numbers (`RunKpis`, additional to `/kpis`; `202` while computing, exactly like `/kpis`):
```json
{"priority": {"strategy": "priority", "end_tick": 1455, "trains_total": 25, "trains_finished": 25, "avg_delay_min": 10.52,
              "punctuality_pct": 48.0, "throughput_per_hour": 0.93, "priority_weighted_delay": 554.0,
              "conflicts_detected": 14, "actions_applied": 2, "blocking_events": 11}}
```
`priority_weighted_delay` = sum of train priority (premium 4 ... freight 1) x delay in minutes. `conflicts_detected` = distinct conflicts the detector flagged during the run. `actions_applied` = holds and precedences applied. `blocking_events` = real waits of at least 3 min caused by another train.

### `GET /benchmark/summary?variant=ml`
Read-only. Serves the saved 20-seed benchmark so the frontend never reads repository files. `variant`: `ml` (default; the ML delay model in the loop, `docs/results/benchmark_summary.csv`) or `persistence` (no ML model, `benchmark_persistence_summary.csv`); anything else is `422`. Produced by `scripts/run_benchmark.py`; nothing is computed here.
```json
{"variant": "ml", "label": "ML delay model in the loop (headline)", "source_file": "benchmark_summary.csv", "seeds": 20,
 "rows": [{"intensity": "low", "strategy": "cpsat", "runs": 20,
           "mean": {"avg_delay_min": 7.99, "punctuality_pct": 67.4, "throughput_per_hour": 0.93, "priority_weighted_delay": 496.85, "actions_applied": 2.3},
           "std":  {"avg_delay_min": 2.56, "punctuality_pct": 6.52, "throughput_per_hour": 0.01, "priority_weighted_delay": 179.6, "actions_applied": 0.98}}],
 "disclaimer": "Synthetic data, simulation only."}
```
`mean` / `std` are over the `runs` seeds (standard deviation across seeds, not a confidence interval). One row per intensity (`low`, `medium`, `high`) and strategy. Errors: `404` with `Benchmark results not found (<file>). Run scripts/run_benchmark.py to create them.` if the file is missing; `500` with a message if it is unreadable or empty. The directory is `Settings.results_dir` (default `docs/results`).

### `GET /trains/{train_id}/explanation?horizon=1&top=5`
Why does the delay model predict this delay? One train, one upcoming station, computed **on request** (never per tick) with SHAP.
- `horizon`: 1 = next station (default), 2 = the one after, 3. `top`: how many factors to list (1-10, default 5).

```json
{"train_id": "T104", "station": "JNC", "horizon": 1, "model_source": "lightgbm",
 "current_delay_min": 12.0, "expected_change_min": 0.1, "predicted_delay_min": 17.4,
 "factors": [{"feature": "fog_active", "value": 1.0, "effect_min": 3.9},
             {"feature": "trains_in_next_blocks", "value": 2.0, "effect_min": 1.2}],
 "other_effect_min": 0.2}
```
The numbers add up: `predicted_delay_min = current_delay_min + expected_change_min + sum(factors.effect_min) + other_effect_min`.
Every effect is in minutes added to (or, if negative, taken off) the train's current delay. `value` is the feature's value for that train
(`null` if not available). Errors: `404` unknown train, `400` train not on the line or fewer than `horizon` stations ahead,
`503` no delay model loaded (not trained yet, or switched off); the `detail` says which.

## Conflicts and recommendations in the snapshot
`conflicts` (every strategy, including `no_control`) lists the conflicts the detector expects in the next 60 simulated minutes, earliest first. One entry per pair of trains, stable id `c-<train>-<train>`:
```json
{"id": "c-22405-54306", "kind": "single_line_meeting", "severity": "high", "train_ids": ["22405", "54306"],
 "location": "BHP-GNK-1", "time_min": 955, "description": "Express 22405 and Passenger 54306 run in opposite directions on the single line BHP-GNK at 15:55. Passenger 54306 would lose about 12 min."}
```
`kind`: `single_line_meeting`, `overtaking` (faster train arrives behind a slower one, no overtaking between stations) or `block` (same block, e.g. a junction merge); `platform` is not produced. `train_ids` = [the train that gets there first, the one that would wait]. `location` is a block id. `severity` = predicted wait x highest priority involved (low / medium / high / critical). The method is described in `backend/app/optimizer/conflicts.py` and its accuracy in `docs/RESULTS.md`.

`recommendations` (`fcfs` and `priority` only; empty for `no_control`) holds one entry per conflict the strategy wants to act on:
```json
{"id": "r-003", "strategy": "priority", "status": "proposed", "conflict_ids": ["c-F7701-22401"], "expected_delay_saved_min": 8.0,
 "action": {"kind": "precedence", "train_id": "F7701", "at_station": "DVG", "hold_minutes": null, "other_train_id": "22401",
            "reason": "Priority rule: Express 22401 (priority 3) outranks Goods F7701 (1). Conflict at DVG-KLP-1 around 09:12. Goods F7701 waits at DVG until Express 22401 has passed."}}
```
`expected_delay_saved_min` = the wait the favoured train avoids (0 for FCFS, which only keeps the natural order). Ids (`r-001`, ...) are stable while the scenario runs; a `proposed` entry disappears when its conflict goes away; `applied` and `ignored` entries stay (last 30). Reset clears the list.

## Delay model in the snapshot
`next_stations[].predicted_min` = scheduled time + the delay model's prediction (LightGBM, trained by `scripts/train_model.py`).
Without a model file, or with `USE_ML_MODEL=false` in `.env`, it falls back to scheduled + current delay ("persistence"), which is what it was
before the model existed. Shapes and fields of every message are unchanged. Stations after the 3rd use the 3rd station's predicted delay.

## How `Disruption` fields are used
- `fog`, `weather_slowdown`: `speed_factor` (above 0) scales train speed on `target_ids` while `start_tick <= tick < end_tick`.
- `signal_failure`: same; factor 0 means the block cannot be entered.
- `block_closure`, `maintenance`: factor 0 and at least one target.
- `late_departure`: `target_ids` is `[train_id]`; `end_tick - start_tick` is how many minutes late the train leaves its origin.
- `target_ids` holds block ids or station codes (a station affects the blocks touching it); `[]` means the whole network.
- A snapshot lists only disruptions active at its tick; closed blocks appear in `blocks` with `closed: true`.

## WebSocket `WS /ws/state`

Server to client only; control happens through REST. Any number of clients may connect. Every message is an envelope:
```json
{"type": "snapshot", "seq": 42, "data": { "...StateSnapshot..." }}
```
| `type` | `data` | When |
|---|---|---|
| `hello` | `{"protocol": 1, "server_time": "2026-10-03T10:00:00+00:00"}` | right after connecting (`seq` 0) |
| `snapshot` | `StateSnapshot` | immediately after `hello` (latest state, `seq` 1), then after every tick, and after start / pause / reset / injected disruptions |
| `error` | `{"code": "...", "message": "..."}` | reserved for server-side problems; not sent yet |

`seq` increases by 1 per message per connection; a gap means a slow client lost frames (the server drops the oldest frames of a client that falls behind), so the client may call `GET /state`.
Reconnect: client retries with exponential backoff (1 s, 2 s, 4 s ... capped at 15 s) and replaces its state with the first `snapshot` it receives. While paused, no snapshots are sent except in reply to start, pause, reset or an injected disruption. Anything a client sends is ignored.

## Not yet in the contract (later phases)
- Auto-applying recommendations in a live run (today the controller applies them; the headless comparison applies all of them).
- Per-train prediction history.

## CP-SAT recommendations (`strategy: "cpsat"`)
Same `Recommendation` shape as the other strategies. `action.reason` always starts with `CP-SAT plan:` and names the hold or precedence, the train that gets through and the saving, e.g. `CP-SAT plan: hold Passenger 54101 for 7 min at GNK so Express 12001 passes; saves 11 weighted delay-minutes (6 min of plain delay).` `expected_delay_saved_min` is the *plain* delay minutes saved over all trains in the same group of trains; the weighted figure is in the reason. If the solver found no plan the reason starts with `CP-SAT fallback to the priority rule (...)` and the action is the priority rule's.
