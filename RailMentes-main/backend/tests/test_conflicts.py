"""Conflict detector on hand-built toy snapshots: each kind, and no false alarms."""

import pytest
from toys import at_station, in_block, opposing_on_single_line, overtake_at_dvg, snapshot, stop, train

from app.models.corridor import build_corridor
from app.models.network import Direction
from app.models.schemas import Conflict, ConflictKind, Severity, TrainStatus
from app.models.train import TrainCategory
from app.optimizer.conflicts import ConflictDetector


@pytest.fixture(scope="module")
def network():
    return build_corridor()


@pytest.fixture
def detector(network) -> ConflictDetector:
    return ConflictDetector(network, lookahead_min=60)


# ---- the three kinds ------------------------------------------------------------------------
def test_opposing_trains_on_single_line_meet(detector: ConflictDetector) -> None:
    (conflict,) = detector.detect(opposing_on_single_line())
    assert conflict.kind is ConflictKind.SINGLE_LINE_MEETING
    assert sorted(conflict.train_ids) == ["A", "B"]
    assert conflict.location == "BHP-GNK-1"
    assert conflict.time_min <= 2  # both enter the segment straight away
    assert conflict.severity is Severity.CRITICAL  # about 19 min lost x express priority 3
    assert "single line BHP-GNK" in conflict.description
    Conflict.model_validate(conflict.model_dump())


def test_meeting_works_for_a_train_already_inside_a_block(detector: ConflictDetector) -> None:
    a = train("A", TrainCategory.EXPRESS, in_block("BHP-GNK-1", 5.0, Direction.FORWARD), [stop("GNK", 14)])
    b = train("B", TrainCategory.EXPRESS, at_station("GNK"), [stop("BHP", 20)])
    (conflict,) = detector.detect(snapshot([a, b]))
    assert conflict.kind is ConflictKind.SINGLE_LINE_MEETING and conflict.train_ids[0] == "A"


def test_same_direction_same_block_is_a_block_conflict(detector: ConflictDetector) -> None:
    # two passengers at VDJ both want VDJ-BHP-1 within a minute of each other (same speed)
    a = train("P1", TrainCategory.PASSENGER, at_station("VDJ"), [stop("BHP", 30)])
    b = train("P2", TrainCategory.PASSENGER, at_station("VDJ"), [stop("BHP", 32)])
    (conflict,) = detector.detect(snapshot([a, b]))
    assert conflict.kind is ConflictKind.BLOCK
    assert conflict.train_ids == ["P1", "P2"]  # P1 gets there first
    assert conflict.location == "VDJ-BHP-1"


def test_faster_train_catching_slower_one_is_overtaking(detector: ConflictDetector) -> None:
    (conflict,) = detector.detect(overtake_at_dvg())
    assert conflict.kind is ConflictKind.OVERTAKING
    assert conflict.train_ids == ["F1", "E1"]  # the freight is ahead
    assert conflict.location == "DVG-KLP-1"
    assert conflict.severity in (Severity.HIGH, Severity.CRITICAL)
    assert "no overtaking between stations" in conflict.description


def test_a_slower_train_behind_a_faster_one_is_only_a_block_conflict(detector: ConflictDetector) -> None:
    # express ahead (leaves DVG at 0), freight right behind: the freight cannot catch up, but it must wait
    express = train("E1", TrainCategory.EXPRESS, at_station("DVG"), [stop("KLP", 19)])
    freight = train("F1", TrainCategory.FREIGHT, at_station("DVG"), [stop("KLP", 35)])
    kinds = {c.kind for c in detector.detect(snapshot([express, freight]))}
    assert ConflictKind.OVERTAKING not in kinds


# ---- severity ------------------------------------------------------------------------------------
def test_severity_follows_wait_and_priority(detector: ConflictDetector) -> None:
    # two freights (priority 1) clash for about a minute: low
    a = train("F1", TrainCategory.FREIGHT, at_station("SGP"), [stop("DVG", 34)])
    b = train("F2", TrainCategory.FREIGHT, at_station("SGP"), [stop("DVG", 44)])
    (conflict,) = detector.detect(snapshot([a, b]))
    assert conflict.kind is ConflictKind.BLOCK and conflict.severity is Severity.LOW


