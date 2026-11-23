"""Loading the training data, the time-based split and the numeric feature matrix.

The split is by DAY, never random: rows from one day share weather, disruptions and the same trains,
so a random split would leak information from the test set into training. Earlier days train the
model, the next block validates it (early stopping), the latest days test it.

All data is synthetic.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from app.ml.features import FEATURE_COLUMNS, TARGET_COLUMNS

CATEGORY_CODES: Final = {"freight": 0, "passenger": 1, "express": 2, "premium": 3}
LATE_THRESHOLD_MIN: Final = 5.0  # "late" = more than 5 minutes (same rule as the punctuality KPI)
DEFAULT_TRAIN_FRACTION: Final = 0.70
DEFAULT_VALIDATION_FRACTION: Final = 0.15
DISRUPTION_FLAGS: Final = ("fog_active", "weather_slowdown_active", "signal_failure_active", "closure_active")


@dataclass(frozen=True)
class Split:
    """Train / validation / test frames plus the day ranges they cover."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame

    def describe(self) -> dict[str, dict[str, object]]:
        """Return rows, days and first/last day of each part (for logs and docs)."""
        return {
            name: {
                "rows": len(frame),
                "days": int(frame["day"].nunique()),
                "first_day": str(frame["day"].min()),
                "last_day": str(frame["day"].max()),
            }
            for name, frame in (("train", self.train), ("validation", self.validation), ("test", self.test))
        }


def load_dataset(path: Path) -> pd.DataFrame:
    """Read the CSV written by ``scripts/generate_data.py`` (empty cell = missing value)."""
    return pd.read_csv(path)


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Turn generated rows (dicts) into a frame, as if they had been read from the CSV."""
    return pd.DataFrame(rows)


def split_by_day(
    data: pd.DataFrame,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
) -> Split:
    """Split by calendar day: first days train, next validation, last days test. No day is in two parts."""
    if not (train_fraction > 0 and validation_fraction > 0 and train_fraction + validation_fraction < 1):
        raise ValueError("fractions must be positive and leave some days for the test block")
    days = sorted(data["day"].unique())
    if len(days) < 3:
        raise ValueError("need at least 3 days to split into train, validation and test")
    n_train = max(1, int(len(days) * train_fraction))
    n_validation = max(1, int(len(days) * validation_fraction))
    n_train = min(n_train, len(days) - n_validation - 1)
    train_days = set(days[:n_train])
    validation_days = set(days[n_train : n_train + n_validation])
    test_days = set(days[n_train + n_validation :])
    return Split(
        train=data[data["day"].isin(train_days)].reset_index(drop=True),
        validation=data[data["day"].isin(validation_days)].reset_index(drop=True),
        test=data[data["day"].isin(test_days)].reset_index(drop=True),
    )


def feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the model input: FEATURE_COLUMNS in fixed order, all numeric, missing values as NaN.

    The text column ``train_category`` becomes a number (freight 0 ... premium 3). Used for training
    and for live prediction, so both see exactly the same columns.
    """
    matrix = frame.reindex(columns=list(FEATURE_COLUMNS)).copy()
    matrix["train_category"] = matrix["train_category"].map(CATEGORY_CODES)
    return matrix.astype(float)


def target_for(frame: pd.DataFrame, horizon: int) -> pd.Series:
    """Return the real arrival delay at the ``horizon``-th next station (NaN near the end of a route)."""
    return frame[TARGET_COLUMNS[horizon - 1]].astype(float)


def usable_rows(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Keep rows whose target for this horizon exists."""
    return frame[target_for(frame, horizon).notna()]


def disruption_active(frame: pd.DataFrame) -> np.ndarray:
    """Return True for rows where any disruption touches the next blocks of the train."""
    return frame[list(DISRUPTION_FLAGS)].sum(axis=1).to_numpy() > 0
