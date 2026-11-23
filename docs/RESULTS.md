# RailMentes results

> **All results come from synthetic data**: a simulation of a *fictional* corridor. Nothing here is real
> Indian Railways performance. Numbers are from one run of `scripts/train_model.py` (data seed 42, 180 days).

## 1. Delay prediction model

### What it does
For a train on the line, predict how late it will be (minutes) when it arrives at each of its **next three
stations**. The dashboard shows this as `predicted_min` and can explain it ("why late") with SHAP.

### Setup
- **Data:** 37,440 rows, one per train leaving or passing a station ([DATA.md](DATA.md)). 24 inputs: train type,
  clock, current delay, scheduled time and distance to the next stations, trains and single-line blocks ahead,
  active disruptions ahead.
- **Split by day, never at random** (rows from one day share weather and traffic, so a random split would leak):

| Part | Days | Rows | Period |
|---|---|---|---|
| train | 125 | 26,000 | 2025-10-01 to 2026-02-02 |
| validation (early stopping, choosing the loss) | 27 | 5,616 | 2026-02-03 to 2026-03-01 |
| test (touched once, for the numbers below) | 28 | 5,824 | 2026-03-02 to 2026-03-29 |

- **Baselines:** *mean* (always the average training delay), *Ridge* (linear regression with a small penalty),
  *persistence* ("the delay stays what it is now"). Persistence is the one that matters.
- **LightGBM:** one model per horizon. Each learns the **change** in delay (`target - delay_now`), so it starts from
  the persistence answer and only learns a correction. Huber loss, learning rate 0.15, 15 leaves, at least 50 rows per leaf,
  80% of rows and features per tree, L2 penalty 1, early stopping after 50 rounds without gain on the validation days
  (stopped at 1071 / 916 / 1128 rounds). The loss was chosen among squared error, absolute error and Huber by validation
  MAE; nothing was tuned on the test days.

### Test results (minutes; lower is better)

| Model | MAE st. 1 | MAE st. 2 | MAE st. 3 | RMSE st. 1 | RMSE st. 2 | RMSE st. 3 |
|---|---|---|---|---|---|---|
| mean | 12.40 | 13.00 | 13.65 | 18.08 | 18.69 | 19.36 |
| Ridge | 0.79 | 2.67 | 4.46 | 2.13 | 5.36 | 7.63 |
| persistence | 1.25 | 3.12 | 4.97 | 2.67 | 6.18 | 9.04 |
| **LightGBM** | **0.33** | **1.78** | **3.13** | **2.01** | **5.27** | **7.40** |

LightGBM improves on persistence by 0.92 / 1.34 / 1.84 min of MAE (74% / 43% / 37% lower error). Full tables:
[results/delay_metrics.md](results/delay_metrics.md) and [results/delay_metrics.csv](results/delay_metrics.csv).

**"Late or not" (delay above 5 minutes), test days**

| Horizon | Model | Precision | Recall |
|---|---|---|---|
| station 1 | persistence / LightGBM | 0.97 / 0.96 | 0.97 / 0.99 |
| station 2 | persistence / LightGBM | 0.96 / 0.95 | 0.84 / 0.88 |
| station 3 | persistence / LightGBM | 0.96 / 0.93 | 0.71 / 0.81 |

Persistence is already very precise (if it is late now it usually stays late). LightGBM's gain is **recall**: it
catches more of the trains that become late further ahead (81% vs 71% at station 3), at slightly lower precision.