# ---- no false alarms ------------------------------------------------------------------------------
def test_empty_snapshot_has_no_conflicts(detector: ConflictDetector) -> None:
    assert detector.detect(snapshot([])) == []


def test_clean_snapshot_has_no_conflicts(detector: ConflictDetector) -> None:
    finished = train("X", TrainCategory.EXPRESS, None, [], status=TrainStatus.FINISHED)
    far_apart = [
        train("A", TrainCategory.EXPRESS, at_station("SGP"), [stop("DVG", 20)]),
        train("B", TrainCategory.EXPRESS, at_station("ARC"), [stop("TLG", 20)]),  # other end of the line
    ]
    opposite_on_double = [
        train("C", TrainCategory.EXPRESS, at_station("SGP"), [stop("DVG", 20)]),
        train("D", TrainCategory.EXPRESS, at_station("DVG"), [stop("SGP", 20)]),  # double line: one track each way
    ]
    for trains in ([finished], far_apart, opposite_on_double):
        assert detector.detect(snapshot(trains)) == []


def test_trains_that_pass_one_after_the_other_do_not_conflict(detector: ConflictDetector) -> None:
    a = train("A", TrainCategory.PASSENGER, at_station("VDJ"), [stop("BHP", 31)])
    b = train("B", TrainCategory.PASSENGER, at_station("VDJ"), [stop("BHP", 60)])  # leaves 30 min later
    assert detector.detect(snapshot([a, b])) == []


def test_not_started_train_is_considered_from_its_scheduled_departure(network) -> None:
    a = train("A", TrainCategory.EXPRESS, at_station("BHP"), [stop("GNK", 20)])
    b = train("B", TrainCategory.EXPRESS, None, [stop("GNK", 50), stop("BHP", 70)], status=TrainStatus.NOT_STARTED)
    # B starts at GNK at minute 50: A has long left the segment
    assert ConflictDetector(network).detect(snapshot([a, b])) == []
    a2 = train("A", TrainCategory.EXPRESS, at_station("BHP"), [stop("GNK", 20)])
    b2 = train("B", TrainCategory.EXPRESS, None, [stop("GNK", 1), stop("BHP", 21)], status=TrainStatus.NOT_STARTED)
    assert [c.kind for c in ConflictDetector(network).detect(snapshot([a2, b2]))] == [ConflictKind.SINGLE_LINE_MEETING]


# ---- configuration -----------------------------------------------------------------------------------
def test_lookahead_is_configurable(network) -> None:
    a = train("A", TrainCategory.EXPRESS, at_station("BHP"), [stop("GNK", 70)])  # leaves BHP at about minute 51
    b = train("B", TrainCategory.EXPRESS, at_station("GNK"), [stop("BHP", 70)])
    state = snapshot([a, b])
    assert ConflictDetector(network, lookahead_min=30).detect(state) == []
    assert len(ConflictDetector(network, lookahead_min=60).detect(state)) == 1


def test_lookahead_must_be_positive(network) -> None:
    with pytest.raises(ValueError):
        ConflictDetector(network, lookahead_min=0)


def test_one_conflict_per_pair_and_stable_ids(detector: ConflictDetector) -> None:
    state = opposing_on_single_line()
    first, second = detector.detect(state), detector.detect(state)
    assert first == second and first[0].id == "c-A-B"


def test_conflicts_are_found_on_a_real_run(network) -> None:
    from app.simulation.disruptions import Intensity
    from app.simulation.scenario import Scenario

    engine = Scenario(seed=42, intensity=Intensity.MEDIUM).build(network)
    detector = ConflictDetector(network)
    found = set()
    while not engine.is_done():
        found.update(c.id for c in detector.detect(engine.snapshot()))
        engine.step()
    assert found  # the simulated day has real meetings and queues
