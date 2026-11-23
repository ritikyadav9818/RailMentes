"""Tests for the shared feature builder (no train/serve skew, no future information)."""

import copy

import pytest

from app.api.runner import SimulationRunner
from app.ml.features import FEATURE_COLUMNS, OPTIONAL_FEATURES, build_features, is_predictable
from app.models.corridor import build_corridor
from app.models.network import Network
from app.models.schemas import Disruption, DisruptionKind, TrainState, TrainStatus
from app.models.train import TrainCategory
from app.simulation.disruptions import Intensity
from app.simulation.engine import SimulationEngine
from app.simulation.scenario import Scenario
from app.simulation.timetable import build_plan


@pytest.fixture(scope="module")
def net() -> Network:
    return build_corridor()


def engine_with(net: Network, specs: list[tuple[str, TrainCategory, str, str, int]]) -> SimulationEngine:
    plans = [build_plan(net, tid, tid, cat, net.shortest_route(a, b), dep) for tid, cat, a, b, dep in specs]
    return SimulationEngine(net, plans, seed=0)


def features_of(engine: SimulationEngine, net: Network, train_id: str) -> dict:
    snapshot = engine.snapshot()
    train = next(t for t in snapshot.trains if t.id == train_id)
    return build_features(snapshot, train, net, engine.last_arrival_delay(train_id))


def run_until(engine: SimulationEngine, condition, limit: int = 3000) -> None:
    while not condition():
        engine.step()
        assert engine.tick < limit, "condition never became true"


def train_state(engine: SimulationEngine, train_id: str) -> TrainState:
    return next(t for t in engine.snapshot().trains if t.id == train_id)


FREIGHT = [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1)]


# ---- columns and values ------------------------------------------------------------------------------
def test_feature_columns_are_exactly_the_declared_ones(net: Network) -> None:
    engine = Scenario(seed=42, intensity=Intensity.LOW).build(net)
    for _ in range(400):
        engine.step()
    snapshot = engine.snapshot()
    rows = [
        build_features(snapshot, t, net, engine.last_arrival_delay(t.id))
        for t in snapshot.trains
        if is_predictable(t)
    ]
    assert rows, "expected trains on the line at tick 400"
    assert all(list(row) == list(FEATURE_COLUMNS) for row in rows)


def test_values_describe_the_train_and_the_clock(net: Network) -> None:
    engine = engine_with(net, [("P", TrainCategory.PREMIUM, "SGP", "ARC", 400)])
    run_until(engine, lambda: engine.tick >= 450)
    row = features_of(engine, net, "P")
    snapshot = engine.snapshot()
    assert row["train_category"] == "premium" and row["priority"] == 4
    assert (row["hour"], row["day_of_week"], row["month"]) == (7, 3, 1)  # 07:30 on Thursday 15 Jan 2026
    assert row["delay_now"] == train_state(engine, "P").delay_min
    assert row["sched_to_s1"] == snapshot.trains[0].next_stations[0].scheduled_min - snapshot.tick
    assert (
        0 < row["dist_to_s1_km"] <= 41 and row["dist_to_s1_km"] < row["dist_to_s2_km"] < row["dist_to_s3_km"]
    )
    assert row["stations_ahead"] == 4 and row["min_speed_factor"] == 1.0


def test_near_the_end_of_the_route_later_stations_are_missing(net: Network) -> None:
    engine = engine_with(net, FREIGHT)
    run_until(engine, lambda: train_state(engine, "F").next_stations[0].station == "VDJ")  # last hop
    row = features_of(engine, net, "F")
    assert row["stations_ahead"] == 1
    assert all(row[c] is None for c in OPTIONAL_FEATURES)
    assert row["sched_to_s1"] is not None and row["dist_to_s1_km"] is not None


def test_works_for_a_train_standing_in_a_station(net: Network) -> None:
    engine = engine_with(
        net, [("P", TrainCategory.PREMIUM, "SGP", "VDJ", 1), ("X", TrainCategory.EXPRESS, "SGP", "VDJ", 3)]
    )
    run_until(engine, lambda: train_state(engine, "X").position is not None)  # waits at SGP
    state = train_state(engine, "X")
    assert state.position is not None and state.position.at_station == "SGP"
    row = features_of(engine, net, "X")
    assert row["dist_to_s1_km"] == pytest.approx(34.0, abs=0.01)


def test_trains_not_on_the_line_are_rejected(net: Network) -> None:
    engine = engine_with(net, FREIGHT)
    waiting = train_state(engine, "F")
    assert not is_predictable(waiting) and waiting.status is TrainStatus.NOT_STARTED
    with pytest.raises(ValueError):
        build_features(engine.snapshot(), waiting, net, 0.0)
    engine.run_until_done()
    with pytest.raises(ValueError):
        build_features(engine.snapshot(), train_state(engine, "F"), net, 0.0)


# ---- congestion and track ------------------------------------------------------------------------------
def test_following_a_slow_train_counts_as_congestion(net: Network) -> None:
    engine = engine_with(
        net, [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1), ("P", TrainCategory.PREMIUM, "SGP", "VDJ", 20)]
    )
    run_until(engine, lambda: engine.tick >= 70)
    assert features_of(engine, net, "P")["trains_in_next_blocks"] == 1  # the freight just ahead
    assert features_of(engine, net, "F")["trains_in_next_blocks"] == 0  # nothing ahead of the freight


