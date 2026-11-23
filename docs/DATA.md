# RailMentes training data

> **All data in this project is synthetic.** It comes from a simulation of a *fictional* railway corridor
> (invented stations, distances and timetables). It is **not** real Indian Railways data, it is not calibrated
> against any real railway, and no result computed from it should be presented as real-world performance.

## 1. How it is generated

The generator runs the **same simulation engine** that powers the live dashboard, headless, for many days.
So the training data and the live system follow the same rules (block safety, single-line crossings,
disruptions), and delay propagation (a slow train delays the ones behind it) comes from the simulation itself,
not from hand-written formulas.

```
plan_days(n, seed)  ->  for each day: calendar date + day seed + disruption intensity
Scenario(...).build ->  engine for that day (timetable, random disruptions, optional realism)
engine.step() loop  ->  every time a train leaves/passes a station, record a pending event
after the step      ->  snapshot -> features.build_features(...)   (one row per event, features only)
day finished        ->  targets = the train's real arrival delay at its next 3 stations
```

Code: [`backend/app/ml/datagen.py`](../backend/app/ml/datagen.py) (generator),
[`backend/app/ml/features.py`](../backend/app/ml/features.py) (the single shared feature function),
[`scripts/generate_data.py`](../scripts/generate_data.py) (command line).

Reproduce (PowerShell, repo root; the default 180 days take about 20 seconds):

```powershell
.\backend\.venv\Scripts\python.exe scripts\generate_data.py                       # 180 days -> data\railmentes_runs.csv
.\backend\.venv\Scripts\python.exe scripts\generate_data.py --days 365 --seed 7 --sqlite
```

Options: `--days`, `--seed`, `--start-date`, `--out`, `--sqlite`, `--sample-rows`, `--no-realism`, `--workers`.
The same seed always gives a byte-identical dataset. `data/` is git-ignored; a 500-row sample is committed in
[`data/sample/`](../data/sample/railmentes_runs_sample.csv).

### The simulated days

- **Dates:** consecutive calendar days from 2025-10-01 (default 180 days = October to March, which contains the
  fog season). The date gives hour, day of week and month.
- **Timetable:** 25 trains per day (4 premium, 7 express, 8 passenger, 6 freight) on 15 stations; departure times
  jitter randomly around fixed windows each day (see `simulation/timetable.py`).
- **Disruption intensity per day** (drawn at random): none 35%, low 35%, medium 20%, high 10%, i.e. mostly calm,
  some medium, few high. Intensity sets the number of random disruptions that day (fog or rain slowdown over a
  stretch of the main line, signal failures, track closures, late departures; durations capped at 120 min, closures
  at 90 min). In **November to February** the weather event is fog 90% of the time; in other months only 10%
  (otherwise it is a rain slowdown).
- **Extra realism** (on in the generator, switch off with `--no-realism`; **off by default in `Scenario`**, so earlier
  behaviour and tests are unchanged): every halt at an intermediate station gets a random extra dwell time
  (exponential, mean = category base x rush-hour factor 1.8 (07-10 h, 17-20 h) x day-of-week factor, capped at 8 min).
  Category bases: premium 0.4, express 0.8, passenger 1.4 min, freight 0. Day-of-week factors (Mon-Sun):
  1.0, 0.9, 0.9, 1.0, 1.25, 1.1, 1.35 (busy Fridays and weekends). These numbers are invented for plausibility.

## 2. One row = one station departure

A row is created each time a train starts the stretch after a station: leaving its origin, leaving a station where
it halted, or passing through a station without stopping. The last station of a route has no row (nothing ahead).
With 25 trains this gives **208 rows per day** (the timetable pattern is the same every day), 37,440 rows for 180 days.

### Identification columns (not model inputs)

| Column | Meaning |
|---|---|
| `scenario_id` | day id, e.g. `D0042-S1596981835` (day index and seed) |
| `day` | calendar date of the day (ISO) |
| `seed` | seed of that day (rebuilds the identical day with `Scenario`) |
| `intensity` | the day's disruption intensity. **Not a feature**: a controller does not know it in advance |
| `train_id`, `station`, `station_idx` | which train, which station it just left or passed, and its position in the route |
| `tick` | simulated minutes since 00:00 of `day` when it happened |

### Feature columns (model inputs, all known at that moment)

Built by `build_features(snapshot, train, network, last_arrival_delay)`. Delays are minutes, negative = early.

| Feature | Meaning |
|---|---|
| `train_category` | premium / express / passenger / freight |
| `priority` | 4 (premium) to 1 (freight) |
| `speed_kmph` | current speed |
| `hour`, `day_of_week`, `month` | from the simulated clock (Monday = 0) |
| `delay_now` | current delay |
| `delay_last_arrival` | delay when it reached the station it just left |
| `stations_ahead` | number of known stations ahead (1 to 4) |
| `next_will_stop` | 1 if the next station is a halt |
| `sched_to_s1`, `sched_to_s2`, `sched_to_s3` | scheduled minutes from now until arrival at the 1st / 2nd / 3rd next station |
| `dist_to_s1_km`, `dist_to_s2_km`, `dist_to_s3_km` | kilometres to those stations |
| `trains_in_next_blocks` | other trains in the next 6 blocks of the train's route (congestion) |
| `opposing_trains_in_next_blocks` | of those, trains running the opposite way on a single-line block |
| `next_hop_single_line` | 1 if the stretch to the next station has single-line blocks |
| `single_line_blocks_ahead` | single-line blocks among the next 6 |
| `fog_active`, `weather_slowdown_active`, `signal_failure_active`, `closure_active` | 1 if such a disruption is active on any of the next 6 blocks |
| `min_speed_factor` | slowest active speed factor there (1 = none, 0 = a block is closed) |

