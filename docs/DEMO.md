# RailMentes: 5-minute demo script

> Everything on screen is **synthetic**: a fictional corridor, simulated trains, simulated disruptions. Say this
> in the first 20 seconds and keep saying "in the simulation".

## Before you start (10 minutes earlier)

1. Laptop on charger, power mode "Best performance", notifications off, browser zoom 100%, window maximised
   (1366x768 or larger; the alerts panel starts collapsed below 1600 px width, the demo opens it for you).
2. Start everything: double-click `start_all.bat` (two windows open: backend and frontend). Wait until the
   backend window shows `Application startup complete`.
3. Open <http://localhost:5173>. The top-right badge must say **Live** (green). If it says "Offline demo data" see the
   fallback plan at the bottom.
4. **Warm up the numbers once:** press **Guided demo**, then after the intro caption press **Space** to pause. The
   backend now computes the four full-day strategy KPIs for this scenario in background processes (one to two
   minutes with the ML model). Without this, the Compare tab at minute 4 may still say "computing".
5. Press the **Reset** button (circular arrow) so the demo starts from a clean day. Keep a second browser tab on
   `docs/results/` charts or `docs/RESULTS.md` as a backup.

## The script

| Min | Do (exact clicks) | Say |
|---|---|---|
| 0:00 | Show the **Map** tab, nothing running. Point at the "Synthetic data" chip in the top bar. | "RailMentes is a train traffic control dashboard for a *fictional* corridor. All data is synthetic, and everything I show is validated in simulation only. The AI layer predicts delays, spots conflicts early, and recommends decisions the controller can apply." |
| 0:30 | Click **Guided demo** (top right, next to Replay same day). The scenario resets and starts by itself: seed 222, January, medium disruptions, CP-SAT. | "The guided demo loads a fixed foggy January day so we all see the same thing. I will be upfront: this day was picked from 32 candidates because it shows the mechanism clearly. It is an illustration, not a typical day. I will show the honest averages at the end." |
| 1:00 | Watch the map. When caption **"1. Fog sets in"** appears, point at the drifting fog and the amber/red markers. | "Fog slows trains in that stretch. Delay builds and slow trains hold up faster ones behind them. These coloured markers are trains; the colour is how late they are, the shape is the type of train." |
| 1:30 | When **"2. A conflict is predicted"** appears, point at the pulsing red ring on the map and the red card in the alerts panel on the left. Click one train chip on the card (for example the first id). | "Two trains would meet on a single track. This alert appeared *before* it happens: the delay model predicts each train's arrival times and the detector looks 60 minutes ahead for overlaps." |
| 2:00 | The train drawer opens on the right. Scroll to **Why late?** and click the horizon tabs (next station, 2nd, 3rd). | "This is the LightGBM prediction explained with SHAP. Each bar is minutes added or removed by one factor, for example fog ahead or trains in the next blocks. On our test days the model's error at the next station is 0.33 minutes versus 1.25 for 'it stays as late as now'." |
| 2:30 | The demo pauses on **"3. The optimizer recommends a decision"**. Read the recommendation card in the alerts panel aloud (action, reason, "saves ~X min"). Click **Apply**, then press **Space** (or **Start**) to resume. | "CP-SAT picked this hold or precedence by minimising priority-weighted predicted delay under safety rules: one train per block, no head-on trains. It only *recommends*; a human applies it. The 'saves' figure is the optimizer's own estimate, and we measured that it overstates the real gain by about 1.4 times." |
| 3:00 | Click the **Time-distance** tab (or press **2**). Point at the "now" line, the dashed predicted lines, the shaded fog and conflict areas. Hover one line. | "Same day as a time-distance graph, the classic controller's view: distance on the vertical axis, time across. Thin is the plan, bold is what happened, dashed is predicted. Crossing lines on a single track are the conflicts." |
| 3:30 | Press **Space** to run on (speed 10x) until the caption **"5. The day is over"** appears (about 1 minute of real time; talk through the previous points meanwhile, or press the speed slider to 20x). Click the **Compare** tab (or press **3**). | "Now the comparison. The top panel is this same day under all four strategies with every recommendation applied." |
| 4:00 | On Compare, point at the caveat panel, then the live KPI cards. | "On this day CP-SAT gets 12.5 minutes average delay against 16.5 with no control, and the priority rule does not help (16.6). That is the best-looking of the 32 days I scanned, which is why I call it an illustration." |
| 4:30 | Scroll to the benchmark charts and table. Point at "Low / Medium / High, 20 seeds" and the CP-SAT row. Optionally click the toggle to the persistence (no ML model) result. | "This is the honest result: 20 random days per disruption level. CP-SAT beats the priority rule by 0.4 to 0.7 minutes, about 2 to 5 percent, and at high disruption the improvement is not reliable. Without the ML delay model it is no better than the simple priority rule. Punctuality and throughput barely move. So: a real but modest gain." |
| 5:00 | Stop. Optionally press **Ctrl+K** to show the command palette and "Replay same day with a strategy". | "Everything is reproducible: same seed, same day, any strategy. Questions?" |