### Where LightGBM helps and where it does not
- **Helps everywhere on MAE**, and more the further ahead we look (the persistence error grows, the model's grows more slowly).
  The gain in minutes is similar for trains that end up on time and trains that end up late (about 0.9 / 1.3 / 1.6-2.2 min at stations 1 / 2 / 3);
  relative to the error it is much bigger for the on-time ones (MAE 0.86 vs 2.50 min at station 3 for trains that end up on time).
- **With a disruption ahead** (156 of 5,824 test rows at station 1): MAE 4.8 vs 6.7 (st. 1), 7.3 vs 10.6 (st. 2), 8.7 vs 13.9 (st. 3),
  so it helps, but errors stay large: a fog or signal failure is hard to time. **RMSE is not much better than a plain Ridge model** there
  (st. 2: LightGBM 11.0, Ridge 10.5; st. 3: 12.4 vs 12.0), i.e. the big misses remain.
- **Trains that really are late (> 5 min):** the gain is smaller than on average (MAE 6.8 vs 9.0 at station 3, RMSE 11.8 vs 14.1) and
  at stations 2 and 3 **Ridge has a slightly lower RMSE than LightGBM** (8.59 vs 8.76; 11.51 vs 11.77).
- **Passenger trains at station 2:** almost no gain over persistence (MAE 2.62 vs 2.80). Freight gains most (1.04 vs 3.97).
- **Ridge is not far behind** (MAE 0.79 / 2.67 / 4.46) and beats LightGBM on RMSE for some groups, so most of the benefit comes from using the
  schedule and train-type features at all, not from the fancy model.
- It does **not** remove large errors: a few trains that suddenly get stuck behind a disruption are still predicted far too early
  (visible as the dots below the diagonal in [results/delay_predicted_vs_actual.png](results/delay_predicted_vs_actual.png)).

### Plots (in `docs/results/`)
`delay_mae_comparison.png` (MAE per model), `delay_error_by_horizon.png` (MAE and RMSE against horizon),
`delay_predicted_vs_actual.png` (persistence vs LightGBM), `delay_feature_importance.png` (mean absolute SHAP effect).
The most used inputs are train type, whether the next station is a halt, hour of day, the slowest speed factor ahead and the number of
trains ahead; current delay matters through the baseline (the model predicts the change from it).

### Honest caveats
1. **Synthetic data.** The simulator is a simplified fictional railway; the numbers say nothing about real railways.
2. **The target is partly determined by the simulator's own rules.** Arrival delay is mostly "scheduled running time vs. what the engine
   makes the train do", and the features include the schedule and distances the engine uses. A model that does well has learned the simulator
   (e.g. freight always runs a little early thanks to the 5% timetable margin), not a real-world law. The same engine produced the training and test days.
3. **Test days are late March**, a different season from most of the training data: only 0.3% of test rows have fog ahead (train 1.2%), fog on 3 of
   28 test days. Disruption results rest on few rows (156 at station 1), so treat them as indicative, not precise.
4. Test days come from the same 25-train timetable and the same random process as the training days, so this is an easier test than a new timetable would be.
5. Delays are whole minutes, early trains count as negative delay (the KPI "average delay" counts them as 0).
6. One data seed and one model seed: no confidence intervals. Differences of a few hundredths of a minute are not meaningful.

### Explaining it in a viva (plain language)
*"For every train we know how late it is now, where it is, what the timetable says, how busy the track ahead is and whether fog or a signal
failure is ahead. We generated 180 simulated days and, for each train at each station, recorded what really happened at the next three stations.
The simplest guess, 'it will be as late as it is now', is already good, so we measure everything against it. Our model (LightGBM, many small
decision trees added one after another) learns when that guess needs correcting: for example a freight train usually gains time, a train
that will have to halt loses time, a train entering a fog stretch will fall behind. We train on the earliest days, use the next block of days to
decide when to stop, and test on the latest days, which the model never saw. We split by day, not randomly, because the trains of one day
affect each other and a random split would let the model peek. On the test days the typical error at the next station falls from
1.25 to 0.33 minutes, and three stations ahead from 5.0 to 3.1 minutes. SHAP then says how many minutes each factor added to a particular train's
predicted delay, which is what the dashboard shows as 'why late'. The limits: the data is simulated, so the model has partly learned our
simulator, and with a disruption ahead it is still off by several minutes."*

### Reproduce
```powershell
.\backend\.venv\Scripts\python.exe scripts\train_model.py
```
Writes `models\delay_model.json` (git-ignored), `docs\results\delay_metrics.md|csv` and the four PNG plots. The same seed gives a byte-identical model file.


---

## 2. Conflict detection and baseline control strategies

All numbers on this page are from the simulator (synthetic data, fictional corridor).

### What was built
- **Detector** (`backend/app/optimizer/conflicts.py`): looks 60 min ahead (configurable). For each train it lists the blocks it will use and when
  (from the predicted arrival at each station: LightGBM, or "the delay stays as it is" without a model). Two trains on the same track at
  overlapping times = a conflict. Kinds: *single_line_meeting* (opposing trains on a single-line stretch), *overtaking* (a faster train arrives
  behind a slower one, nobody can pass between stations) and *block* (anything else on one block, e.g. two lines merging at a junction).
  Severity = predicted wait (min) x highest priority involved: < 6 low, < 15 medium, < 30 high, else critical.
- **Strategies**: `no_control` (does nothing), `fcfs` (the train that reaches the contested track first goes; the other is **held** at its last
  station for the predicted wait), `priority` (the higher-priority train goes first, tie: the more delayed one; the other gets a
  **precedence** "let that train pass this station first", or a hold if the winner does not come through that station).
  Both rules act only when the yielding train is about to leave the station (<= 10 min), act once per conflict, and a precedence is only
  used if the winner reaches the station within 15 min (waiting longer for a far-away train costs more than it saves).
- **Closed loop** (`closed_loop.py`): every tick = snapshot -> detect -> strategy -> apply -> step. The scenario fixes timetable and
  disruptions, so every strategy faces the same day (checked by a test).

### Strategy comparison
Mean over 8 seeds (1-8), no ML model in the loop (persistence), so it can be reproduced in about a minute:
```powershell
.\backend\.venv\Scripts\python.exe scripts\compare_strategies.py --seeds 1 2 3 4 5 6 7 8 --intensity low medium high --no-model
```

| intensity | strategy | avg delay (min) | punctual % | priority-weighted delay | actions | real waits |
|---|---|---|---|---|---|---|
| low | no control | 9.75 | 65.0 | 658 | 0 | 17.1 |
| low | FCFS | 9.60 | 64.5 | 649 | 9.8 | 8.8 |
| low | priority | **8.47** | 67.0 | **532** | 1.6 | 8.9 |
| medium | no control | 13.50 | 59.0 | 882 | 0 | 15.5 |
| medium | FCFS | 13.78 | 59.0 | 906 | 9.4 | 7.5 |
| medium | priority | **12.27** | 61.0 | **766** | 1.5 | 8.5 |
| high | no control | 20.36 | 43.0 | 1294 | 0 | 19.0 |
| high | FCFS | 20.62 | 42.5 | 1323 | 11.1 | 10.3 |
| high | priority | **19.32** | 44.0 | **1191** | 2.0 | 10.5 |

("Real waits" = times a train had to wait at least 3 min for a block held by another train, counted by the simulator itself.
Throughput is 0.92-0.93 trains/hour for every strategy: it is set by the timetable, which has the last trains leaving late in the evening.)

One seed with the ML delay model in the loop (seed 42; `compare_strategies.py --seed 42`), average delay in minutes:

| intensity | no control | FCFS | priority |
|---|---|---|---|
| medium | 10.96 | 12.64 | **10.52** |
| high | 17.44 | 18.60 | **15.40** |

What this says, honestly:
- **Priority beats no control** in all three intensities: -13% / -9% / -5% average delay and -19% / -13% / -8% priority-weighted delay
  (low / medium / high). It does so with very few actions (1.5-2 per day): it lets premium and express trains pass slow ones at stations.
  The gain is modest; the improvement is concentrated on high-priority trains, while some low-priority trains wait longer (that is the point of the rule).
- **FCFS is no better than no control** (-1.5% to +2% over 8 seeds, and +7% to +15% on the single ML run). That is expected: the simulator already serves trains
  in order of arrival at every block, so telling the later train to wait only repeats what happens anyway, plus the cost of prediction errors
  (a hold that is a minute too long is a minute lost). FCFS does reduce the number of trains that wait *on the line* (real waits roughly halve)
  because they now wait at stations instead, but that does not reduce delay. It is a baseline, not a competitor.
- With the ML model, FCFS gets worse than with persistence (12.6 vs 11.0 on seed 42, medium). The model moves the predicted times by a few
  minutes from tick to tick, and FCFS holds for exactly the predicted wait. Priority is not affected the same way.
- 8 seeds, one corridor, one day type: no confidence intervals. Differences of one or two percent are noise.
- The 4th strategy (CP-SAT) is section 3. This section's 8-seed table predates the 20-seed benchmark; use section 3 for the final comparison.

### Detector validation
Ground truth = the simulator's own log: every time a train was refused a block because another train held it (waits caused by closed blocks
excluded; a long wait can have several blockers, all recorded). The scenarios run with no control, so the detector cannot change what it tries
to predict. 15 scenarios (seeds 1-5 x low/medium/high intensity).
- **A flag matches a real wait** when it names the same two trains, the same station-to-station segment, and its predicted time is within
  10 min of when the wait really started. (Matching on the pair alone gave 100% recall at every look-ahead, which only showed that two trains
  running close together stay flagged for hours.)
