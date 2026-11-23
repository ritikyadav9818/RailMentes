"""Train, evaluate and save the delay-prediction model.

Usage (PowerShell, from the repo root):
    .\\backend\\.venv\\Scripts\\python.exe scripts\\train_model.py
    .\\backend\\.venv\\Scripts\\python.exe scripts\\train_model.py --data data\\railmentes_runs.csv --seed 42

Steps: load the synthetic dataset (generated first if the CSV is missing) -> split by day (train / validation /
test) -> fit the baselines (mean, Ridge, persistence) -> train LightGBM with early stopping on the validation
days -> evaluate everything on the test days -> save the model to models/ (git-ignored) and the metrics
table and plots to docs/results/.

All data is synthetic (simulation of a fictional network).
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pandas as pd  # noqa: E402

from app.ml import plots  # noqa: E402
from app.ml.baselines import (  # noqa: E402
    fit_mean,
    fit_ridge,
    mean_predict,
    persistence_predict,
    ridge_predict,
)
from app.ml.datagen import DEFAULT_START, generate_dataset, plan_days, write_csv  # noqa: E402
from app.ml.dataset import (  # noqa: E402
    LATE_THRESHOLD_MIN,
    Split,
    load_dataset,
    split_by_day,
    target_for,
    usable_rows,
)
from app.ml.evaluate import (  # noqa: E402
    Predictor,
    collect_predictions,
    error_table,
    late_quality,
    lightgbm_vs_persistence,
    to_markdown,
)
from app.ml.explain import Explainer  # noqa: E402
from app.ml.features import STATIONS_AHEAD  # noqa: E402
from app.ml.model import DelayModel, ModelConfig, train_model  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EXPLAIN_SAMPLE_ROWS = 2000


def ensure_data(path: Path, days: int, seed: int) -> None:
    """Generate the dataset if the CSV does not exist yet."""
    if path.is_file():
        return
    print(f"{path} not found - generating {days} days (seed {seed}) ...")
    write_csv(generate_dataset(plan_days(days, seed, DEFAULT_START)), path)


def build_predictors(split: Split, model: DelayModel) -> dict[str, Predictor]:
    """Fit the baselines on the training days and return every model as ``(rows, horizon) -> prediction``."""
    means = fit_mean(split.train)
    ridge = fit_ridge(split.train)
    return {
        "mean": lambda rows, k: mean_predict(means, rows, k),
        "ridge": lambda rows, k: ridge_predict(ridge, rows, k),
        "persistence": lambda rows, k: persistence_predict(rows),
        "lightgbm": model.predict,
    }


def split_report(split: Split) -> str:
    """Return the split as a markdown table."""
    rows = [{"part": name, **info} for name, info in split.describe().items()]
    return to_markdown(pd.DataFrame(rows))


def write_report(path: Path, sections: list[tuple[str, str]], intro: str) -> None:
    """Write the metrics markdown file."""
    text = [f"# Delay model: test-set metrics\n\n{intro}\n"]
    text += [f"\n## {title}\n\n{body}\n" for title, body in sections]
    path.write_text("".join(text), encoding="utf-8")


def make_plots(split: Split, model: DelayModel, predictors: dict[str, Predictor], errors: pd.DataFrame,
               out: Path) -> list[Path]:
    """Draw the four result figures."""
    horizons = range(1, STATIONS_AHEAD + 1)
    rows = {k: usable_rows(split.test, k) for k in horizons}
    actual = {k: target_for(rows[k], k).to_numpy() for k in horizons}
    persistence = {k: predictors["persistence"](rows[k], k) for k in horizons}
    boosted = {k: predictors["lightgbm"](rows[k], k) for k in horizons}
    sample = split.test.sample(n=min(EXPLAIN_SAMPLE_ROWS, len(split.test)), random_state=model.config.seed)
    explainer = Explainer(model)
    importance = {k: explainer.global_importance(sample, k) for k in horizons}
    return [
        plots.plot_mae_comparison(errors, out / "delay_mae_comparison.png"),
        plots.plot_error_by_horizon(errors, out / "delay_error_by_horizon.png"),
        plots.plot_predicted_vs_actual(actual, persistence, boosted, out / "delay_predicted_vs_actual.png"),
        plots.plot_feature_importance(importance, out / "delay_feature_importance.png"),
    ]


def main() -> None:
    """Run the whole training and evaluation pipeline."""
    parser = argparse.ArgumentParser(description="Train and evaluate the RailMentes delay model.")
    parser.add_argument("--data", type=Path, default=REPO / "data" / "railmentes_runs.csv")
    parser.add_argument("--days", type=int, default=180, help="days to generate if --data does not exist")
    parser.add_argument("--seed", type=int, default=42, help="seed for data generation and for LightGBM")
    parser.add_argument("--model-out", type=Path, default=REPO / "models" / "delay_model.json")
    parser.add_argument("--results-dir", type=Path, default=REPO / "docs" / "results")
    parser.add_argument("--no-plots", action="store_true", help="skip the PNG figures")
    args = parser.parse_args()

    started = time.perf_counter()
    ensure_data(args.data, args.days, args.seed)
    data = load_dataset(args.data)
    split = split_by_day(data)
    print("Split by day (no day appears in two parts):")
    print(split_report(split))

    model = train_model(split, ModelConfig(seed=args.seed))
    model.save(args.model_out)
    print(f"\nTrained. Best iterations per horizon: {model.info['best_iterations']}. Saved to {args.model_out}")

    predictors = build_predictors(split, model)
    predictions = collect_predictions(split.test, predictors)
    errors = error_table(predictions)
    sections = [
        ("Split by day", split_report(split)),
        ("Test error by model and station horizon (minutes)", to_markdown(errors)),
        ("LightGBM gain over persistence (MAE, minutes; positive = LightGBM better)",
         to_markdown(lightgbm_vs_persistence(errors, ["horizon"]))),
        (f"Late or not (delay > {LATE_THRESHOLD_MIN:g} min): precision and recall", to_markdown(late_quality(predictions))),
    ]
    breakdowns = [
        ("disruption", "Disruption ahead (any disruption on the next blocks) vs none"),
        ("actual_late", "Delay above 5 minutes vs not (split by the real outcome)"),
        ("train_category", "By train type"),
    ]
    for column, title in breakdowns:
        table = error_table(predictions, by=column)
        gain = lightgbm_vs_persistence(table, [column, "horizon"])
        counts = table[table["model"] == "lightgbm"][[column, "horizon", "n"]]
        sections.append((f"{title}: LightGBM vs persistence (MAE)", to_markdown(gain.merge(counts, on=[column, "horizon"]))))
        sections.append((f"{title}: all models", to_markdown(table)))

    args.results_dir.mkdir(parents=True, exist_ok=True)
    errors.to_csv(args.results_dir / "delay_metrics.csv", index=False)
    intro = (
        "Synthetic data only. Test = the latest days of the dataset, never used for training or early stopping. "
        "Delays in minutes; MAE = mean absolute error, RMSE = root mean squared error."
    )
    write_report(args.results_dir / "delay_metrics.md", sections, intro)
    if not args.no_plots:
        for path in make_plots(split, model, predictors, errors, args.results_dir):
            print(f"saved {path}")

    pivot = errors.pivot_table(index="model", columns="horizon", values=["mae", "rmse"], observed=True)
    print("\nTest MAE / RMSE (minutes):")
    print(pivot.round(2).to_string())
    print(f"\nMetrics table: {args.results_dir / 'delay_metrics.md'}   total time {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
