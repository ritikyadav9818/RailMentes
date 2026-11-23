"""Request and small response bodies of the API (the shared data contract stays in models/schemas.py)."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ml.explain import Explanation
from app.models.schemas import Action, DisruptionKind, StrategyName
from app.simulation.disruptions import Intensity

MIN_SPEED = 0.5  # ticks (simulated minutes) per real second
MAX_SPEED = 20.0
MAX_MANUAL_DURATION_MIN = 1440


class Body(BaseModel):
    """Base class: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class StartRequest(Body):
    """POST /scenario/start. Everything is optional."""

    seed: int | None = None  # a different seed rebuilds the scenario first
    strategy: StrategyName | None = None
    speed: float | None = Field(default=None, ge=MIN_SPEED, le=MAX_SPEED)


class ResetRequest(Body):
    """POST /scenario/reset. Missing fields keep their current value."""

    seed: int | None = None
    intensity: Intensity | None = None
    month: int | None = Field(default=None, ge=1, le=12)


class SpeedRequest(Body):
    """POST /scenario/speed."""

    speed: float = Field(ge=MIN_SPEED, le=MAX_SPEED)


class ActionRequest(Body):
    """POST /actions. Either a manual ``action`` or a ``recommendation_id`` + ``decision``."""

    action: Action | None = None
    recommendation_id: str | None = None
    decision: Literal["apply", "ignore", "undo"] | None = None

    @model_validator(mode="after")
    def _exactly_one_form(self) -> Self:
        manual = self.action is not None
        decision = self.recommendation_id is not None and self.decision is not None
        if manual == decision or (self.recommendation_id is None) != (self.decision is None):
            raise ValueError("send either 'action', or both 'recommendation_id' and 'decision'")
        return self


class DisruptionRequest(Body):
    """POST /disruptions: start a manual disruption now."""

    kind: DisruptionKind
    duration_min: int = Field(gt=0, le=MAX_MANUAL_DURATION_MIN)
    target_ids: list[str] = Field(default_factory=list)
    speed_factor: float | None = Field(default=None, ge=0, le=1)
    description: str | None = None


class ScenarioInfo(BaseModel):
    """GET /scenario: current configuration and progress."""

    seed: int
    intensity: Intensity
    month: int
    speed: float
    running: bool
    tick: int
    finished: bool


class TrainExplanation(Explanation):
    """GET /trains/{id}/explanation: why the delay model predicts this delay at one upcoming station."""

    train_id: str
    station: str  # the upcoming station the prediction is for
    model_source: str  # "lightgbm" (explanations need the model)
