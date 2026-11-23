"""Tests for the tick-based simulation engine."""

import pytest

from app.models.corridor import build_corridor
from app.models.network import LineType, Network
from app.models.schemas import Action, ActionKind, StateSnapshot, TrainStatus
from app.models.train import TrainCategory
from app.simulation.engine import SimulationEngine
from app.simulation.timetable import build_plan

SEED = 42


@pytest.fixture(scope="module")
def net() -> Network:
    return build_corridor()


def run_day(net: Network, seed: int = SEED) -> tuple[SimulationEngine, list[StateSnapshot]]:
    engine = SimulationEngine.from_seed(net, seed)
    snapshots = [engine.snapshot()]
    while not engine.is_done():
        engine.step()
        snapshots.append(engine.snapshot())
        assert engine.tick < 4000, "simulation did not finish"
    return engine, snapshots


@pytest.fixture(scope="module")
def day(net: Network) -> tuple[SimulationEngine, list[StateSnapshot]]:
    return run_day(net)


def pair_engine(net: Network, specs: list[tuple[str, TrainCategory, str, str, int]]) -> SimulationEngine:
    """Engine with hand-made trains: (id, category, origin, destination, departure)."""
    plans = [
        build_plan(net, tid, tid, cat, net.shortest_route(a, b), dep) for tid, cat, a, b, dep in specs
    ]
    return SimulationEngine(net, plans, seed=0)


def final_delay(engine: SimulationEngine, train_id: str) -> float:
    return next(t.delay_min for t in engine.snapshot().trains if t.id == train_id)


# ---- determinism ---------------------------------------------------------------------
def test_same_seed_gives_identical_run(net: Network, day: tuple[SimulationEngine, list[StateSnapshot]]) -> None:
    _, first = day
    _, second = run_day(net)
    assert len(first) == len(second)
    assert all(a == b for a, b in zip(first, second, strict=True))


def test_different_seed_gives_different_run(net: Network, day: tuple[SimulationEngine, list[StateSnapshot]]) -> None:
    _, other = run_day(net, seed=SEED + 1)
    assert other[600].trains != day[1][600].trains


# ---- safety ----------------------------------------------------------------------------
def test_no_two_trains_share_a_block_resource(net: Network, day: tuple[SimulationEngine, list[StateSnapshot]]) -> None:
    blocks = {b.id: b for b in net.blocks}
    for snap in day[1]:
        keys = [
            blocks[t.position.block_id].resource_key(t.position.direction)
            for t in snap.trains
            if t.position and t.position.block_id
        ]
        assert len(keys) == len(set(keys)), f"clash at tick {snap.tick}"
        assert len(snap.blocks) == len(keys)


def test_single_segments_never_carry_opposing_trains(
    net: Network, day: tuple[SimulationEngine, list[StateSnapshot]]
) -> None:
    blocks = {b.id: b for b in net.blocks}
    for snap in day[1]:
        directions: dict[tuple[str, str], set[str]] = {}
        for t in snap.trains:
            if t.position and t.position.block_id:
                blk = blocks[t.position.block_id]
                if blk.line is LineType.SINGLE:
                    directions.setdefault((blk.from_code, blk.to_code), set()).add(t.position.direction.value)
        assert all(len(d) == 1 for d in directions.values()), f"head-on at tick {snap.tick}"


def test_opposing_trains_share_single_line_and_one_waits(net: Network) -> None:
    # Both are passengers meeting on the single stretch BHP-GNK-RMJ.
    engine = pair_engine(
        net,
        [
            ("EAST", TrainCategory.PASSENGER, "VDJ", "RMJ", 1),
            ("WEST", TrainCategory.PASSENGER, "RMJ", "VDJ", 1),
        ],
    )
    saw_waiting = False
    while not engine.is_done():
        engine.step()
        snap = engine.snapshot()
        saw_waiting |= any(t.status is TrainStatus.WAITING_FOR_SIGNAL for t in snap.trains)
        sides = {t.position.direction for t in snap.trains if t.position and t.position.block_id and "BHP-GNK" in t.position.block_id}
        assert len(sides) <= 1
        assert engine.tick < 1000
    assert saw_waiting
    assert max(final_delay(engine, "EAST"), final_delay(engine, "WEST")) >= 10


# ---- completion and delay ------------------------------------------------------------------
def test_every_train_completes_its_route(day: tuple[SimulationEngine, list[StateSnapshot]]) -> None:
    engine, snapshots = day
    assert all(t.status is TrainStatus.FINISHED for t in snapshots[-1].trains)
    for tid, log in engine.arrival_log.items():
        plan = engine._trains[tid].plan  # noqa: SLF001 - test peeks at the plan
        assert [s for s, _ in log] == plan.route
        assert [t for _, t in log] == sorted(t for _, t in log)


