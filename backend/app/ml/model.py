"""The LightGBM delay model: one booster per horizon (next, 2nd and 3rd station).

Each booster learns the CHANGE in delay (``target - delay_now``), not the delay itself. So the model
starts from the persistence guess ("stays as late as now") and only learns a correction. Prediction =
``delay_now + predicted change``. Early stopping watches the validation block, never the test block.

The model is saved as one JSON file (the LightGBM text dump inside), so it can be read without pickle.

All data is synthetic.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.ml.dataset import Split, feature_matrix, target_for, usable_rows
from app.ml.features import FEATURE_COLUMNS, STATIONS_AHEAD

MODEL_FORMAT: Final = 1


@dataclass(frozen=True)
class ModelConfig:
    """Modest LightGBM settings, chosen once and not tuned on the test block.

    ``objective`` "huber" behaves like squared error for small mistakes and like absolute error for
    big ones, so a few very late trains do not dominate. It was picked on the VALIDATION block only,
    out of squared error, absolute error and huber (huber had the best validation MAE and a good RMSE).
    """

    objective: str = "huber"
    learning_rate: float = 0.15
    num_leaves: int = 15
    min_data_in_leaf: int = 50
    feature_fraction: float = 0.8
    bagging_fraction: float = 0.8
    bagging_freq: int = 1
    lambda_l2: float = 1.0
    max_rounds: int = 2000
    early_stopping_rounds: int = 50
    seed: int = 42

    def lgb_params(self) -> dict[str, Any]:
        """Return the parameters in LightGBM's own names (deterministic on one machine)."""
        return {
            "objective": self.objective,
            "learning_rate": self.learning_rate,
            "num_leaves": self.num_leaves,
            "min_data_in_leaf": self.min_data_in_leaf,
            "feature_fraction": self.feature_fraction,
            "bagging_fraction": self.bagging_fraction,
            "bagging_freq": self.bagging_freq,
            "lambda_l2": self.lambda_l2,
            "seed": self.seed,
            "deterministic": True,
            "force_row_wise": True,
            "num_threads": 1,
            "verbosity": -1,
        }


class DelayModel:
    """Three boosters (horizon 1, 2, 3) that predict the change in delay."""

    def __init__(
        self, boosters: dict[int, lgb.Booster], config: ModelConfig, info: dict[str, Any] | None = None
    ):
        self.boosters = boosters
        self.config = config
        self.info = info or {}

    def predict_change(self, features: pd.DataFrame, horizon: int) -> np.ndarray:
        """Return the predicted change in delay (minutes) for each row of a ``feature_matrix``."""
        booster = self.boosters[horizon]
        # a plain array is much faster than a DataFrame here (LightGBM re-checks every column otherwise)
        return booster.predict(features.to_numpy(dtype=float), num_iteration=booster.best_iteration)

    def predict(self, frame: pd.DataFrame, horizon: int) -> np.ndarray:
        """Return the predicted delay (minutes) at the ``horizon``-th next station."""
        change = self.predict_change(feature_matrix(frame), horizon)
        return frame["delay_now"].to_numpy(dtype=float) + change

    # ---- saving ----------------------------------------
    def save(self, path: Path) -> None:
        """Write the model to a JSON file (creates the folder)."""
        payload = {
            "format": MODEL_FORMAT,
            "feature_columns": list(FEATURE_COLUMNS),
            "config": asdict(self.config),
            "info": self.info,
            "boosters": {
                str(k): {"best_iteration": b.best_iteration, "model": b.model_to_string()}
                for k, b in self.boosters.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "DelayModel":
        """Read a model written by ``save``. Raises ValueError if the file does not fit this code."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != MODEL_FORMAT or payload.get("feature_columns") != list(FEATURE_COLUMNS):
            raise ValueError("model file does not match the current feature list; retrain it")
        boosters = {}
        for key, item in payload["boosters"].items():
            booster = lgb.Booster(model_str=item["model"])
            booster.best_iteration = item["best_iteration"]
            boosters[int(key)] = booster
        return cls(boosters, ModelConfig(**payload["config"]), payload.get("info", {}))


def _dataset(frame: pd.DataFrame, horizon: int) -> lgb.Dataset:
    rows = usable_rows(frame, horizon)
    change = target_for(rows, horizon) - rows["delay_now"].astype(float)
    return lgb.Dataset(feature_matrix(rows), label=change, free_raw_data=False)


def train_model(split: Split, config: ModelConfig | None = None) -> DelayModel:
    """Train one booster per horizon on ``split.train``; stop early on ``split.validation``."""
    config = config or ModelConfig()
    boosters: dict[int, lgb.Booster] = {}
    for horizon in range(1, STATIONS_AHEAD + 1):
        train_set = _dataset(split.train, horizon)
        validation_set = _dataset(split.validation, horizon)
        boosters[horizon] = lgb.train(
            config.lgb_params(),
            train_set,
            num_boost_round=config.max_rounds,
            valid_sets=[validation_set],
            callbacks=[lgb.early_stopping(config.early_stopping_rounds, verbose=False)],
        )
    info = {
        "split": split.describe(),
        "best_iterations": {str(k): b.best_iteration for k, b in boosters.items()},
        "synthetic_data": True,
    }
    return DelayModel(boosters, config, info)
