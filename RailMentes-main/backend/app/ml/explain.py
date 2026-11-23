"""SHAP explanations for the delay model ("why is this train predicted late?").

SHAP splits a prediction into one contribution per feature. Because the model predicts the CHANGE in
delay, every contribution is in minutes added to (or taken from) the train's current delay:

    predicted delay = current delay + expected change + sum of all feature effects

TreeExplainer is exact and fast for tree models (milliseconds for one row). Explanations are computed
only on request, never for every tick. ``shap`` is imported lazily because it is slow to import.

All data is synthetic.
"""

import pandas as pd
from pydantic import BaseModel

from app.ml.dataset import feature_matrix
from app.ml.features import FEATURE_COLUMNS, FeatureRow
from app.ml.model import DelayModel

DEFAULT_TOP_N = 5
MIN_SHOWN_EFFECT_MIN = 0.05  # smaller effects are folded into "other"


class FeatureEffect(BaseModel):
    """One feature's push on the prediction."""

    feature: str  # column name, e.g. "fog_active"
    value: float | str | None  # the feature's value for this train (None = not available)
    effect_min: float  # minutes added to the delay (negative = reduces it)


class Explanation(BaseModel):
    """Why the model predicts this delay at one future station of one train."""

    horizon: int  # 1 = next station, 2 = the one after, 3
    current_delay_min: float
    expected_change_min: float  # the average change before looking at any feature
    predicted_delay_min: float
    factors: list[FeatureEffect]  # the biggest effects first
    other_effect_min: float  # sum of all effects not listed in ``factors``


class Explainer:
    """Wraps one SHAP TreeExplainer per horizon (built on first use, then reused)."""

    def __init__(self, model: DelayModel):
        self.model = model
        self._explainers: dict[int, object] = {}

    def _explainer(self, horizon: int):  # noqa: ANN202 - shap type is only known after the lazy import
        if horizon not in self._explainers:
            import shap

            self._explainers[horizon] = shap.TreeExplainer(self.model.boosters[horizon])
        return self._explainers[horizon]

    def prepare(self, horizon: int) -> None:
        """Build the explainer of one horizon ahead of time."""
        self._explainer(horizon)

    def shap_values(self, frame: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, float]:
        """Return (effects per row and feature in minutes, expected change) for rows of raw data."""
        explainer = self._explainer(horizon)
        matrix = feature_matrix(frame)
        values = explainer.shap_values(matrix, check_additivity=False)
        return pd.DataFrame(values, columns=list(FEATURE_COLUMNS)), float(explainer.expected_value)

    def explain(self, row: FeatureRow, horizon: int, top_n: int = DEFAULT_TOP_N) -> Explanation:
        """Explain the prediction for ONE train from its live feature row."""
        frame = pd.DataFrame([row])
        effects, base = self.shap_values(frame, horizon)
        per_feature = effects.iloc[0]
        order = per_feature.abs().sort_values(ascending=False).index
        shown = [name for name in order if abs(per_feature[name]) >= MIN_SHOWN_EFFECT_MIN][:top_n]
        other = float(per_feature.drop(shown).sum())
        current = float(row["delay_now"])
        return Explanation(
            horizon=horizon,
            current_delay_min=current,
            expected_change_min=round(base, 2),
            predicted_delay_min=round(current + base + float(per_feature.sum()), 2),
            factors=[
                FeatureEffect(
                    feature=name, value=_clean(row[name]), effect_min=round(float(per_feature[name]), 2)
                )
                for name in shown
            ],
            other_effect_min=round(other, 2),
        )

    def global_importance(self, frame: pd.DataFrame, horizon: int) -> pd.Series:
        """Mean absolute effect (minutes) of each feature over ``frame``, biggest first."""
        effects, _ = self.shap_values(frame, horizon)
        return effects.abs().mean().sort_values(ascending=False)


def _clean(value: object) -> float | str | None:
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return None
    return value if isinstance(value, str) else float(value)  # type: ignore[arg-type]