- **Recall** = real waits flagged between *look-ahead* and 5 min before they started. **Precision** = flagged conflict episodes (the same
  conflict flagged on consecutive ticks) that came true. "waits >= 3 min" leaves out the 1-2 minute waits that are mostly tick-order
  effects of the simulator.

With the ML delay model (as used live):

| look-ahead (min) | waits >= (min) | real waits | flagged in advance | recall | median lead (min) | flagged episodes | came true | precision |
|---|---|---|---|---|---|---|---|---|
| 15 | 1 | 460 | 452 | 98% | 14 | 356 | 320 | 90% |
| 30 | 1 | 460 | 460 | 100% | 24 | 384 | 333 | 87% |
| 60 | 1 | 460 | 460 | 100% | 42 | 360 | 285 | 79% |
| 15 | 3 | 239 | 239 | 100% | 14 | 356 | 250 | 70% |
| 30 | 3 | 239 | 239 | 100% | 27 | 384 | 251 | 65% |
| 60 | 3 | 239 | 239 | 100% | 49 | 360 | 209 | 58% |

With persistence (no model):

| look-ahead (min) | waits >= (min) | real waits | flagged in advance | recall | median lead (min) | flagged episodes | came true | precision |
|---|---|---|---|---|---|---|---|---|
| 15 | 1 | 460 | 453 | 98% | 15 | 174 | 163 | 94% |
| 30 | 1 | 460 | 455 | 99% | 18 | 188 | 164 | 87% |
| 60 | 1 | 460 | 455 | 99% | 18 | 198 | 170 | 86% |
| 15 | 3 | 239 | 239 | 100% | 14 | 174 | 147 | 84% |
| 30 | 3 | 239 | 239 | 100% | 26 | 188 | 150 | 80% |
| 60 | 3 | 239 | 239 | 100% | 37 | 198 | 148 | 75% |

