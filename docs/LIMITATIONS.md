# Limitations and honest caveats

RailMentes is a student demonstration of decision support for train control. It is not a signalling system and
none of its numbers describe a real railway. This page lists what is simplified or weaker than it may look.
Numbers come from [RESULTS.md](RESULTS.md).

## The data and the claim

- **All data is synthetic.** The corridor (15 stations, 45 blocks), the timetable and every disruption are invented. Station
  names are Indian-style only. No real Indian Railways data was used, and no result is real-world performance.
- **Validated in simulation only.** Nothing was tested on a real railway, a real signalling system or with real controllers.
  There was no user study.
- **The model has partly learned the simulator.** The training data comes from the same engine that runs the demo,
  and the target is mostly "scheduled time versus what the engine makes the train do". A good score shows the model
  understands our simulator, not that it would work on a real network.
- **Test days are easy and one-sided.** The test period is 2026-03-02 to 03-29, nearly fog-free (0.3 percent of test rows have fog ahead; fog on 3 of 28
  days). Disruption results rest on few rows (156 at the next station) and are indicative only. Test and training days
  share the same 25-train timetable.
- **No confidence intervals on the model metrics**: one data seed and one model seed. Differences of a few hundredths of
  a minute mean nothing.
- **Persistence is a strong baseline.** Part of the "prediction" is just the current delay; the model's real value
  is the correction (0.33 vs 1.25 minutes at the next station, 3.13 vs 4.97 at the third). Ridge regression is
  not far behind and has a slightly lower RMSE for trains that are really late and with a disruption ahead.

## The simulation

- **Trains are points.** No length, so no train can block two blocks at once or clear a junction late.
- **No platform limits.** Any number of trains can stand at a station, so platform conflicts do not exist and the detector does not produce them.
- **No acceleration or braking**, no rolling stock, crew, level crossing or train-failure effects.
- **Fixed timetable.** The same 25 trains (4 premium, 7 express, 8 passenger, 6 freight) run every day; only departure jitter, disruptions and dwell
  noise change. No holidays, no multi-day weather.
- **Rule-based movement.** Blocks are first-come-first-served in the engine; a single-line section can only hold one direction at a time;
  no overtaking between stations (only at stations); a closed block stops entry only, a train already inside crawls out at 30 percent speed.
- **Whole-minute resolution** (one tick = one minute).
- **The extra dwell-time factors (rush hour, day of week) are invented** for plausibility; the day-of-week effect in the data is weak.
- **Early running** is possible (the timetable has a 5 percent margin); "average delay" counts early trains as 0.

## The detector and the optimizer

- **The detector is deliberately simple**: overlap of predicted time intervals per block, 60 minutes ahead. It ignores disruptions except through the
  predicted times. Precision drops with the look-ahead (70 to 90 percent at 15 minutes, 58 to 79 percent at 60 minutes) and the flags flicker more with the ML model than with persistence.
- **Only two actions exist**: hold at a station and "let that train pass first". No rerouting, no platform changes, no speed advice.
- **The optimizer's estimated savings are overstated by about 1.4x.** The "saves X min" on a recommendation is the solver's own prediction; over
  24 medium and high days it claimed 48 delay-minutes per day and 35 were actually gained.
- **The gain over the priority rule is modest and conditional.** 0.4 to 0.7 minutes (2 to 5 percent) of average delay, against a day-to-day spread of 3 to 5
  minutes. Clear at low and medium intensity; not reliable at high intensity for weighted delay and punctuality. **Without the ML delay model CP-SAT is no better
  than the priority rule.** Punctuality and throughput hardly move for any strategy; FCFS is no better than doing nothing.
- **Stateless optimizer.** It re-plans every tick and does not remember its own holds; the loop's guards (once per conflict, once per train and station) prevent
  stacking. A hold on a train whose real departure is already later than predicted has no effect.
- **Tuning**: two penalty values were tuned on seeds 101 to 110 (differences inside the noise); the benchmark seeds 1 to 20 were never used for tuning. "No difference"
  means "not detectable with 20 seeds", not "proven equal".
- **One corridor, 25 trains a day, three disruption levels.** Results may not carry over to other networks or traffic.

## The live system and the dashboard

- **Recommend-only live.** A live run with a strategy selected is not expected to match the KPI table unless the controller applies every recommendation
  (the table applies all of them).
- **Apply cannot be undone** by the backend; only Ignore can be undone.
- **The guided demo is a hand-picked day.** Seed 222 was the best-looking of 32 scanned seeds (24 percent lower average delay than no control); the typical gain is much smaller.
- **Time-distance history is kept in the browser.** The backend sends only the present moment, so reloading the page loses the recorded part of the path
  (the planned timetable is rebuilt).
- **Offline mode shows one static sample frame**, not a moving simulation.
- **One scenario at a time**, one user. No login, no database of runs, no authentication: it is meant to run on localhost.
- **Layout limits**: at 1366 px width with both side panels open the map is small (collapse a panel with `[` or `]`); below 1280 px the header wraps.
- **Reorders in the alerts panel snap into place** rather than glide (a deliberate trade-off to keep cards from overlapping while they animate).
- **Machine dependence**: the 20-seed benchmark takes about 10 minutes on a 16-core machine; the first Compare numbers take one to two minutes after a reset.

## What it is not

Not an interlocking, not a signalling or safety system, not a forecast of any real service, and not evidence that AI improves real railway operations. It shows a method
(predict, detect, optimise, measure honestly) on a simulated corridor.
