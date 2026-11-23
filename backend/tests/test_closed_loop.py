"""Closed-loop runs: fairness, determinism and "every train still finishes" under every strategy."""

import pytest

from app.models.corridor import build_corridor
from app.models.schemas import Disruption, DisruptionKind
from app.optimizer.closed_loop import run_closed_loop
from app.optimizer.registry import IMPLEMENTED_STRATEGIES, make_strategy
from app.simulation.disruptions import Intensity
from app.simulation.runtime import Phase
from app.simulation.scenario import Scenario


@pytest.fixture(scope="module")
def network():
    return build_corridor()


def run(network, name, seed=42, intensity=Intensity.MEDIUM):
    return run_closed_loop(Scenario(seed=seed, intensity=intensity), make_strategy(name, network), network)


def test_all_strategies_face_the_same_day(network) -> None:
    results = [run(network, name, intensity=Intensity.HIGH) for name in IMPLEMENTED_STRATEGIES]
    assert results[0].disruptions  # a high-intensity day really has disruptions
    for other in results[1:]:
        assert other.disruptions == results[0].disruptions
        assert other.departures == results[0].departures
        assert other.final.trains[0].id == results[0].final.trains[0].id
        assert len(other.final.trains) == len(results[0].final.trains) == 25


def test_a_different_seed_is_a_different_day(network) -> None:
    assert run(network, IMPLEMENTED_STRATEGIES[0], seed=1).departures != run(network, IMPLEMENTED_STRATEGIES[0], seed=2).departures


@pytest.mark.parametrize("name", IMPLEMENTED_STRATEGIES)
def test_same_seed_same_result(network, name) -> None:
    first, second = run(network, name), run(network, name)
    assert first.kpis == second.kpis
    assert first.applied == second.applied
    assert first.conflict_ids == second.conflict_ids


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("name", IMPLEMENTED_STRATEGIES)
def test_high_intensity_day_still_finishes_with_every_train(network, name, seed) -> None:
    result = run(network, name, seed=seed, intensity=Intensity.HIGH)
    assert result.kpis.trains_finished == result.kpis.trains_total == 25


def test_no_control_applies_no_actions_and_changes_nothing(network) -> None:
    result = run(network, IMPLEMENTED_STRATEGIES[0])
    assert result.applied == [] and result.kpis.actions_applied == 0
    engine = Scenario(seed=42, intensity=Intensity.MEDIUM).build(network)
    engine.run_until_done()
    assert result.kpis.avg_delay_min == engine.snapshot().kpis.avg_delay_min  # same as a plain run


def test_actions_are_applied_and_counted(network) -> None:
    result = run(network, IMPLEMENTED_STRATEGIES[1])  # FCFS
    assert result.kpis.actions_applied == len(result.applied) > 0
    assert all(a.reason for a in result.applied)
    assert result.kpis.conflicts_detected == len(result.conflict_ids) > 0


def test_each_conflict_is_acted_on_only_once(network) -> None:
    result = run(network, IMPLEMENTED_STRATEGIES[1])
    slots = [(a.train_id, a.at_station) for a in result.applied]
    assert len(slots) == len(set(slots))


def test_a_deadlock_is_reported(network) -> None:
    closure = Disruption(
        id="x",
        kind=DisruptionKind.BLOCK_CLOSURE,
        start_tick=0,
        end_tick=100000,
        target_ids=["SGP-DVG-1"],
        speed_factor=0.0,
        description="closed all day",
    )
    scenario = Scenario(seed=42, manual_disruptions=(closure,))
    with pytest.raises(RuntimeError, match="not finished"):
        run_closed_loop(scenario, make_strategy(IMPLEMENTED_STRATEGIES[0], network), network, max_ticks=300)


def test_wait_events_are_logged_by_the_engine(network) -> None:
    engine = Scenario(seed=42, intensity=Intensity.HIGH).build(network)
    engine.run_until_done()
    events = engine.wait_events
    assert events and all(e.end is not None and e.end >= e.start for e in events)
    assert all(e.train_id not in e.blockers for e in events)
    assert any(e.blockers for e in events)  # trains really wait for each other
    assert all(t.phase is Phase.FINISHED and t.open_wait is None for t in engine._trains.values())


def test_a_closed_block_is_logged_without_a_blocking_train(network) -> None:
    closure = Disruption(
        id="x",
        kind=DisruptionKind.BLOCK_CLOSURE,
        start_tick=0,
        end_tick=200,
        target_ids=["SGP-DVG-1"],
        speed_factor=0.0,
        description="closed",
    )
    engine = Scenario(seed=42, manual_disruptions=(closure,)).build(network)
    engine.run_until_done()
    closed_waits = [e for e in engine.wait_events if e.block_id == "SGP-DVG-1" and e.start < 200]
    assert closed_waits and all(e.blockers == [] for e in closed_waits[:1])