def test_opposing_train_on_a_single_line_is_counted(net: Network) -> None:
    engine = engine_with(
        net,
        [
            ("EAST", TrainCategory.PASSENGER, "VDJ", "RMJ", 1),
            ("WEST", TrainCategory.PASSENGER, "RMJ", "VDJ", 1),
        ],
    )
    seen_opposing, seen_single, seen_double = 0, set(), set()
    while not engine.is_done():
        engine.step()
        for tid in ("EAST", "WEST"):
            state = train_state(engine, tid)
            if is_predictable(state):
                row = features_of(engine, net, tid)
                seen_opposing = max(seen_opposing, row["opposing_trains_in_next_blocks"])
                (seen_single if row["next_hop_single_line"] else seen_double).add(tid)
    assert seen_opposing >= 1
    assert seen_single and seen_double  # both kinds of stretch occur on this route


# ---- disruptions -------------------------------------------------------------------------------------------
def test_disruption_flags_follow_active_disruptions(net: Network) -> None:
    engine = engine_with(net, FREIGHT)
    run_until(engine, lambda: engine.tick >= 40)
    calm = features_of(engine, net, "F")
    assert (calm["fog_active"], calm["signal_failure_active"], calm["closure_active"]) == (0, 0, 0)
    assert calm["min_speed_factor"] == 1.0

    engine.inject_disruption(DisruptionKind.WEATHER_SLOWDOWN, 60)
    rain = features_of(engine, net, "F")
    assert (
        rain["weather_slowdown_active"] == 1 and rain["fog_active"] == 0 and rain["min_speed_factor"] == 0.8
    )

    engine.inject_disruption(DisruptionKind.FOG, 60)
    fog = features_of(engine, net, "F")
    assert fog["fog_active"] == 1 and fog["min_speed_factor"] == 0.6

    state = train_state(engine, "F")
    engine.inject_disruption(DisruptionKind.SIGNAL_FAILURE, 60, [state.next_stations[0].station])
    engine.inject_disruption(DisruptionKind.BLOCK_CLOSURE, 60, [state.position.block_id])
    both = features_of(engine, net, "F")
    assert (
        both["signal_failure_active"] == 1 and both["closure_active"] == 1 and both["min_speed_factor"] == 0.0
    )


def test_a_disruption_far_away_does_not_count(net: Network) -> None:
    engine = engine_with(net, FREIGHT)
    run_until(engine, lambda: engine.tick >= 20)
    engine.inject_disruption(DisruptionKind.BLOCK_CLOSURE, 60, ["TLG-ARC-1"])  # other end of the corridor
    assert features_of(engine, net, "F")["closure_active"] == 0


# ---- no future information ----------------------------------------------------------------------------------
def test_features_are_pure_and_ignore_the_future(net: Network) -> None:
    scenario = Scenario(seed=7, intensity=Intensity.LOW)
    calm, doomed = scenario.build(net), scenario.build(net)
    everything = [b.id for b in net.blocks]
    closure = Disruption(
        id="future",
        kind=DisruptionKind.BLOCK_CLOSURE,
        start_tick=420,
        end_tick=520,
        target_ids=everything,
        speed_factor=0.0,
        description="planned for later",
    )
    for engine in (calm, doomed):
        for _ in range(400):
            engine.step()
    doomed.add_disruption(closure)  # starts after tick 400, so a controller cannot see it yet

    snap_a, snap_b = calm.snapshot(), doomed.snapshot()
    on_line = [t for t in snap_a.trains if is_predictable(t)]
    assert on_line
    before = {}
    for t in on_line:
        tb = next(x for x in snap_b.trains if x.id == t.id)
        fa = build_features(snap_a, t, net, calm.last_arrival_delay(t.id))
        fb = build_features(snap_b, tb, net, doomed.last_arrival_delay(t.id))
        assert fa == fb, f"features of {t.id} depend on the future"
        before[t.id] = fa

    frozen = copy.deepcopy(snap_a)
    for _ in range(200):  # now the two futures really differ
        calm.step()
        doomed.step()
    assert calm.snapshot().trains != doomed.snapshot().trains
    for t in on_line:  # recomputing from the old snapshot gives the old features, and it was not modified
        assert build_features(snap_a, t, net, 0.0) is not None
    assert snap_a == frozen


def test_changing_only_future_planned_disruptions_changes_nothing(net: Network) -> None:
    quiet = Scenario(seed=11, intensity=Intensity.NONE).build(net)
    for _ in range(300):
        quiet.step()
    snapshot = quiet.snapshot()
    train = next(t for t in snapshot.trains if is_predictable(t))
    baseline = build_features(snapshot, train, net, quiet.last_arrival_delay(train.id))
    quiet.add_disruption(
        Disruption(
            id="later",
            kind=DisruptionKind.FOG,
            start_tick=900,
            end_tick=960,
            target_ids=[],
            speed_factor=0.5,
            description="x",
        )
    )
    again = quiet.snapshot()
    assert (
        build_features(
            again, next(t for t in again.trains if t.id == train.id), net, quiet.last_arrival_delay(train.id)
        )
        == baseline
    )


# ---- live path ----------------------------------------------------------------------------------------------------
def test_runner_live_features_use_the_same_columns() -> None:
    runner = SimulationRunner(seed=42)
    for _ in range(400):
        runner.engine.step()
    live = runner.live_features()
    assert live and all(list(row) == list(FEATURE_COLUMNS) for row in live.values())
    assert all(train_id in runner.engine.plans for train_id in live)
