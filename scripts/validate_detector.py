"""Validate the conflict detector against the simulator (recall and precision at several look-aheads).

Usage (PowerShell, from the repo root):
    .\\backend\\.venv\\Scripts\\python.exe scripts\\validate_detector.py
    .\\backend\\.venv\\Scripts\\python.exe scripts\\validate_detector.py --seeds 1 2 3 --no-model

Prints markdown tables (paste them into docs/RESULTS.md). Scenarios run in parallel processes.
See backend/app/optimizer/validation.py for the exact definitions of recall and precision.
"""

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.predict import load_predictor  # noqa: E402
from app.models.corridor import build_corridor  # noqa: E402
from app.optimizer.conflicts import ConflictDetector  # noqa: E402
from app.optimizer.validation import Observations, ValidationRow, observe, score  # noqa: E402
from app.simulation.disruptions import Intensity  # noqa: E402
from app.simulation.scenario import Scenario  # noqa: E402

MODEL_PATH = ROOT / "models" / "delay_model.json"


def run_one(job: tuple[int, str, tuple[int, ...], bool]) -> Observations:
    """Observe one scenario (worker process)."""
    seed, intensity, lookaheads, use_model = job
    network = build_corridor()
    predictor = load_predictor(MODEL_PATH) if use_model else None
    detectors = {h: ConflictDetector(network, h) for h in lookaheads}
    return observe(Scenario(seed=seed, intensity=Intensity(intensity)), network, detectors, predictor)


def table(rows: list[ValidationRow]) -> str:
    """Return a markdown table."""
    lines = [
        "| look-ahead (min) | waits >= (min) | real waits | flagged in advance | recall | median lead (min) "
        "| flagged episodes | came true | precision |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lead = "-" if r.median_lead_min is None else f"{r.median_lead_min:.0f}"
        lines.append(
            f"| {r.lookahead_min} | {r.min_wait_min} | {r.events} | {r.events_flagged} | {r.recall:.0%} | {lead} "
            f"| {r.episodes} | {r.episodes_real} | {r.precision:.0%} |"
        )
    return "\n".join(lines)


def main() -> None:
    """Run the scenarios, score them, print the tables."""
    parser = argparse.ArgumentParser(description="Validate the conflict detector against the simulator.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--intensity", nargs="+", choices=[i.value for i in Intensity], default=["low", "medium", "high"])
    parser.add_argument("--lookaheads", type=int, nargs="+", default=[15, 30, 60])
    parser.add_argument("--min-waits", type=int, nargs="+", default=[1, 3])
    parser.add_argument("--no-model", action="store_true", help="use the persistence fallback instead of the ML model")
    args = parser.parse_args()
    use_model = not args.no_model and MODEL_PATH.is_file()

    jobs = [(s, i, tuple(args.lookaheads), use_model) for s in args.seeds for i in args.intensity]
    with ProcessPoolExecutor() as pool:
        observations = list(pool.map(run_one, jobs))
    source = "ML delay model" if use_model else "persistence (no ML model)"
    print(f"Detector validation | predictions: {source} | {len(jobs)} scenarios "
          f"(seeds {args.seeds}, intensities {args.intensity}) | synthetic data\n")
    rows = [score(observations, h, w) for w in args.min_waits for h in args.lookaheads]
    print(table(rows))


if __name__ == "__main__":
    main()
