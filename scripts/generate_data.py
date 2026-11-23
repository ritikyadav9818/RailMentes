"""Generate synthetic railway run data by simulating many days headless.

Usage (PowerShell, from the repo root):
    .\\backend\\.venv\\Scripts\\python.exe scripts\\generate_data.py
    .\\backend\\.venv\\Scripts\\python.exe scripts\\generate_data.py --days 365 --seed 7 --out data\\runs.csv --sqlite

All data is synthetic (simulation of a fictional network), not real Indian Railways data.
"""

import argparse
import os
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ml.datagen import (  # noqa: E402
    DEFAULT_START,
    Row,
    generate_dataset,
    plan_days,
    sample_rows,
    write_csv,
    write_sqlite,
)
from app.ml.features import ALL_COLUMNS, STATIONS_AHEAD  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PROGRESS_EVERY_DAYS = 20


def print_stats(rows: list[Row]) -> None:
    """Print a short description of the targets."""
    print("Targets (delay in minutes at the next stations):")
    for k in range(1, STATIONS_AHEAD + 1):
        values = [float(r[f"target_delay_{k}"]) for r in rows if r[f"target_delay_{k}"] is not None]
        late = sum(v > 5 for v in values) / len(values)
        print(
            f"  target_delay_{k}: n={len(values):6d}  mean={statistics.fmean(values):6.2f}  "
            f"std={statistics.pstdev(values):6.2f}  min={min(values):6.1f}  max={max(values):6.1f}  "
            f"share > 5 min = {late:6.1%}"
        )


def main() -> None:
    """Parse arguments, generate, save and report."""
    parser = argparse.ArgumentParser(description="Generate synthetic RailMentes run data.")
    parser.add_argument("--days", type=int, default=180, help="number of simulated days (default 180)")
    parser.add_argument("--seed", type=int, default=42, help="master seed (same seed = identical dataset)")
    parser.add_argument(
        "--start-date", type=date.fromisoformat, default=DEFAULT_START, help="first day, YYYY-MM-DD"
    )
    parser.add_argument(
        "--out", type=Path, default=REPO / "data" / "railmentes_runs.csv", help="output CSV path"
    )
    parser.add_argument("--sqlite", action="store_true", help="also write a SQLite file next to the CSV")
    parser.add_argument(
        "--sample-rows", type=int, default=500, help="rows of the small committed sample (0 = none)"
    )
    parser.add_argument(
        "--no-realism", action="store_true", help="exact timetable halts (no random extra dwell)"
    )
    parser.add_argument("--workers", type=int, default=1, help="parallel processes (1 = one process)")
    args = parser.parse_args()

    specs = plan_days(args.days, args.seed, args.start_date)
    print(
        f"Generating {args.days} days from {specs[0].day} to {specs[-1].day} (seed {args.seed}); synthetic data."
    )
    started = time.perf_counter()
    collected: list[Row] = []
    done = 0

    def on_day(rows: list[Row]) -> None:
        nonlocal done
        done += 1
        collected.extend(rows)
        if done % PROGRESS_EVERY_DAYS == 0 or done == args.days:
            elapsed = time.perf_counter() - started
            eta = elapsed / done * (args.days - done)
            print(
                f"  day {done:4d}/{args.days}  rows so far {len(collected):7d}  elapsed {elapsed:5.1f}s  eta {eta:5.1f}s"
            )

    days = generate_dataset(specs, realism=not args.no_realism, workers=max(1, args.workers))
    count = write_csv(days, args.out, on_day)
    if args.sqlite:
        sqlite_path = args.out.with_suffix(".sqlite")
        write_sqlite(collected, sqlite_path)
        print(f"SQLite : {sqlite_path} ({sqlite_path.stat().st_size / 1e6:.1f} MB)")
    if args.sample_rows > 0:
        sample_path = args.out.parent / "sample" / f"{args.out.stem}_sample.csv"
        write_csv([sample_rows(collected, args.sample_rows)], sample_path)
        print(f"Sample : {sample_path} ({min(args.sample_rows, count)} rows)")

    print(
        f"CSV    : {args.out} ({args.out.stat().st_size / 1e6:.1f} MB, {count} rows, {len(ALL_COLUMNS)} columns)"
    )
    print_stats(collected)
    share = {}
    for r in collected:
        share[r["intensity"]] = share.get(r["intensity"], 0) + 1
    print("Rows by day intensity:", {k: share[k] for k in sorted(share)})
    print(
        f"Total run time: {time.perf_counter() - started:.1f} s on {os.cpu_count()} CPUs (workers={args.workers})"
    )


if __name__ == "__main__":
    main()