Reading the tables:
- **Recall is very high** (98-100%): almost every real wait had been flagged at least 5 min earlier. Part of this is the definition (10-min
  time tolerance, segment-level match, any of the blockers) and part is that waits cluster where trains bunch up, which is easy to see.
  Recall says nothing about *how early*: the median lead is 14 min at a 15-min look-ahead and 37-49 min at 60 min.
- **Precision is lower and falls with the look-ahead** (ML): 70-90% at 15 min, 58-79% at 60 min. Far ahead, small errors in the
  predicted times decide whether two trains actually overlap, so some flagged conflicts never happen (the trains pass one after the other).
- **The ML model makes the detector noisier, not better**: about twice as many episodes (356 vs 174 at 15 min). Its predicted times change by a
  few minutes from tick to tick, so a borderline conflict is flagged, un-flagged and flagged again, and each flicker counts as a new episode
  (the "episodes" count is inflated, the lower precision partly reflects that). Persistence gives smoother, more stable flags.
  The delay model is more accurate on average (see section 1) but the detector needs *stable* times at the one-minute scale.
- Not measured: conflicts that were flagged and then avoided *because of* a control action (the validation runs with no control).

Detector improvements (one round, as planned; both are small):
1. Departures from a halt now respect the timetable (a train does not leave before its scheduled departure). Effect on the numbers: within +-1 point.
2. The ground truth only recorded the *first* train that blocked a waiting train; a long wait often has several blockers. Recording all of them
   corrected the measurement (it is a fix to the measurement, not to the detector): precision persistence 15 min / >= 3 min went from 77% to 84%,
   60 min from 67% to 75%.

