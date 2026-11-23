"""Run one simulated day headless and print a short summary.

Usage (PowerShell, from the repo root):
    .\\backend\\.venv\\Scripts\\python.exe scripts\\run_sim.py --seed 42 --intensity medium
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.models.corridor import build_corridor  # noqa: E402
from app.models.schemas import TrainStatus  # noqa: E402
from app.simulation.disruptions import Intensity  # noqa: E402
from app.simulation.scenario import Scenario  # noqa: E402


def main() -> None:
    """Parse args, run the day, print the summary."""
    parser = argparse.ArgumentParser(description="Run one RailMentes sim-day headless.")
    parser.add_argument("--seed", type=int, default=42, help="random seed (same seed = same run)")
    parser.add_argument(
        "--intensity", choices=[i.value for i in Intensity], default="none", help="amount of random disruptions"
    )
    parser.add_argument("--month", type=int, default=1, help="month 1-12 (fog is likely in Nov-Feb)")
    args = parser.parse_args()

    scenario = Scenario(seed=args.seed, intensity=Intensity(args.intensity), month=args.month)
    engine = scenario.build(build_corridor())
    end_tick = engine.run_until_done()
    trains = engine.snapshot().trains
    delays = [max(t.delay_min, 0.0) for t in trains]  # early trains count as 0, like the KPI
    worst = max(trains, key=lambda t: t.delay_min)
    completed = sum(t.status is TrainStatus.FINISHED for t in trains)

    print(f"Seed {args.seed} | intensity {args.intensity} | month {args.month} | synthetic data, fictional network")
    print(f"Trains completed : {completed}/{len(trains)} (day ended at tick {end_tick})")
    print(f"Disruptions      : {len(engine.disruptions)}")
    print(f"Average delay    : {sum(delays) / len(delays):.1f} min")
    print(f"Max delay        : {worst.delay_min:.1f} min ({worst.name}, {worst.category.value})")
    for category in ("premium", "express", "passenger", "freight"):
        group = [max(t.delay_min, 0.0) for t in trains if t.category.value == category]
        print(f"  {category:<10} avg delay {sum(group) / len(group):6.1f} min  ({len(group)} trains)")


if __name__ == "__main__":
    main()
