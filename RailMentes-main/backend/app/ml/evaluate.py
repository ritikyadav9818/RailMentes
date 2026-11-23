"""Test-set evaluation: MAE / RMSE per model and horizon, breakdowns, and "late or not" quality.

Everything works on one long table with a row per (test row, horizon, model), so a breakdown is
just a group-by. "Late" means more than 5 minutes (``LATE_THRESHOLD_MIN``).

All data is synthetic.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

from app.ml.dataset import LATE_THRESHOLD_MIN, disruption_active, target_for, usable_rows
from app.ml.features import STATIONS_AHEAD

Predictor = Callable[[pd.DataFrame, int], np.ndarray]  # (rows, horizon) -> predicted delay
MODEL_ORDER = ("mean", "ridge", "persistence", "lightgbm")


def collect_predictions(test: pd.DataFrame, predictors: dict[str, Predictor]) -> pd.DataFrame:
    """Return one row per (test row, horizon, model) with the actual and predicted delay and group labels."""
    parts = []
    for horizon in range(1, STATIONS_AHEAD + 1):
        rows = usable_rows(test, horizon)
        common = pd.DataFrame(
            {
                "horizon": horizon,
                "actual": target_for(rows, horizon).to_numpy(),
                "train_category": rows["train_category"].to_numpy(),
                "disruption": np.where(disruption_active(rows), "disruption ahead", "no disruption"),
                "intensity": rows["intensity"].to_numpy(),
            }
        )
        common["actual_late"] = np.where(common["actual"] > LATE_THRESHOLD_MIN, "late (>5 min)", "on time")
        for name, predict in predictors.items():
            parts.append(common.assign(model=name, predicted=predict(rows, horizon)))
    return pd.concat(parts, ignore_index=True)


def _errors(group: pd.DataFrame) -> pd.Series:
    error = group["predicted"] - group["actual"]
    return pd.Series({"n": len(group), "mae": error.abs().mean(), "rmse": float(np.sqrt((error**2).mean()))})


def _ordered(table: pd.DataFrame) -> pd.DataFrame:
    table = table.copy()
    table["model"] = pd.Categorical(table["model"], categories=MODEL_ORDER, ordered=True)
    sort_keys = [c for c in table.columns if c not in ("n", "mae", "rmse", "precision", "recall", "f1")]
    return table.sort_values(sort_keys).reset_index(drop=True)


def error_table(predictions: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """MAE and RMSE per model and horizon, optionally split by a label column (e.g. ``disruption``)."""
    keys = ([by] if by else []) + ["horizon", "model"]
    table = predictions.groupby(keys, observed=True)[["predicted", "actual"]].apply(_errors).reset_index()
    table["n"] = table["n"].astype(int)
    return _ordered(table)


def late_quality(predictions: pd.DataFrame) -> pd.DataFrame:
    """Precision and recall of "will be late (> 5 min)" per model and horizon.

    Precision: of the trains predicted late, how many really were. Recall: of the trains that really
    were late, how many were predicted late.
    """
    rows = []
    for (horizon, model), group in predictions.groupby(["horizon", "model"], observed=True):
        said_late = group["predicted"] > LATE_THRESHOLD_MIN
        was_late = group["actual"] > LATE_THRESHOLD_MIN
        true_positive = int((said_late & was_late).sum())
        precision = true_positive / said_late.sum() if said_late.sum() else float("nan")
        recall = true_positive / was_late.sum() if was_late.sum() else float("nan")
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else float("nan")
        rows.append(
            {
                "horizon": horizon,
                "model": model,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "n_late": int(was_late.sum()),
            }
        )
    return _ordered(pd.DataFrame(rows))


def lightgbm_vs_persistence(table: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Add the MAE gain of LightGBM over persistence (positive = LightGBM better, in minutes)."""
    wide = table.pivot_table(index=keys, columns="model", values="mae", observed=True)
    out = wide[["persistence", "lightgbm"]].copy()
    out["gain_min"] = out["persistence"] - out["lightgbm"]
    return out.reset_index()


def to_markdown(table: pd.DataFrame, digits: int = 2) -> str:
    """Render a frame as a GitHub markdown table (no extra dependency)."""

    def cell(value: object) -> str:
        if isinstance(value, float | np.floating):
            return "n/a" if np.isnan(value) else f"{value:.{digits}f}"
        return str(value)

    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    divider = "|" + "|".join("---" for _ in table.columns) + "|"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([header, divider, *body])
