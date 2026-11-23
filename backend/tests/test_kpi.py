"""KPI maths on a small hand-checked case."""

import pytest
from toys import at_station, snapshot, train

from app.models.schemas import KPI, StrategyName, TrainStatus
from app.models.train import TrainCategory
from app.optimizer.kpi import RunKpis, compute_kpis, count_blocking_events
from app.simulation.runtime import WaitEvent


def finished(train_id: str, category: TrainCategory, delay: float):
    return train(train_id, category, None, [], delay=delay, status=TrainStatus.FINISHED)


@pytest.fixture
def day():
    """Four finished trains (priority 4, 3, 2, 1) and one that has not started; 2 hours in."""
    return snapshot(
        [
            finished("P", TrainCategory.PREMIUM, -2.0),  # early: counts as 0
            finished("E", TrainCategory.EXPRESS, 3.0),
            finished("S", TrainCategory.PASSENGER, 5.0),  # exactly 5 min late is still punctual
            finished("F", TrainCategory.FREIGHT, 12.0),
            train("N", TrainCategory.PASSENGER, None, [], status=TrainStatus.NOT_STARTED),
        ],
        tick=120,
    )


def test_kpi_maths(day) -> None:
    kpis = compute_kpis(day, StrategyName.FCFS, conflicts_detected=7, actions_applied=3, blocking_events=2)
    assert kpis.avg_delay_min == 5.0  # (0 + 3 + 5 + 12) / 4
    assert kpis.punctuality_pct == 75.0  # 3 of 4 within 5 min
    assert kpis.throughput_per_hour == 2.0  # 4 trains in 2 hours
    assert kpis.priority_weighted_delay == 31.0  # 4*0 + 3*3 + 2*5 + 1*12
    assert (kpis.trains_total, kpis.trains_finished, kpis.end_tick) == (5, 4, 120)
    assert (kpis.conflicts_detected, kpis.actions_applied, kpis.blocking_events) == (7, 3, 2)
    assert kpis.strategy is StrategyName.FCFS


def test_running_trains_use_their_current_delay() -> None:
    state = snapshot([train("A", TrainCategory.EXPRESS, at_station("SGP"), [], delay=8.0)], tick=30)
    kpis = compute_kpis(state, StrategyName.NO_CONTROL)
    assert (kpis.avg_delay_min, kpis.punctuality_pct, kpis.throughput_per_hour) == (8.0, 0.0, 0.0)


def test_empty_day_is_all_zero_and_fully_punctual() -> None:
    kpis = compute_kpis(snapshot([]), StrategyName.NO_CONTROL)
    assert (kpis.avg_delay_min, kpis.punctuality_pct, kpis.throughput_per_hour) == (0.0, 100.0, 0.0)


def test_blocking_events_only_count_real_waits_caused_by_trains() -> None:
    events = [
        WaitEvent("a", "X-1", start=10, blockers=["b"], end=12),  # 2 min: too short
        WaitEvent("a", "X-2", start=20, blockers=["b"], end=23),  # 3 min: counts
        WaitEvent("c", "X-3", start=30, blockers=[], end=60),  # block closed: not a train conflict
        WaitEvent("d", "X-4", start=90, blockers=["e"]),  # still waiting at tick 100: 10 min so far
    ]
    assert count_blocking_events(events, now=100) == 2
    assert count_blocking_events(events, now=100, min_minutes=1) == 3


def test_conflicts_avoided_is_relative_to_no_control(day) -> None:
    kpis = compute_kpis(day, StrategyName.PRIORITY, blocking_events=4)
    assert kpis.to_schema(baseline_blocking_events=10).conflicts_avoided == 6
    assert kpis.to_schema(baseline_blocking_events=3).conflicts_avoided == 0  # never negative
    assert kpis.to_schema().conflicts_avoided == 0
    assert isinstance(kpis.to_schema(10), KPI) and isinstance(kpis, RunKpis)
