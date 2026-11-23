"""Shared data contract (Pydantic) used by simulator, ML, optimizer, API and frontend.

Rules of the contract:
    * Every model forbids unknown fields, so a typo or drifting field fails loudly.
    * Time is in simulation MINUTES since scenario start (== ticks) unless a field
      says otherwise. ``StateSnapshot.sim_time`` is the same instant as a wall-clock
      style datetime, for display only.
    * Keep ``frontend/src/api/types.ts`` in sync with this file by hand.

All data is synthetic.
"""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.network import Direction, LineType
from app.models.train import TrainCategory


class Contract(BaseModel):
    """Base class: strict (no extra fields)."""

    model_config = ConfigDict(extra="forbid")


# ---- enums -------------------------------------------------------------------
class TrainStatus(StrEnum):
    """What a train is doing right now."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    HALTED_AT_STATION = "halted_at_station"
    WAITING_FOR_SIGNAL = "waiting_for_signal"
    FINISHED = "finished"


class Severity(StrEnum):
    """Conflict severity (UI: low = grey, medium/high = amber, critical = red)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictKind(StrEnum):
    """Kinds of upcoming conflict the detector reports."""

    BLOCK = "block"  # two trains need the same block
    PLATFORM = "platform"  # more trains than platforms at a station
    OVERTAKING = "overtaking"  # fast train caught behind a slow one on a line with no loop
    SINGLE_LINE_MEETING = "single_line_meeting"  # opposing trains on a single line


class DisruptionKind(StrEnum):
    """Kinds of random or injected disruption."""

    FOG = "fog"
    WEATHER_SLOWDOWN = "weather_slowdown"
    SIGNAL_FAILURE = "signal_failure"
    BLOCK_CLOSURE = "block_closure"
    LATE_DEPARTURE = "late_departure"
    MAINTENANCE = "maintenance"


class ActionKind(StrEnum):
    """What a controller (or strategy) can do."""

    HOLD = "hold"  # keep a train at a station for N minutes
    PRECEDENCE = "precedence"  # one train yields to another at a station


class RecommendationStatus(StrEnum):
    """Life cycle of a recommendation shown in the alerts feed."""

    PROPOSED = "proposed"
    APPLIED = "applied"
    IGNORED = "ignored"
    UNDONE = "undone"


class StrategyName(StrEnum):
    """The four control strategies we always compare."""

    NO_CONTROL = "no_control"
    FCFS = "fcfs"
    PRIORITY = "priority"
    CPSAT = "cpsat"


# ---- static network (GET /network) ---------------------------------------------
class StationInfo(Contract):
    """A station as the frontend needs it to draw the map."""

    code: str
    name: str
    size: int = Field(ge=1, le=3)  # 1 major, 2 medium, 3 minor
    platforms: int = Field(ge=1)
    is_junction: bool = False
    freight_only: bool = False


class BlockInfo(Contract):
    """A block section (static data)."""

    id: str
    from_code: str
    to_code: str
    length_km: float = Field(gt=0)
    line: LineType
    speed_limit_kmph: int = Field(gt=0)


class NetworkInfo(Contract):
    """Whole static network, sent once."""

    disclaimer: str
    stations: list[StationInfo]
    blocks: list[BlockInfo]


# ---- live state ----------------------------------------------------------------
class Position(Contract):
    """Where a train is: inside a block, or standing at a station (exactly one)."""

    block_id: str | None = None
    # Distance already covered in this block, measured in the train's travel direction.
    offset_km: float = Field(default=0.0, ge=0)
    direction: Direction | None = None
    at_station: str | None = None

    @model_validator(mode="after")
    def _block_xor_station(self) -> Self:
        if (self.block_id is None) == (self.at_station is None):
            raise ValueError("position needs exactly one of block_id or at_station")
        if self.block_id is not None and self.direction is None:
            raise ValueError("direction is required when the train is inside a block")
        return self


class StationStop(Contract):
    """One upcoming station for a train (stop or pass-through)."""

    station: str
    will_stop: bool
    scheduled_min: int  # timetable time
    predicted_min: int  # ML-predicted actual time (equals scheduled + predicted delay)


class DelayFactor(Contract):
    """One SHAP-style reason for a predicted delay (shown as a bar in the drawer)."""

    feature: str  # e.g. "fog", "upstream_delay"
    contribution_min: float  # positive = adds delay, negative = reduces it


class TrainState(Contract):
    """Live state of one train."""

    id: str
    name: str
    category: TrainCategory
    priority: int = Field(ge=1)
    position: Position | None  # None while not_started or finished
    speed_kmph: float = Field(ge=0)
    delay_min: float  # current delay vs timetable (negative = early)
    status: TrainStatus
    next_stations: list[StationStop] = Field(default_factory=list)
    delay_factors: list[DelayFactor] = Field(default_factory=list)  # why it is predicted late


class BlockOccupancy(Contract):
    """Dynamic state of a block. The snapshot lists only occupied or closed blocks."""

    block_id: str
    train_id: str | None = None
    direction: Direction | None = None
    closed: bool = False


class Disruption(Contract):
    """An active or scheduled disruption."""

    id: str
    kind: DisruptionKind
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    target_ids: list[str] = Field(default_factory=list)  # block ids / station codes; [] = whole network
    speed_factor: float = Field(ge=0, le=1)  # 1 = no effect, 0 = fully blocked
    description: str


class Conflict(Contract):
    """An upcoming conflict found by look-ahead."""

    id: str
    kind: ConflictKind
    severity: Severity
    train_ids: list[str] = Field(min_length=1)
    location: str  # block id or station code
    time_min: int  # predicted time the conflict happens
    description: str


class Action(Contract):
    """A concrete control action. This is what a Strategy returns."""

    kind: ActionKind
    train_id: str  # the train that is held / that yields
    at_station: str
    hold_minutes: int | None = Field(default=None, gt=0)  # HOLD only
    other_train_id: str | None = None  # PRECEDENCE only: the train that goes first
    reason: str  # plain-language explanation shown to the controller

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Self:
        if self.kind is ActionKind.HOLD and self.hold_minutes is None:
            raise ValueError("hold action needs hold_minutes")
        if self.kind is ActionKind.PRECEDENCE and self.other_train_id is None:
            raise ValueError("precedence action needs other_train_id")
        return self


class Recommendation(Contract):
    """An Action offered to the controller, with context for the alerts feed."""

    id: str
    strategy: StrategyName
    action: Action
    conflict_ids: list[str]  # conflicts this action resolves
    expected_delay_saved_min: float
    status: RecommendationStatus = RecommendationStatus.PROPOSED


class KPI(Contract):
    """Headline numbers for one strategy."""

    strategy: StrategyName
    avg_delay_min: float
    punctuality_pct: float = Field(ge=0, le=100)  # share of trains <= 5 min late
    throughput_per_hour: float = Field(ge=0)
    conflicts_avoided: int = Field(ge=0)
    prediction_mae_min: float | None = None
    prediction_rmse_min: float | None = None


class StateSnapshot(Contract):
    """Everything the UI needs for one tick (REST GET /state and each WebSocket frame)."""

    tick: int = Field(ge=0)
    sim_time: datetime
    running: bool
    strategy: StrategyName
    trains: list[TrainState]
    blocks: list[BlockOccupancy]
    disruptions: list[Disruption]
    conflicts: list[Conflict]
    recommendations: list[Recommendation]
    kpis: KPI
