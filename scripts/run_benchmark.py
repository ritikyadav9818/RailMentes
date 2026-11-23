"""Benchmark: no_control, fcfs, priority and cpsat over many seeds at low / medium / high intensity.

Usage (PowerShell, from the repo root):
    .\\backend\\.venv\\Scripts\\python.exe scripts\\run_benchmark.py                 # 20 seeds, ML model, ~10 min
    .\\backend\\.venv\\Scripts\\python.exe scripts\\run_benchmark.py --no-model       # quick mode (persistence)
    .\\backend\\.venv\\Scripts\\python.exe scripts\\run_benchmark.py --seeds 101-106 --out C:\\temp\\tuning

Every strategy faces exactly the same day for a given (seed, intensity). Writes to ``--out``
(default docs/results/, files named ``benchmark[_persistence]_*``): per-run CSV, summary CSV + markdown (mean
and standard deviation), paired comparison against the priority rule, and charts.
Seeds 1-20 are the benchmark seeds; the optimizer's penalty values were tuned on seeds 101-110 only.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.ml.predict import DelayPredictor, load_predictor  # noqa: E402
from app.models.corridor import build_corridor  # noqa: E402
from app.models.schemas import StrategyName  # noqa: E402
from app.optimizer.closed_loop import run_closed_loop  # noqa: E402
from app.optimizer.cpsat.problem import Params  # noqa: E402
from app.optimizer.cpsat.strategy import CpSatStrategy  # noqa: E402
from app.optimizer.registry import IMPLEMENTED_STRATEGIES, make_strategy  # noqa: E402
from app.simulation.disruptions import Intensity  # noqa: E402
from app.simulation.scenario import Scenario  # noqa: E402

MODEL_PATH = ROOT / "models" / "delay_model.json"
DEFAULT_OUT = ROOT / "docs" / "results"
METRICS = (
    ("avg_delay_min", "Average delay (min)", "lower is better"),
    ("punctuality_pct", "Punctuality (% <= 5 min late)", "higher is better"),
    ("throughput_per_hour", "Throughput (trains/hour)", "higher is better"),
    ("priority_weighted_delay", "Priority-weighted delay", "lower is better"),
    ("actions_applied", "Actions per day", "fewer is better"),
)
LABELS = {"no_control": "No control", "fcfs": "FCFS", "priority": "Priority rule", "cpsat": "CP-SAT"}


@lru_cache(maxsize=1)
def _predictor() -> DelayPredictor | None:
    return load_predictor(MODEL_PATH)


def parse_seeds(text: str) -> list[int]:
    """Parse ``1-20`` or ``1,5,9`` into a list of seeds."""
    seeds: list[int] = []
    for part in text.split(","):
        low, _, high = part.partition("-")
        seeds += range(int(low), int(high or low) + 1)
    return seeds


def run_one(job: tuple[int, str, str, bool, dict]) -> dict:
    """Run one (seed, intensity, strategy) in a worker process and return a flat result row."""
    seed, intensity, strategy, use_model, overrides = job
    network = build_corridor()
    name = StrategyName(strategy)
    if name is StrategyName.CPSAT:
        impl = CpSatStrategy(network, params=Params(**overrides))
    else:
        impl = make_strategy(name, network)
    scenario = Scenario(seed=seed, intensity=Intensity(intensity))
    started = time.perf_counter()
    result = run_closed_loop(scenario, impl, network, _predictor() if use_model else None)
    row = {"seed": seed, "intensity": intensity, "strategy": strategy, **result.kpis.model_dump()}
    row["strategy"] = strategy
    row["run_seconds"] = round(time.perf_counter() - started, 2)
    if isinstance(impl, CpSatStrategy):
        times = impl.solve_seconds or [0.0]
        row.update(
            solves=impl.stats["solves"],
            cache_hits=impl.stats["cache_hits"],
            fallbacks=impl.stats["fallbacks"],
            not_optimal=impl.stats["not_optimal"],
            solve_ms_median=round(1000 * float(np.median(times)), 1),
            solve_ms_p95=round(1000 * float(np.percentile(times, 95)), 1),
            solve_ms_max=round(1000 * max(times), 1),
        )
    return row


def summarise(runs: pd.DataFrame) -> pd.DataFrame:
    """Mean and standard deviation over seeds for every (intensity, strategy)."""
    columns = [m for m, _, _ in METRICS] + ["blocking_events", "conflicts_detected"]
    grouped = runs.groupby(["intensity", "strategy"], sort=False)[columns]
    mean, std = grouped.mean(), grouped.std(ddof=1)
    table = mean.join(std, rsuffix="_std")
    table["runs"] = grouped.size()
    return table.reset_index()


def paired(runs: pd.DataFrame, versus: str = "priority", rng_seed: int = 0) -> pd.DataFrame:
    """CP-SAT minus ``versus`` on the same seeds: mean difference, 95% bootstrap interval, seeds won."""
    rng = np.random.default_rng(rng_seed)
    rows = []
    for intensity, group in runs.groupby("intensity", sort=False):
        wide = group.pivot(index="seed", columns="strategy")
        for metric, title, direction in METRICS:
            if "cpsat" not in wide[metric] or versus not in wide[metric]:
                continue
            diff = (wide[metric]["cpsat"] - wide[metric][versus]).to_numpy()
            boots = rng.choice(diff, size=(4000, len(diff))).mean(axis=1)
            low, high = np.percentile(boots, [2.5, 97.5])
            better = diff < -1e-9 if direction != "higher is better" else diff > 1e-9
            worse = diff > 1e-9 if direction != "higher is better" else diff < -1e-9
            rows.append(
                {
                    "intensity": intensity,
                    "metric": title,
                    "mean_diff": diff.mean(),
                    "ci_low": low,
                    "ci_high": high,
                    "cpsat_better_seeds": int(better.sum()),
                    "cpsat_worse_seeds": int(worse.sum()),
                    "seeds": len(diff),
                }
            )
    return pd.DataFrame(rows)


def markdown_summary(table: pd.DataFrame) -> str:
    """Return the summary as a markdown table: mean +- std per metric."""
    head = ["intensity", "strategy", *(title for _, title, _ in METRICS), "runs"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, r in table.iterrows():
        cells = [r["intensity"], LABELS[r["strategy"]]]
        for metric, _, _ in METRICS:
            cells.append(f"{r[metric]:.2f} ± {r[metric + '_std']:.2f}")
        cells.append(str(int(r["runs"])))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def markdown_paired(table: pd.DataFrame) -> str:
    """Return the paired CP-SAT-vs-priority comparison as a markdown table."""
    head = ["intensity", "metric", "CP-SAT minus priority (mean)", "95% interval", "seeds CP-SAT better", "worse"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, r in table.iterrows():
        lines.append(
            f"| {r['intensity']} | {r['metric']} | {r['mean_diff']:+.2f} | [{r['ci_low']:+.2f}, {r['ci_high']:+.2f}] "
            f"| {r['cpsat_better_seeds']}/{r['seeds']} | {r['cpsat_worse_seeds']}/{r['seeds']} |"
        )
    return "\n".join(lines)


def solver_summary(runs: pd.DataFrame) -> str:
    """Return one line about the optimizer's own cost (solve time, fallbacks)."""
    cp = runs[runs["strategy"] == "cpsat"]
    if cp.empty:
        return ""
    return (
        f"CP-SAT solver: {int(cp['solves'].sum())} solves, {int(cp['cache_hits'].sum())} cache hits, "
        f"{int(cp['fallbacks'].sum())} fallbacks to the priority rule, {int(cp['not_optimal'].sum())} not-optimal plans; "
        f"median solve {cp['solve_ms_median'].median():.0f} ms, worst solve {cp['solve_ms_max'].max():.0f} ms; "
        f"a full simulated day takes {cp['run_seconds'].mean():.1f} s on average."
    )


