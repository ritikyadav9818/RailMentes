"""Simple baselines the LightGBM model has to beat.

    mean         - always predict the average training delay at that horizon
    ridge        - linear regression with a small penalty (Ridge) on all features
    persistence  - "the delay stays what it is now" (the strong one: it is the main bar to beat)

All data is synthetic.
"""

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.dataset import feature_matrix, target_for, usable_rows
from app.ml.features import STATIONS_AHEAD

RIDGE_ALPHA = 1.0


def persistence_predict(frame: pd.DataFrame) -> np.ndarray:
    """Predict that the delay at any later station equals the delay right now."""
    return frame["delay_now"].to_numpy(dtype=float)


def fit_mean(train: pd.DataFrame) -> dict[int, float]:
    """Return the training mean delay for each horizon."""
    return {k: float(target_for(usable_rows(train, k), k).mean()) for k in range(1, STATIONS_AHEAD + 1)}


def mean_predict(means: dict[int, float], frame: pd.DataFrame, horizon: int) -> np.ndarray:
    """Predict the stored mean for every row."""
    return np.full(len(frame), means[horizon])


def fit_ridge(train: pd.DataFrame) -> dict[int, Pipeline]:
    """Fit one Ridge model per horizon (missing inputs filled with the median, inputs standardised)."""
    models: dict[int, Pipeline] = {}
    for k in range(1, STATIONS_AHEAD + 1):
        rows = usable_rows(train, k)
        model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=RIDGE_ALPHA))
        models[k] = model.fit(feature_matrix(rows), target_for(rows, k))
    return models


def ridge_predict(models: dict[int, Pipeline], frame: pd.DataFrame, horizon: int) -> np.ndarray:
    """Predict with the Ridge model of this horizon."""
    return models[horizon].predict(feature_matrix(frame))
