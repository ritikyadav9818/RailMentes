"""Live delay prediction: predicted arrival times for every active train in a snapshot.

``DelayPredictor`` loads the saved model and predicts with the SAME ``build_features`` rows the model
was trained on. If the model file is missing, switched off or broken, it falls back to PERSISTENCE
("the delay stays what it is now") and says so (``source`` and ``reason``). Persistence gives exactly the
placeholder times the engine already puts in a snapshot, so the fallback changes nothing visible.

All data is synthetic.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.dataset import feature_matrix
from app.ml.explain import DEFAULT_TOP_N, Explainer, Explanation
from app.ml.features import STATIONS_AHEAD, FeatureRow
from app.ml.model import DelayModel
from app.models.schemas import StateSnapshot, StationStop, TrainState

logger = logging.getLogger(__name__)

SOURCE_MODEL = "lightgbm"
SOURCE_FALLBACK = "persistence"


class DelayPredictor:
    """Predicts the delay at the next 3 stations of a train. Falls back to persistence without a model."""

    def __init__(self, model: DelayModel | None = None, reason: str = ""):
        self.model = model
        self.reason = reason if model is None else ""  # why there is no model (empty when there is one)
        self._explainer: Explainer | None = None

    @property
    def source(self) -> str:
        """Return "lightgbm" when the model is used, otherwise "persistence"."""
        return SOURCE_MODEL if self.model is not None else SOURCE_FALLBACK

    def predict_delays(self, features: dict[str, FeatureRow]) -> dict[str, list[float]]:
        """Return, per train id, the predicted delay (min) at the 1st, 2nd and 3rd next station."""
        if not features:
            return {}
        frame = pd.DataFrame(list(features.values()), index=list(features))
        now = frame["delay_now"].to_numpy(dtype=float)
        if self.model is None:
            columns = [now] * STATIONS_AHEAD
        else:
            matrix = feature_matrix(frame)
            columns = [now + self.model.predict_change(matrix, k) for k in range(1, STATIONS_AHEAD + 1)]
        stacked = np.column_stack(columns)
        return {train_id: stacked[i].tolist() for i, train_id in enumerate(features)}

    def apply(self, snapshot: StateSnapshot, features: dict[str, FeatureRow]) -> StateSnapshot:
        """Return the snapshot with ``next_stations[].predicted_min`` set from the model.

        Only the predicted times change. Stations beyond the 3rd use the 3rd station's predicted delay.
        A predicted time is never earlier than the current tick.
        """
        if self.model is None or not features:
            return snapshot
        delays = self.predict_delays(features)
        trains = [
            _with_predictions(train, delays[train.id], snapshot.tick) if train.id in delays else train
            for train in snapshot.trains
        ]
        return snapshot.model_copy(update={"trains": trains})

    def warm_up(self) -> None:
        """Build the SHAP explainers now (about 2 s), so the first explanation request is fast."""
        if self.model is None:
            return
        self._explainer = self._explainer or Explainer(self.model)
        for horizon in range(1, STATIONS_AHEAD + 1):
            self._explainer.prepare(horizon)

    def explain(self, row: FeatureRow, horizon: int, top_n: int = DEFAULT_TOP_N) -> Explanation:
        """Explain the model's prediction for one train (SHAP). Raises RuntimeError without a model."""
        if self.model is None:
            raise RuntimeError(f"no delay model loaded ({self.reason}); predictions use persistence")
        if self._explainer is None:
            self._explainer = Explainer(self.model)
        return self._explainer.explain(row, horizon, top_n)


def _with_predictions(train: TrainState, delays: list[float], tick: int) -> TrainState:
    stops = [
        StationStop(
            station=stop.station,
            will_stop=stop.will_stop,
            scheduled_min=stop.scheduled_min,
            predicted_min=max(tick, stop.scheduled_min + round(delays[min(i, len(delays) - 1)])),
        )
        for i, stop in enumerate(train.next_stations)
    ]
    return train.model_copy(update={"next_stations": stops})


def load_predictor(path: Path, enabled: bool = True) -> DelayPredictor:
    """Load the model at ``path``; on any problem return a persistence predictor and log why."""
    if not enabled:
        reason = "switched off (USE_ML_MODEL)"
    elif not path.is_file():
        reason = f"model file not found at {path}; run scripts/train_model.py"
    else:
        try:
            return DelayPredictor(DelayModel.load(path))
        except Exception as error:  # noqa: BLE001 - a broken model must never stop the server
            reason = f"could not load {path}: {error}"
    logger.warning("Delay model not used - falling back to persistence: %s", reason)
    return DelayPredictor(None, reason)
