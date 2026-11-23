"""Read the saved 20-seed benchmark (``docs/results/benchmark*_summary.csv``) for GET /benchmark/summary."""

import csv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

Variant = Literal["ml", "persistence"]
FILES: dict[str, str] = {"ml": "benchmark_summary.csv", "persistence": "benchmark_persistence_summary.csv"}
LABELS: dict[str, str] = {
    "ml": "ML delay model in the loop (headline)",
    "persistence": "Persistence (no ML model, secondary)",
}
METRICS = (
    "avg_delay_min",
    "punctuality_pct",
    "throughput_per_hour",
    "priority_weighted_delay",
    "actions_applied",
)


class BenchmarkMissingError(LookupError):
    """The summary file does not exist (the benchmark has not been run, or was not copied)."""


class BenchmarkReadError(ValueError):
    """The summary file exists but cannot be understood."""


class BenchmarkRow(BaseModel):
    """One strategy at one intensity: mean and standard deviation over the seeds for each metric."""

    model_config = ConfigDict(extra="forbid")

    intensity: str
    strategy: str
    runs: int
    mean: dict[str, float]
    std: dict[str, float]


class BenchmarkSummary(BaseModel):
    """Response of GET /benchmark/summary."""

    model_config = ConfigDict(extra="forbid")

    variant: Variant
    label: str
    source_file: str
    seeds: int
    rows: list[BenchmarkRow]
    disclaimer: str = "Synthetic data, simulation only."


def _row(raw: dict[str, str]) -> BenchmarkRow:
    return BenchmarkRow(
        intensity=raw["intensity"],
        strategy=raw["strategy"],
        runs=int(raw["runs"]),
        mean={m: float(raw[m]) for m in METRICS},
        std={m: float(raw[f"{m}_std"]) for m in METRICS},
    )


def load_benchmark(results_dir: Path, variant: Variant) -> BenchmarkSummary:
    """Parse one summary CSV; raises BenchmarkMissingError or BenchmarkReadError with a plain message."""
    name = FILES[variant]
    path = results_dir / name
    if not path.is_file():
        raise BenchmarkMissingError(
            f"Benchmark results not found ({name}). Run scripts/run_benchmark.py to create them."
        )
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = [_row(raw) for raw in csv.DictReader(handle)]
    except (KeyError, ValueError, OSError) as error:
        raise BenchmarkReadError(f"Benchmark file {name} could not be read ({error!r}).") from error
    if not rows:
        raise BenchmarkReadError(f"Benchmark file {name} has no rows.")
    return BenchmarkSummary(
        variant=variant, label=LABELS[variant], source_file=name, seeds=max(r.runs for r in rows), rows=rows
    )
