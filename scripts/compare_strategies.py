"""Run one seeded scenario under every implemented strategy and print a KPI comparison table.

Usage (PowerShell, from the repo root):
    .\\backend\\.venv\\Scripts\\python.exe scripts\\compare_strategies.py --seed 42
    .\\backend\\.venv\\Scripts\\python.exe scripts\\compare_strategies.py --seed 7 --intensity high --no-model

Every strategy faces exactly the same timetable and disruptions (same seed and intensity).
With several seeds the table shows the mean over those seeds.
With the trained delay model (models/delay_model.json) a run takes ~10-20 s; --no-model uses the
"delay stays as it is" fallback and takes ~2 s.
"""

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.predict import load_predictor  # noqa: E402
from app.models.corridor import build_corridor  # noqa: E402
from app.models.schemas import StrategyName  # noqa: E402
from app.optimizer.closed_loop import run_closed_loop  # noqa: E402
from app.optimizer.kpi import RunKpis  # noqa: E402
from app.optimizer.registry import IMPLEMENTED_STRATEGIES, make_strategy  # noqa: E402
from app.simulation.disruptions import Intensity  # noqa: E402
from app.simulation.scenario import Scenario  # noqa: E402

MODEL_PATH = ROOT / "models" / "delay_model.json"
COLUMNS = (
    ("avg delay (min)", "avg_delay_min", "{:.2f}"),
    ("punctual %", "punctuality_pct", "{:.1f}"),
    ("trains/hour", "throughput_per_hour", "{:.2f}"),
    ("prio-weighted delay", "priority_weighted_delay", "{:.0f}"),
    ("conflicts seen", "conflicts_detected", "{:g}"),
    ("actions", "actions_applied", "{:g}"),
    ("real waits", "blocking_events", "{:g}"),
)


def run_one(job: tuple[int, str, str, bool]) -> RunKpis:
    """Run one (seed, intensity, strategy) in a worker process."""
    seed, intensity, strategy, use_model = job
    network = build_corridor()
    predictor = load_predictor(MODEL_PATH) if use_model else None
    scenario = Scenario(seed=seed, intensity=Intensity(intensity))
    return run_closed_loop(scenario, make_strategy(StrategyName(strategy), network), network, predictor).kpis


def format_table(intensity: str, results: dict[str, list[RunKpis]]) -> str:
    """Return a plain-text table, one row per strategy (the mean when there are several seeds)."""
    header = ["strategy", *(title for title, _, _ in COLUMNS)]
    rows = [
        [name, *(fmt.format(round(sum(getattr(k, field) for k in runs) / len(runs), 2)) for _, field, fmt in COLUMNS)]
        for name, runs in results.items()
    ]
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(r, widths, strict=True)) for r in [header, *rows]]
    return f"Intensity: {intensity}\n" + "\n".join(lines)


def main() -> None:
    """Parse args, run all strategies for each intensity, print the tables."""
    parser = argparse.ArgumentParser(description="Compare control strategies on seeded scenarios.")
    parser.add_argument("--seed", type=int, default=42, help="one seed (default 42)")
    parser.add_argument("--seeds", type=int, nargs="+", help="several seeds: the table shows the mean")
    parser.add_argument("--intensity", nargs="+", choices=[i.value for i in Intensity], default=["medium", "high"])
    parser.add_argument("--no-model", action="store_true", help="skip the ML delay model (faster)")
    args = parser.parse_args()
    seeds = args.seeds or [args.seed]
    use_model = not args.no_model and MODEL_PATH.is_file()
    if not args.no_model and not use_model:
        print(f"(no delay model at {MODEL_PATH}; using the persistence fallback)")

    strategies = [s.value for s in IMPLEMENTED_STRATEGIES]
    jobs = [(seed, i, s, use_model) for i in args.intensity for s in strategies for seed in seeds]
    with ProcessPoolExecutor() as pool:
        done = list(pool.map(run_one, jobs))
    source = "ML delay model" if use_model else "persistence (no ML model)"
    label = f"seed {seeds[0]}" if len(seeds) == 1 else f"mean of {len(seeds)} seeds ({seeds[0]}..{seeds[-1]})"
    print(f"RailMentes strategy comparison | {label} | predictions: {source} | synthetic data\n")
    per_intensity = len(strategies) * len(seeds)
    for k, intensity in enumerate(args.intensity):
        chunk = done[k * per_intensity : (k + 1) * per_intensity]
        block = {s: chunk[j * len(seeds) : (j + 1) * len(seeds)] for j, s in enumerate(strategies)}
        print(format_table(intensity, block), end="\n\n")


if __name__ == "__main__":
    main()