First version, for the record (before both changes; ground truth = first blocker only), persistence: recall 98-100%, precision 67-86%; ML: recall 98-100%, precision 55-86%.

### Limits and viva notes
- The detector is deliberately simple: block-level overlap of predicted time intervals. It has no platform conflicts (the simulator has no platform
  limit), ignores disruptions except through the predicted times, and treats trains as points.
- The strategies only use HOLD and PRECEDENCE at stations, as the shared contract defines; they cannot reroute.
- In the live dashboard the strategy only *recommends* (the controller applies or ignores each one); the headless comparison applies
  every action automatically. So a live run with a strategy selected is not expected to match the KPI table unless every recommendation is applied.
- Simple explanation: *"A conflict is two trains that, by our predicted times, want the same piece of track at the same time. FCFS says the one
  who gets there first goes; priority says the more important train goes. Both just make the other train wait at the station before."*

### Reproduce
```powershell
.\backend\.venv\Scripts\python.exe scripts\compare_strategies.py --seed 42                    # one seed, with the ML model
.\backend\.venv\Scripts\python.exe scripts\validate_detector.py                               # detector tables above (with ML)
.\backend\.venv\Scripts\python.exe scripts\validate_detector.py --no-model                    # persistence
```


---

## 3. The CP-SAT optimizer (strategy `cpsat`) and the 4-strategy benchmark

All numbers are from the simulator (synthetic data, fictional corridor). Files: `docs/results/benchmark_*` (per-run CSV, summary CSV and
markdown, one chart per metric) and `benchmark_persistence_*` (same, without the ML model).

### What it does (viva version)
Every tick the conflict detector says which trains will fight for the same track in the next 60 minutes. The optimizer takes **only those
trains** (plus trains that share a track with them), writes down for each train *how many minutes it is held at each station* and, for each
pair, *who goes first*, and asks Google CP-SAT for the combination with the **smallest priority-weighted predicted delay**
(premium counts 4x, freight 1x). Rules it must obey: one train per block, no head-on trains on a single line, 1 minute headway, no passing
between stations, at most 20 minutes per hold, nothing for a train that already left the station. Letting a train go second is only possible
by holding the one that would have been first. Each hold costs a little (25 weighted minutes per action, 0.1 per hold minute), so it never
acts for a tiny gain. Models are tiny (typically 2-4 trains, 20-40 track visits): the median solve takes 9-18 ms, the worst 0.23 s,
and every solve in the benchmark finished OPTIMAL.

Output: a `PRECEDENCE` ("let that train pass this station first") when the winner comes through the same station soon (it adapts to the real
times), otherwise a `HOLD` of the solved length. The reason names the train, minutes, station, the train that gets through and the saving.
If the solver finds nothing it falls back to the priority rule and says so in the reason (0 fallbacks in the final benchmark; an earlier run
showed 10, caused by a circular "who is first" order when three trains entered at the same minute; fixed by an exit-time tie-break and
covered by a regression test).

Determinism: one worker, fixed seed, effort limit in CP-SAT *deterministic time*, so the same day always gives the same actions (tested).
It sees exactly what the priority rule sees: the predicted snapshot and the detected conflicts (a test checks it).

### Tuning (and which seeds)
The two penalty values were chosen on **seeds 101-110 only** (persistence predictions, low / medium / high; no overlap with the benchmark seeds 1-20).
Mean priority-weighted delay over the three intensities (lower is better; the priority rule gets 814 on the same seeds):

