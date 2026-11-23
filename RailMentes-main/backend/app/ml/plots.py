"""Result plots for the delay model (saved as PNG files). Colours: one fixed colour per model.

All data is synthetic.
"""

from pathlib import Path
from typing import Final

import matplotlib

matplotlib.use("Agg")  # draw to files only, no window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

MODEL_COLORS: Final = {
    "mean": "#8a8985",
    "ridge": "#1baf7a",
    "persistence": "#eb6834",
    "lightgbm": "#2a78d6",
}
INK: Final = "#0b0b0b"
MUTED: Final = "#52514e"
GRID: Final = "#e4e3df"
SEED: Final = 42
SCATTER_POINTS: Final = 3000
TOP_FEATURES: Final = 10


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def plot_mae_comparison(errors: pd.DataFrame, path: Path) -> Path:
    """Draw grouped bars of the test MAE per model for each station horizon."""
    models = [m for m in MODEL_COLORS if m in set(errors["model"])]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.8 / len(models)
    for i, model in enumerate(models):
        part = errors[errors["model"] == model].sort_values("horizon")
        x = np.arange(len(part)) + (i - (len(models) - 1) / 2) * width
        bars = ax.bar(x, part["mae"], width * 0.88, color=MODEL_COLORS[model], label=model)
        ax.bar_label(bars, fmt="%.1f", fontsize=8, color=INK, padding=2)
    ax.set_xticks(range(len(part)), [f"station {h}" for h in part["horizon"]])
    ax.set_ylabel("MAE on the test days (minutes)", color=MUTED)
    ax.set_ylim(0, errors["mae"].max() * 1.2)  # room for the legend above the bars
    ax.set_title("Mean absolute error by model (lower is better)", color=INK, loc="left", fontsize=12)
    ax.legend(frameon=False, fontsize=9, ncols=len(models), loc="upper left")
    _style(ax)
    return _save(fig, path)


def plot_error_by_horizon(errors: pd.DataFrame, path: Path) -> Path:
    """Two small charts (MAE and RMSE) of error against how many stations ahead we predict."""
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for ax, metric, label in zip(axes, ("mae", "rmse"), ("MAE (minutes)", "RMSE (minutes)"), strict=True):
        for model, color in MODEL_COLORS.items():
            part = errors[errors["model"] == model].sort_values("horizon")
            if part.empty:
                continue
            ax.plot(
                part["horizon"], part[metric], marker="o", markersize=6, linewidth=2, color=color, label=model
            )
        ax.set_xticks(
            sorted(errors["horizon"].unique()), [f"station {h}" for h in sorted(errors["horizon"].unique())]
        )
        ax.set_ylabel(label, color=MUTED)
        _style(ax)
    axes[0].legend(frameon=False, fontsize=9)
    fig.suptitle(
        "Error grows with the horizon (test days, lower is better)", color=INK, x=0.07, ha="left", fontsize=12
    )
    return _save(fig, path)


def plot_predicted_vs_actual(
    actual: dict[int, np.ndarray],
    persistence: dict[int, np.ndarray],
    lightgbm: dict[int, np.ndarray],
    path: Path,
) -> Path:
    """Scatter of predicted against actual delay: persistence (top row) and LightGBM (bottom row)."""
    rng = np.random.default_rng(SEED)
    horizons = sorted(actual)
    fig, axes = plt.subplots(2, len(horizons), figsize=(4 * len(horizons), 7), sharex="col", sharey="col")
    for col, horizon in enumerate(horizons):
        y = actual[horizon]
        pick = rng.choice(len(y), size=min(SCATTER_POINTS, len(y)), replace=False)
        low, high = float(np.min(y)), float(np.max(y))
        for row, (name, pred) in enumerate(
            (("persistence", persistence[horizon]), ("lightgbm", lightgbm[horizon]))
        ):
            ax = axes[row, col]
            ax.scatter(y[pick], pred[pick], s=6, alpha=0.25, color=MODEL_COLORS[name], linewidths=0)
            ax.plot([low, high], [low, high], color=MUTED, linewidth=1, linestyle="--")
            ax.set_title(f"{name}, station {horizon}", color=INK, loc="left", fontsize=10)
            ax.set_ylabel("predicted delay (min)" if col == 0 else "", color=MUTED)
            ax.set_xlabel("actual delay (min)" if row == 1 else "", color=MUTED)
            _style(ax)
    fig.suptitle(
        "Predicted vs actual delay on the test days (dashed = perfect)",
        color=INK,
        x=0.07,
        ha="left",
        fontsize=12,
    )
    fig.tight_layout()
    return _save(fig, path)


def plot_feature_importance(importance: dict[int, pd.Series], path: Path) -> Path:
    """Horizontal bars of mean |SHAP| (minutes) for the top features, one panel per horizon."""
    fig, axes = plt.subplots(1, len(importance), figsize=(5 * len(importance), 5), sharex=True)
    for ax, (horizon, values) in zip(np.atleast_1d(axes), sorted(importance.items()), strict=True):
        top = values.head(TOP_FEATURES)[::-1]
        ax.barh(top.index, top.to_numpy(), color=MODEL_COLORS["lightgbm"], height=0.7)
        ax.set_title(f"station {horizon}", color=INK, loc="left", fontsize=10)
        ax.set_xlabel("average effect on the prediction (minutes)", color=MUTED)
        _style(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.grid(axis="y", visible=False)
    fig.suptitle(
        "What the model uses: mean absolute SHAP effect per feature",
        color=INK,
        x=0.07,
        ha="left",
        fontsize=12,
    )
    fig.tight_layout()
    return _save(fig, path)