def charts(table: pd.DataFrame, out: Path, stem: str, label: str) -> list[Path]:
    """Draw one grouped bar chart per metric (bars = mean over seeds, whiskers = one standard deviation)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"no_control": "#9aa0a6", "fcfs": "#e8a33d", "priority": "#3b7ddd", "cpsat": "#1b9e77"}
    intensities = list(dict.fromkeys(table["intensity"]))
    strategies = list(dict.fromkeys(table["strategy"]))
    width = 0.8 / len(strategies)
    paths = []
    for metric, title, direction in METRICS:
        fig, ax = plt.subplots(figsize=(7, 4))
        for k, strategy in enumerate(strategies):
            rows = table[table["strategy"] == strategy].set_index("intensity").loc[intensities]
            x = np.arange(len(intensities)) + (k - (len(strategies) - 1) / 2) * width
            ax.bar(x, rows[metric], width, yerr=rows[metric + "_std"], capsize=3, color=colors[strategy],
                   label=LABELS[strategy], edgecolor="white", linewidth=0.5)
        ax.set_xticks(np.arange(len(intensities)), [i.capitalize() for i in intensities])
        ax.set_xlabel("Disruption intensity")
        ax.set_ylabel(title)
        ax.set_title(f"{title} ({direction})\n{label}", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        path = out / f"{stem}_{metric}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths.append(path)
    return paths


def main() -> None:
    """Run the benchmark and write the result files."""
    parser = argparse.ArgumentParser(description="Benchmark the four control strategies over many seeds.")
    parser.add_argument("--seeds", default="1-20", help="e.g. 1-20 or 1,5,9 (default 1-20)")
    parser.add_argument("--intensity", nargs="+", choices=[i.value for i in Intensity], default=["low", "medium", "high"])
    parser.add_argument("--strategies", nargs="+", default=[s.value for s in IMPLEMENTED_STRATEGIES])
    parser.add_argument("--no-model", action="store_true", help="quick mode: persistence instead of the ML model")
    parser.add_argument("--params", default="{}", help='CP-SAT Params overrides as JSON, e.g. \'{"action_penalty": 2}\'')
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-charts", action="store_true")
    args = parser.parse_args()

    overrides = json.loads(args.params)
    unknown = set(overrides) - {f.name for f in fields(Params)}
    if unknown:
        parser.error(f"unknown Params fields: {sorted(unknown)}")
    use_model = not args.no_model
    if use_model and not MODEL_PATH.is_file():
        parser.error(f"no delay model at {MODEL_PATH}; run scripts/train_model.py or use --no-model")
    seeds = parse_seeds(args.seeds)
    jobs = [(s, i, st, use_model, overrides) for i in args.intensity for st in args.strategies for s in seeds]
    print(f"{len(jobs)} runs ({len(seeds)} seeds x {len(args.intensity)} intensities x {len(args.strategies)} strategies), "
          f"predictions: {'ML model' if use_model else 'persistence'}", flush=True)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs, chunksize=1))
    print(f"done in {time.perf_counter() - started:.0f} s", flush=True)

    runs = pd.DataFrame(rows)
    table = summarise(runs)
    stem = "benchmark" if use_model else "benchmark_persistence"
    label = f"mean of {len(seeds)} seeds, {'ML delay model' if use_model else 'persistence'}, synthetic data"
    args.out.mkdir(parents=True, exist_ok=True)
    runs.to_csv(args.out / f"{stem}_runs.csv", index=False)
    table.to_csv(args.out / f"{stem}_summary.csv", index=False)
    pair = paired(runs)
    note = solver_summary(runs)
    text = (
        f"# Benchmark ({label})\n\nSeeds {seeds[0]}..{seeds[-1]}; mean ± standard deviation over seeds.\n\n"
        f"{markdown_summary(table)}\n\n## CP-SAT vs the priority rule (same seeds)\n\n{markdown_paired(pair)}\n\n{note}\n"
    )
    (args.out / f"{stem}_summary.md").write_text(text, encoding="utf-8")
    if not args.no_charts:
        charts(table, args.out, stem, label)
    print(text)


if __name__ == "__main__":
    main()