| action penalty | hold penalty | weighted delay (mean of 3 intensities) | actions/day (low / medium / high) |
|---|---|---|---|
| 4 | 0.1 | 826 | 2.7 / 2.4 / 3.5 |
| 4 | 0.5 | 835 | 2.8 / 2.2 / 3.1 |
| 10 | 0.1 | 835 | 2.8 / 2.2 / 3.2 |
| 10 | 0.5 | 826 | 2.5 / 2.0 / 2.6 |
| **25** | **0.1** | **823** | **2.2 / 2.0 / 2.6** |
| 25 | 0.5 | 835 | 1.8 / 2.0 / 2.4 |

The differences are inside the noise (a standard error of about 60): the penalties barely matter. **Chosen: action penalty 25, hold penalty 0.1**
(best number and fewest actions). It was not re-tuned for the ML predictions; the headline run uses the same values. (The tuning grid was run
before two later changes that do not alter the model's answers except in rare ties: a faster solver setting and the tie-break above.)
Other defaults, not tuned: look-ahead 60 min, headway 1 min, max hold 20 min, decision horizon 10 min (act only when the train leaves within 10 min).

### Benchmark: 20 seeds (1-20) x 3 intensities x 4 strategies, ML delay model in the loop (headline)
Mean ± standard deviation over the 20 days (the spread is mostly "some days are harder than others", not noise in the comparison):

| intensity | strategy | avg delay (min) | punctuality % | trains/hour | priority-weighted delay | actions/day |
|---|---|---|---|---|---|---|
| low | No control | 9.47 ± 2.79 | 66.0 ± 5.9 | 0.93 | 631 ± 198 | 0 |
| low | FCFS | 9.31 ± 2.47 | 65.8 ± 6.0 | 0.93 | 620 ± 190 | 9.7 |
| low | Priority rule | 8.40 ± 2.63 | 66.2 ± 5.9 | 0.93 | 522 ± 182 | 1.6 |
| low | **CP-SAT** | **7.99 ± 2.56** | 67.4 ± 6.5 | 0.93 | **497 ± 180** | 2.3 |
| medium | No control | 13.87 ± 3.70 | 58.0 ± 7.5 | 0.93 | 917 ± 260 | 0 |
| medium | FCFS | 14.29 ± 4.12 | 58.0 ± 7.5 | 0.93 | 954 ± 303 | 9.3 |
| medium | Priority rule | 13.31 ± 3.83 | 59.2 ± 7.1 | 0.93 | 836 ± 272 | 2.0 |
| medium | **CP-SAT** | **12.63 ± 3.60** | 59.4 ± 7.4 | 0.93 | **798 ± 256** | 2.2 |
| high | No control | 20.75 ± 5.07 | 43.0 ± 6.5 | 0.93 | 1330 ± 337 | 0 |
| high | FCFS | 21.04 ± 5.41 | 43.0 ± 7.4 | 0.93 | 1349 ± 365 | 10.9 |
| high | Priority rule | 20.02 ± 4.88 | 43.6 ± 7.3 | 0.93 | 1226 ± 308 | 2.9 |
| high | **CP-SAT** | **19.54 ± 5.26** | 43.0 ± 7.6 | 0.93 | 1217 ± 344 | 2.7 |

CP-SAT minus priority on the same seeds (paired; 95% bootstrap interval of the mean difference; seeds where CP-SAT was better / worse):

| intensity | avg delay (min) | priority-weighted delay | punctuality (points) | actions/day |
|---|---|---|---|---|
| low | **-0.41** [-0.63, -0.20], 13 / 1 | **-25** [-40, -12], 12 / 1 | +1.2 [+0.2, +2.4] | +0.75 |
| medium | **-0.68** [-1.04, -0.37], 13 / 1 | **-37** [-57, -20], 12 / 2 | +0.2 [-1.0, +1.4] (no difference) | +0.2 |
| high | **-0.48** [-0.95, -0.04], 11 / 5 | -9 [-38, +20], 10 / 6 (**no difference**) | -0.6 [-1.8, +0.4] (no difference) | -0.15 |

Versus no control, CP-SAT lowers average delay by 16% / 9% / 6% (low / medium / high) and priority-weighted delay by 21% / 13% / 9%;
the priority rule gets 11% / 4% / 4% and 17% / 9% / 8%. Throughput is 0.93 trains/hour for every strategy (it is fixed by the timetable).

### Same benchmark with persistence ("the delay stays as it is"), no ML model (secondary table)

| intensity | strategy | avg delay (min) | punctuality % | priority-weighted delay | actions/day |
|---|---|---|---|---|---|
| low | Priority rule | 8.22 ± 2.61 | 66.8 ± 6.9 | 511 ± 186 | 1.5 |
| low | CP-SAT | 8.14 ± 2.36 | 66.4 ± 7.0 | 513 ± 168 | 2.5 |
| medium | Priority rule | 13.01 ± 3.92 | 59.6 ± 7.3 | 818 ± 273 | 1.8 |
| medium | CP-SAT | 12.93 ± 3.74 | 58.2 ± 8.3 | 825 ± 266 | 2.6 |
| high | Priority rule | 19.54 ± 4.75 | 44.0 ± 6.9 | 1200 ± 297 | 2.5 |
| high | CP-SAT | 19.27 ± 5.15 | 43.8 ± 7.6 | 1195 ± 332 | 2.6 |

(The No control and FCFS rows are in `benchmark_persistence_summary.md`.)
Paired CP-SAT minus priority: average delay -0.08 / -0.09 / -0.28 min, **all three intervals include 0**; weighted delay +3 / +7 / -5, all include 0;
punctuality at medium intensity is 1.4 points *worse* (interval [-2.6, -0.6]); CP-SAT uses about one action more per day at low and medium.

### Verdict (plain)
- **Where CP-SAT wins:** with the ML delay model in the loop, at low and medium intensity it beats the priority rule on average delay (-0.4 and -0.7 min)
  and on priority-weighted delay (-25 and -37) in 12-13 of 20 seeds, and the intervals exclude zero. At high intensity it wins on average
  delay (-0.5 min) but **not** reliably on weighted delay or punctuality. It beats no control and FCFS on delay everywhere.
- **Where it does not:** (1) **without the ML model it is no better than the priority rule** (and 1.4 points worse on punctuality at medium intensity): the
  gain depends on accurate predicted times, whereas the priority rule only compares ranks. (2) Punctuality (share <= 5 min late) hardly moves for any
  strategy. (3) Throughput does not move at all. (4) The gains are small in absolute terms: 0.4-0.7 minutes of average delay, 2-5% on top of the priority rule,
  against a day-to-day spread of 3-5 minutes. It is a real but modest improvement, not a transformation.
- **Why only modest:** the simulator already serves trains in order of arrival, so only deliberate re-ordering (a faster or more important train goes
  first) can help, and the priority rule already does the biggest part of that with 1.5-3 actions a day. CP-SAT adds weighing of who loses how much and of
  knock-on effects, and cannot add much more because the only tools are holds and precedences, and the plan rests on predicted minutes.
- **The "saves X weighted delay-minutes" in each reason is the optimizer's own prediction, not a measurement.** Over 24 medium and high days
  (persistence) the actions claimed 48 plain delay-minutes per day in total, against 35 minutes per day actually gained vs no control: about 1.4x overstated.
- Limits: one corridor, 25 trains a day, 20 seeds; "no difference" means "not detectable with 20 seeds". The detector only sees 60 minutes ahead and its flags
  flicker with the ML model (section 2). The optimizer is stateless: it re-plans every tick and does not know its own earlier holds (the closed loop acts once per
  conflict and once per train and station). A hold on a train whose real departure is already later than predicted has no effect (hidden delays are
  not in the snapshot, and the optimizer is not allowed to know more than the other strategies).

### Reproduce
```powershell
.\backend\.venv\Scripts\python.exe scripts\run_benchmark.py                 # headline: ML model, 20 seeds, about 10 min on 16 cores
.\backend\.venv\Scripts\python.exe scripts\run_benchmark.py --no-model       # persistence, about 4 min
.\backend\.venv\Scripts\python.exe scripts\run_benchmark.py --seeds 101-110 --intensity medium --no-model --out $env:TEMP\tune   # quick / tuning-style run
```
