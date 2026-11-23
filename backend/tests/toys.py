"""Hand-built toy snapshots for the conflict detector and strategy tests (all on the real demo corridor).

Times are simulation minutes; ``tick`` is "now". Predicted = scheduled (no delay) unless a test changes it.
"""

from datetime import datetime

from app.models.network import Direction
from app.models.schemas import (
    KPI,
    Position,
    StateSnapshot,
    StationStop,
    StrategyName,
    TrainState,
    TrainStatus,
)
from app.models.train import TrainCategory, get_train_type

SIM_START = datetime(2026, 1, 15, 0, 0)


def stop(station: str, minute: int, will_stop: bool = True) -> StationStop:
    """An upcoming station at ``minute`` (predicted == scheduled)."""
    return StationStop(station=station, will_stop=will_stop, scheduled_min=minute, predicted_min=minute)


def at_station(code: str) -> Position:
    """A train standing at a station."""
    return Position(at_station=code)


def in_block(block_id: str, offset_km: float, direction: Direction) -> Position:
    """A train inside a block."""
    return Position(block_id=block_id, offset_km=offset_km, direction=direction)


def train(
    train_id: str,
    category: TrainCategory,
    position: Position | None,
    stops: list[StationStop],
    delay: float = 0.0,
    status: TrainStatus = TrainStatus.RUNNING,
) -> TrainState:
    """A train with the priority of its category."""
    return TrainState(
        id=train_id,
        name=f"{category.value.title()} {train_id}",
        category=category,
        priority=get_train_type(category).priority,
        position=position,
        speed_kmph=0.0,
        delay_min=delay,
        status=status,
        next_stations=stops,
    )


def snapshot(trains: list[TrainState], tick: int = 0) -> StateSnapshot:
    """A snapshot with no disruptions, blocks, conflicts or recommendations."""
    kpi = KPI(
        strategy=StrategyName.NO_CONTROL, avg_delay_min=0, punctuality_pct=100, throughput_per_hour=0, conflicts_avoided=0
    )
    return StateSnapshot(
        tick=tick,
        sim_time=SIM_START,
        running=False,
        strategy=StrategyName.NO_CONTROL,
        trains=trains,
        blocks=[],
        disruptions=[],
        conflicts=[],
        recommendations=[],
        kpis=kpi,
    )


def opposing_on_single_line() -> StateSnapshot:
    """Two expresses leave BHP and GNK towards each other on the single line BHP-GNK (32 km, 100 km/h)."""
    a = train("A", TrainCategory.EXPRESS, at_station("BHP"), [stop("GNK", 20)])
    b = train("B", TrainCategory.EXPRESS, at_station("GNK"), [stop("BHP", 20)])
    return snapshot([a, b])


def overtake_at_dvg(shift: int = 0) -> StateSnapshot:
    """A freight leaves DVG for KLP (double line); an express is about to reach DVG and is faster.

    ``shift`` moves every time later by that many minutes (the freight then leaves DVG later).
    """
    freight = train("F1", TrainCategory.FREIGHT, at_station("DVG"), [stop("KLP", 35 + shift)])
    express = train(
        "E1",
        TrainCategory.EXPRESS,
        in_block("SGP-DVG-3", 5.0, Direction.FORWARD),
        [stop("DVG", 3 + shift, will_stop=False), stop("KLP", 22 + shift)],
    )
    return snapshot([freight, express])