**Pacing (measured):** after you click Guided demo the fog caption appears within seconds, the conflict after about
15 to 20 seconds and the recommendation after about 50 seconds, where the demo **pauses by itself**. So the
simulation waits for you at the recommendation: talk quickly through the fog and the conflict, press **Space** to pause
earlier if you want more time, and do the train-drawer step (2:00) while it is paused on the recommendation. The
minute marks in the table are a speaking plan, not the simulation clock.

If you are short of time, skip the drawer (2:00) and the time-distance tab (3:00).

## About the guided-demo seed (be honest about it)

The demo runs **seed 222, January, medium intensity, CP-SAT**. It was found by running seeds 201 to 232 under no
control, the priority rule and CP-SAT, keeping the days that have fog, a single-line meeting and a recommendation,
and ranking them by the CP-SAT gain over no control. Seed 222 was the best-looking of the 32 (the top three gains
were 24 to 33 percent); the full day gives 16.5 minutes average delay with no control, 16.6 with the priority
rule and 12.5 with CP-SAT (-24 percent). It was **chosen because it looks good**. The 20-seed benchmark, which
never used these seeds, says the typical gain over the priority rule is 2 to 5 percent. The captions and the
Compare tab say so, and you should say it out loud.

## If something goes wrong

| Problem | What to do |
|---|---|
| The recommendation does not appear or disappears before you click | Predictions flicker. The demo resumes by itself and waits for the next one; or press **Reset**, press **Guided demo** again. |
| Apply does nothing / button disabled | The badge is not **Live**. Check the backend window; see below. |
| Compare says "computing" | The background KPI runs take one to two minutes with the model. Talk through the benchmark table (it is a saved file and loads instantly) and come back. |
| Page looks frozen | Press **F5**. The backend keeps the scenario; the actual-path history on the time-distance graph restarts (recorded in the browser), the plan is rebuilt. |
| You lost your place | Press **Ctrl+K** and type "reset" or "demo". |

## Fallback plan 1: the backend fails

Symptom: badge shows **Offline demo data** (the page shows one bundled sample frame, controls are disabled).

1. Do not panic: say "the dashboard degrades gracefully; with no backend it shows bundled sample data".
2. Try to fix it in under a minute: close the "RailMentes backend" window and run `.\scripts\run_backend.ps1`
   in PowerShell. The page reconnects by itself within 15 seconds and switches to live data (no reload needed).
3. If the backend will not start (for example a broken Python environment), continue offline:
   - Walk through the static map and alerts panel (two sample alerts with CP-SAT recommendations and a sample train
     drawer with a "why late" explanation are in the bundled frame). Start, Apply, Guided demo and Replay are disabled
     offline. The Compare tab shows the caveat panel, but its live comparison and the 20-seed benchmark need the
     backend and show "Cannot reach the backend", so use the saved files below for the numbers.
   - Show the screenshots in `docs/screenshots/` (the `slice2-1920x1080-*` files follow the demo order: fog,
     conflict, recommendation, time-distance, apply, compare, replay).
   - Show the benchmark results from files: `docs/RESULTS.md` section 3 and the charts in `docs/results/`.
   - Say clearly that you are showing saved results.

## Fallback plan 2: no internet

Nothing in the demo needs the internet. Fonts and all packages are installed locally, the backend and frontend
both run on `localhost`, and the data is generated on the laptop. The only things that need a network are the
first-time installs (`pip`, `npm`) and viewing the Mermaid diagrams in `docs/ARCHITECTURE.md` on GitHub: before
the viva, open that file in VS Code's Markdown preview or export the diagrams to images, and keep a copy offline.
If the venue Wi-Fi is the problem, turn Wi-Fi off and run the demo exactly as above.

## Keyboard cheat sheet

`Space` start or pause · `1` `2` `3` tabs · `[` alerts panel · `]` train panel · `Esc` close train · `Ctrl+K` command
palette · `?` help · map: wheel zoom, drag pan, `0` or `F` fit, `+` `-` zoom.
