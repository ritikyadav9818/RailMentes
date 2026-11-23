"""Tests for disruptions, scenarios and runtime injection."""

import random

import pytest

from app.models.corridor import build_corridor
from app.models.network import Network
from app.models.schemas import Disruption, DisruptionKind, StateSnapshot, TrainStatus
from app.models.train import TrainCategory
from app.simulation.disruptions import (
    INTENSITY_COUNTS,
    MAX_CLOSURE_MIN,
    MAX_WEATHER_MIN,
    Intensity,
    generate_disruptions,
)
from app.simulation.engine import SimulationEngine
from app.simulation.scenario import Scenario
from app.simulation.timetable import build_plan, generate_timetable

SEED = 42


@pytest.fixture(scope="module")
def net() -> Network:
    return build_corridor()


def run_day(net: Network, scenario: Scenario, every: int = 1) -> tuple[SimulationEngine, list[StateSnapshot]]:
    engine = scenario.build(net)
    snapshots = [engine.snapshot()]
    while not engine.is_done():
        engine.step()
        if engine.tick % every == 0:
            snapshots.append(engine.snapshot())
        assert engine.tick < 4000, "simulation did not finish"
    snapshots.append(engine.snapshot())
    return engine, snapshots


def solo_engine(net: Network, specs: list[tuple[str, TrainCategory, str, str, int]]) -> SimulationEngine:
    """Engine with hand-made trains: (id, category, origin, destination, departure)."""
    plans = [build_plan(net, tid, tid, cat, net.shortest_route(a, b), dep) for tid, cat, a, b, dep in specs]
    return SimulationEngine(net, plans, seed=0)


def disruption(
    kind: DisruptionKind, start: int, end: int, targets: list[str], factor: float, did: str = "x"
) -> Disruption:
    return Disruption(
        id=did,
        kind=kind,
        start_tick=start,
        end_tick=end,
        target_ids=targets,
        speed_factor=factor,
        description="t",
    )


def final_delay(engine: SimulationEngine, train_id: str) -> float:
    return next(t.delay_min for t in engine.snapshot().trains if t.id == train_id)