def test_unblocked_train_is_on_time(net: Network) -> None:
    engine = pair_engine(net, [("P", TrainCategory.PREMIUM, "SGP", "VDJ", 10)])
    engine.run_until_done()
    assert final_delay(engine, "P") <= 0


SLOW_THEN_FAST = [
    ("SLOW", TrainCategory.FREIGHT, "SGP", "VDJ", 1),
    ("FAST", TrainCategory.PREMIUM, "SGP", "VDJ", 20),
]


def test_blocked_train_accumulates_delay(net: Network) -> None:
    engine = pair_engine(net, SLOW_THEN_FAST)
    engine.run_until_done()
    assert final_delay(engine, "FAST") > 30


def test_delay_grows_while_waiting(net: Network) -> None:
    engine = pair_engine(net, SLOW_THEN_FAST)
    seen = []
    while not engine.is_done():
        engine.step()
        seen.append(final_delay(engine, "FAST"))
    assert max(seen) > 30 and seen[-1] == max(seen[-5:])


# ---- actions ----------------------------------------------------------------------------------
def test_hold_delays_the_held_train(net: Network) -> None:
    base = pair_engine(net, [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1)])
    base.run_until_done()
    held = pair_engine(net, [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1)])
    held.apply_action(Action(kind=ActionKind.HOLD, train_id="F", at_station="DVG", hold_minutes=15, reason="t"))
    held.run_until_done()
    assert final_delay(held, "F") - final_delay(base, "F") >= 14


def test_precedence_lets_the_faster_train_through(net: Network) -> None:
    base = pair_engine(net, SLOW_THEN_FAST)
    base.run_until_done()
    ruled = pair_engine(net, SLOW_THEN_FAST)
    ruled.apply_action(
        Action(kind=ActionKind.PRECEDENCE, train_id="SLOW", at_station="KLP", other_train_id="FAST", reason="t")
    )
    ruled.run_until_done()
    assert final_delay(ruled, "FAST") < final_delay(base, "FAST") - 20
    assert final_delay(ruled, "SLOW") >= final_delay(base, "SLOW")


def test_action_takes_effect_on_next_tick(net: Network) -> None:
    engine = pair_engine(net, [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 50)])
    engine.apply_action(Action(kind=ActionKind.HOLD, train_id="F", at_station="SGP", hold_minutes=30, reason="t"))
    assert engine._trains["F"].pending_holds == {}  # noqa: SLF001 - not applied yet
    engine.step()
    assert engine._trains["F"].pending_holds == {"SGP": 30}  # noqa: SLF001


def test_invalid_actions_rejected(net: Network) -> None:
    engine = pair_engine(net, [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1)])
    hold = {"kind": ActionKind.HOLD, "hold_minutes": 5, "reason": "t"}
    with pytest.raises(ValueError):
        engine.apply_action(Action(train_id="NOPE", at_station="SGP", **hold))
    with pytest.raises(ValueError):
        engine.apply_action(Action(train_id="F", at_station="ARC", **hold))  # not on route
    for _ in range(200):
        engine.step()
    with pytest.raises(ValueError):
        engine.apply_action(Action(train_id="F", at_station="SGP", **hold))  # already left
    with pytest.raises(ValueError):
        engine.apply_action(
            Action(kind=ActionKind.PRECEDENCE, train_id="F", at_station="VDJ", other_train_id="F", reason="t")
        )


# ---- snapshots ----------------------------------------------------------------------------------
def test_every_snapshot_validates(day: tuple[SimulationEngine, list[StateSnapshot]]) -> None:
    for snap in day[1]:
        assert StateSnapshot.model_validate(snap.model_dump(mode="json")) == snap


def test_snapshot_content(net: Network) -> None:
    engine = SimulationEngine.from_seed(net, SEED)
    for _ in range(400):
        engine.step()
    snap = engine.snapshot()
    assert snap.tick == 400 and snap.sim_time.hour == 6 and snap.sim_time.minute == 40
    assert snap.disruptions == [] and snap.conflicts == [] and snap.recommendations == []
    assert len(snap.trains) == 25
    running = [t for t in snap.trains if t.status is TrainStatus.RUNNING]
    assert running and all(t.speed_kmph > 0 and t.position and t.position.block_id for t in running)
    assert any(t.next_stations for t in snap.trains)