`sched_to_s2/s3` and `dist_to_s2/s3_km` are **empty** when fewer than 2 or 3 stations remain on the route.
All other feature columns are never missing.

### Target columns

| Target | Meaning |
|---|---|
| `target_delay_1` | the train's **arrival** delay (actual minus scheduled arrival, whole minutes) at the next station |
| `target_delay_2`, `target_delay_3` | same for the 2nd and 3rd next station (**empty** near the end of the route) |

### No future information

Features are computed from the snapshot at that instant (`tests/test_features.py` proves that two runs that only
differ in the future give the same features). Disruptions that are scheduled but not yet active are not visible.
The only value that is not inside a snapshot, `delay_last_arrival`, is the delay already measured at a past station.
Targets are the only columns that use later information, by definition.
The generator and the live API (`SimulationRunner.live_features`) call the same function, so there is no
train/serve skew.

## 3. What the 180-day dataset looks like (seed 42)

| | `target_delay_1` | `target_delay_2` | `target_delay_3` |
|---|---|---|---|
| rows | 37,440 | 32,940 | 28,440 |
| mean (min) | 6.75 | 7.29 | 7.97 |
| standard deviation | 17.53 | 18.15 | 18.85 |
| min / max | -16 / 143 | -16 / 143 | -16 / 143 |
| share of rows with delay > 5 min | 30.7% | 33.4% | 36.5% |

Mean `target_delay_1` by group (what the simulation produces; these are not inputs to the generator):

| Group | Mean delay (min) | Share > 5 min |
|---|---|---|
| Day intensity none / low / medium / high | 1.9 / 5.9 / 10.5 / 17.2 | 21% / 30% / 39% / 51% |
| Category premium / express / passenger / freight | 5.9 / 9.7 / 12.2 / -1.6 | 29% / 33% / 44% / 16% |
| Fog active ahead: no / yes | 6.6 / 24.6 | 30% / 78% |
| Signal failure ahead: no / yes | 6.7 / 22.5 | 30% / 67% |
| Trains in the next blocks: 0 / 1 / 2 | 5.6 / 9.3 / 13.9 | 28% / 36% / 46% |

Delays peak around 08-10 h and 15-16 h and are lowest at night. Fog appears on 21, 18, 19 and 14 days in January,
February, November and December but on only 3 days each in October and March; rain slowdowns show the opposite pattern.

Simple baselines on this data (use them as the bar a model must beat):

| Horizon | MAE predicting the mean | MAE predicting `delay_now` | RMSE predicting `delay_now` |
|---|---|---|---|
| next station | 12.35 | **1.25** | 2.71 |
| 2nd station | 12.97 | 3.05 | 6.09 |
| 3rd station | 13.64 | 4.82 | 8.91 |

## 4. What is realistic and what is simplified

Realistic enough for a student project:
- Delays are *caused* by the rules: slowed trains hold up those behind them, single-line sections force waiting,
  closures stop traffic, fast trains get stuck behind slow ones where they cannot overtake.
- Delays depend on time of day (rush hour), season (fog months), train priority, congestion and upstream delay.
- Mixed traffic with different speeds and stopping patterns, early running (negative delays) when a train is faster than its timetable allows for.

Simplifications and limits (do not over-claim):
- **Fictional network and timetable.** The same 25 trains run every day on the same routes; only departure jitter,
  disruptions and dwell noise change. The row count per day is therefore constant (208).
- Trains are points (no length), no acceleration or braking, no platform capacity limits, no rolling-stock or crew effects,
  no level crossings, no breakdowns of the trains themselves.
- Disruptions are drawn independently each day (no multi-day weather, no festival or holiday traffic). Fog affects a
  stretch of the main line with a single speed factor.
- The extra-dwell model and its day-of-week and rush-hour factors are invented. The day-of-week effect in the data is
  weak (mean delay between about 6.0 and 7.7 min across weekdays).
- **Persistence is a very strong baseline.** The next delay is usually close to the current delay (MAE 1.25 min at the next
  station), because arrival delay changes little between neighbouring stations. A useful model must beat
  `delay_now`, not just the mean; the 2nd and 3rd station targets and rows with disruptions are where there is something to learn.
- Because the generator and the live system share the engine and the feature code, a model trained here is tested
  on data from the same simulator. Good scores show the model understands the simulator, not a real railway.
- Delay is measured against a timetable that includes a 5% running-time margin, so unobstructed trains (especially freight)
  arrive a little early.