FREIGHT = [("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1)]
KLP_MJG = ["KLP-MJG-1", "KLP-MJG-2", "KLP-MJG-3"]


# ---- determinism and none-intensity ----------------------------------------------------------
def test_same_seed_and_intensity_give_identical_runs(net: Network) -> None:
    scenario = Scenario(seed=SEED, intensity=Intensity.MEDIUM)
    _, first = run_day(net, scenario)
    _, second = run_day(net, scenario)
    assert first == second


def test_intensity_changes_the_run(net: Network) -> None:
    _, low = run_day(net, Scenario(seed=SEED, intensity=Intensity.LOW), every=10)
    _, high = run_day(net, Scenario(seed=SEED, intensity=Intensity.HIGH), every=10)
    assert low[-1].trains != high[-1].trains
    assert max(len(s.disruptions) for s in high) > max(len(s.disruptions) for s in low)


def test_none_intensity_matches_the_undisturbed_engine(net: Network) -> None:
    _, with_scenario = run_day(net, Scenario(seed=SEED, intensity=Intensity.NONE))
    plain = SimulationEngine.from_seed(net, SEED)
    expected = [plain.snapshot()]
    while not plain.is_done():
        plain.step()
        expected.append(plain.snapshot())
    assert with_scenario[:-1] == expected
    assert all(s.disruptions == [] for s in with_scenario)


# ---- closed block -------------------------------------------------------------------------------
def test_closed_block_really_blocks_trains(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    engine.add_disruption(disruption(DisruptionKind.BLOCK_CLOSURE, 0, 300, ["KLP-MJG-2"], 0.0))
    seen_waiting = False
    while not engine.is_done():
        engine.step()
        snap = engine.snapshot()
        train = snap.trains[0]
        in_closed = train.position is not None and train.position.block_id == "KLP-MJG-2"
        if engine.tick < 300:
            assert not in_closed
            closed = [b for b in snap.blocks if b.block_id == "KLP-MJG-2"]
            assert closed and closed[0].closed and closed[0].train_id is None
            seen_waiting |= train.status is TrainStatus.WAITING_FOR_SIGNAL
        assert engine.tick < 1000
    assert seen_waiting
    assert final_delay(engine, "F") > 150  # it sat in front of the closure for ~200 minutes


def test_train_already_inside_a_closing_block_crawls_out(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    engine.add_disruption(
        disruption(DisruptionKind.MAINTENANCE, 50, 150, ["SGP-DVG-1", "SGP-DVG-2", "SGP-DVG-3"], 0.0)
    )
    engine.run_until_done()  # must not divide by zero or hang
    assert engine.is_done()


# ---- fog ------------------------------------------------------------------------------------------
def test_fog_slows_trains_only_in_its_window_and_area(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    engine.add_disruption(disruption(DisruptionKind.FOG, 80, 120, KLP_MJG, 0.5))
    in_area_in_window, in_area_outside, elsewhere_in_window = [], [], []
    while not engine.is_done():
        engine.step()
        train = engine.snapshot().trains[0]
        if (
            train.status is not TrainStatus.RUNNING
            or train.position is None
            or train.position.block_id is None
        ):
            continue
        inside_area = train.position.block_id in KLP_MJG
        inside_window = 80 <= engine.tick < 120
        if inside_area and inside_window:
            in_area_in_window.append(train.speed_kmph)
        elif inside_area:
            in_area_outside.append(train.speed_kmph)
        elif inside_window:
            elsewhere_in_window.append(train.speed_kmph)
    assert in_area_in_window and in_area_outside and elsewhere_in_window
    assert set(in_area_in_window) == {30.0}  # freight 60 km/h x 0.5
    assert set(in_area_outside) == {60.0}
    assert set(elsewhere_in_window) == {60.0}


def test_station_target_slows_adjacent_blocks(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    engine.add_disruption(disruption(DisruptionKind.SIGNAL_FAILURE, 0, 2000, ["DVG"], 0.5))
    engine.run_until_done()
    assert final_delay(engine, "F") > 15  # two segments touch DVG and run at half speed


# ---- late departure and knock-on --------------------------------------------------------------------
LATE_FREIGHT_THEN_PREMIUM = [
    ("F", TrainCategory.FREIGHT, "SGP", "VDJ", 1),
    ("P", TrainCategory.PREMIUM, "SGP", "VDJ", 100),
]


def test_late_departure_delays_the_train_and_others_behind_it(net: Network) -> None:
    normal = solo_engine(net, LATE_FREIGHT_THEN_PREMIUM)
    normal.run_until_done()
    late = solo_engine(net, LATE_FREIGHT_THEN_PREMIUM)
    late.add_disruption(disruption(DisruptionKind.LATE_DEPARTURE, 1, 61, ["F"], 1.0))
    late.run_until_done()
    assert final_delay(late, "F") - final_delay(normal, "F") >= 55
    assert final_delay(normal, "P") <= 0  # premium never meets the freight normally
    assert final_delay(late, "P") > 15  # stuck behind the late freight: knock-on delay


def test_late_train_waits_visibly_at_its_origin(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    engine.add_disruption(disruption(DisruptionKind.LATE_DEPARTURE, 1, 31, ["F"], 1.0))
    for _ in range(20):
        engine.step()
    train = engine.snapshot().trains[0]
    assert train.position is not None and train.position.at_station == "SGP"
    assert train.delay_min >= 19
    assert len(engine.snapshot().disruptions) == 1


# ---- runtime injection ------------------------------------------------------------------------------------
def test_runtime_injection_takes_effect(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    for _ in range(30):
        engine.step()
    added = engine.inject_disruption(DisruptionKind.BLOCK_CLOSURE, 60, ["KLP-MJG-2"])
    assert added.id == "m-001" and added.start_tick == 30 and added.end_tick == 90
    assert [d.id for d in engine.snapshot().disruptions] == ["m-001"]
    while not engine.is_done():
        engine.step()
        position = engine.snapshot().trains[0].position
        if engine.tick < 90 and position and position.block_id:
            assert position.block_id != "KLP-MJG-2"
        assert engine.tick < 1000
    assert [d.id for d in engine.snapshot().disruptions] == []  # window is over


def test_injected_disruptions_get_unique_ids_and_defaults(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    fog = engine.inject_disruption(DisruptionKind.FOG, 30)
    slow = engine.inject_disruption(DisruptionKind.WEATHER_SLOWDOWN, 30, ["BHP-GNK-1"], 0.7)
    assert (fog.id, slow.id) == ("m-001", "m-002")
    assert fog.target_ids == [] and fog.speed_factor == 0.6 and slow.speed_factor == 0.7


def test_injection_rejects_bad_input(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.BLOCK_CLOSURE, 30, ["NOPE-1"])
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.BLOCK_CLOSURE, 30)  # closure needs a target
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.BLOCK_CLOSURE, 30, ["KLP-MJG-2"], 0.5)
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.FOG, 30, speed_factor=0.0)
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.FOG, 0)
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.LATE_DEPARTURE, 10, ["NO-SUCH-TRAIN"])
    assert engine.disruptions == []  # failed injections leave nothing behind
    for _ in range(10):
        engine.step()
    with pytest.raises(ValueError):
        engine.inject_disruption(DisruptionKind.LATE_DEPARTURE, 10, ["F"])  # already left


def test_duplicate_disruption_id_rejected(net: Network) -> None:
    engine = solo_engine(net, FREIGHT)
    engine.add_disruption(disruption(DisruptionKind.FOG, 0, 10, [], 0.5, "same"))
    with pytest.raises(ValueError):
        engine.add_disruption(disruption(DisruptionKind.FOG, 20, 30, [], 0.5, "same"))


def test_scenario_manual_disruptions_are_numbered(net: Network) -> None:
    manual = (disruption(DisruptionKind.FOG, 0, 60, [], 0.7, "anything"),)
    engine = Scenario(seed=SEED, intensity=Intensity.LOW, manual_disruptions=manual).build(net)
    ids = [d.id for d in engine.disruptions]
    assert ids[-1] == "m-001" and all(i.startswith("d-") for i in ids[:-1])
    assert engine.inject_disruption(DisruptionKind.FOG, 10).id == "m-002"


# ---- generator --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("intensity", list(Intensity))
def test_generator_counts_and_limits(net: Network, intensity: Intensity) -> None:
    plans = generate_timetable(net, SEED)
    found = generate_disruptions(net, plans, random.Random(1), intensity, month=1)
    counts = INTENSITY_COUNTS[intensity]
    assert len(found) == counts.weather + counts.signal + counts.late + counts.closure
    assert [d.id for d in found] == [f"d-{i:03d}" for i in range(1, len(found) + 1)]
    assert [d.start_tick for d in found] == sorted(d.start_tick for d in found)
    for d in found:
        length = d.end_tick - d.start_tick
        if d.kind in (DisruptionKind.FOG, DisruptionKind.WEATHER_SLOWDOWN, DisruptionKind.SIGNAL_FAILURE):
            assert 0 < length <= MAX_WEATHER_MIN
        elif d.kind in (DisruptionKind.BLOCK_CLOSURE, DisruptionKind.MAINTENANCE):
            assert 0 < length <= MAX_CLOSURE_MIN and d.speed_factor == 0
        else:
            assert 10 <= length <= 60
        assert d.kind is not DisruptionKind.LATE_DEPARTURE or d.target_ids[0] in {p.id for p in plans}
    assert len({tuple(d.target_ids) for d in found if d.kind is DisruptionKind.LATE_DEPARTURE}) == counts.late


def test_fog_is_likely_in_winter_and_rare_in_summer(net: Network) -> None:
    plans = generate_timetable(net, SEED)

    def fog_count(month: int) -> int:
        total = 0
        for seed in range(60):
            engine = SimulationEngine(net, plans, seed)
            events = generate_disruptions(net, plans, engine.rng, Intensity.LOW, month)
            total += sum(d.kind is DisruptionKind.FOG for d in events)
        return total

    assert fog_count(1) >= 45
    assert fog_count(7) <= 15


def test_month_sets_the_snapshot_date(net: Network) -> None:
    engine = Scenario(seed=SEED, month=7).build(net)
    assert engine.snapshot().sim_time.month == 7
    with pytest.raises(ValueError):
        Scenario(month=13).build(net)


def test_weather_targets_are_main_line_blocks(net: Network) -> None:
    plans = generate_timetable(net, SEED)
    engine = SimulationEngine(net, plans, SEED)
    blocks = {b.id: b for b in net.blocks}
    for d in generate_disruptions(net, plans, engine.rng, Intensity.HIGH, 1):
        if d.kind in (DisruptionKind.FOG, DisruptionKind.WEATHER_SLOWDOWN):
            assert all(t in blocks for t in d.target_ids) and len(d.target_ids) >= 6


# ---- every intensity: snapshots valid, safety holds, everyone finishes ------------------------------------------------
@pytest.mark.parametrize("intensity", list(Intensity))
def test_every_intensity_finishes_safely_with_valid_snapshots(net: Network, intensity: Intensity) -> None:
    engine, snapshots = run_day(net, Scenario(seed=SEED, intensity=intensity), every=3)
    blocks = {b.id: b for b in net.blocks}
    assert all(t.status is TrainStatus.FINISHED for t in snapshots[-1].trains)
    for snap in snapshots:
        assert StateSnapshot.model_validate(snap.model_dump(mode="json")) == snap
        keys = [
            blocks[t.position.block_id].resource_key(t.position.direction)
            for t in snap.trains
            if t.position and t.position.block_id
        ]
        assert len(keys) == len(set(keys)), f"clash at tick {snap.tick}"
        for d in snap.disruptions:
            assert d.start_tick <= snap.tick < d.end_tick
    counts = INTENSITY_COUNTS[intensity]
    assert len(engine.disruptions) == counts.weather + counts.signal + counts.late + counts.closure
