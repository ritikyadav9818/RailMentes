"""Detector validation: scoring maths on hand-made observations, plus one real run."""

import pytest

from app.models.corridor import build_corridor
from app.optimizer.conflicts import ConflictDetector
from app.optimizer.validation import Flag, Observations, episodes, observe, pair_id, score, segment_of
from app.simulation.disruptions import Intensity
from app.simulation.runtime import WaitEvent
from app.simulation.scenario import Scenario


def wait(train_id: str, blocker: str, start: int, block: str = "BHP-GNK-1", length: int = 5) -> WaitEvent:
    return WaitEvent(train_id, block, start, [blocker], start + length)


def flags(first: int, last: int, time_min: int, segment: str = "BHP-GNK") -> list[Flag]:
    return [Flag(t, time_min, segment) for t in range(first, last + 1)]


def test_helpers() -> None:
    assert segment_of("BHP-GNK-2") == "BHP-GNK"
    assert pair_id("B", "A") == pair_id("A", "B") == "c-A-B"


def test_episodes_split_on_gaps() -> None:
    runs = episodes({"c-A-B": flags(10, 12, 20) + flags(20, 21, 30)})
    assert [(e.flags[0].tick, e.flags[-1].tick) for _, e in runs] == [(10, 12), (20, 21)]


def test_recall_and_precision_on_a_hand_made_case() -> None:
    obs = Observations(
        events=[
            wait("A", "B", start=100),  # flagged in advance and the time is right
            wait("C", "D", start=200),  # never flagged
            wait("E", "F", start=300),  # flagged only 2 min before: too late to count
            wait("G", "H", start=400, block="DVG-KLP-1"),  # flagged on another segment: no match
        ],
        end_tick=500,
        seen={
            60: {
                "c-A-B": flags(80, 85, 102),  # wait really starts at 100 (within 10 min of 102)
                "c-X-Y": flags(150, 160, 170),  # nothing happens: a false alarm
                "c-E-F": flags(298, 299, 301),
                "c-G-H": flags(380, 390, 401),  # segment BHP-GNK, the wait was at DVG-KLP
            }
        },
    )
    row = score([obs], lookahead=60, min_wait=1)
    assert (row.events, row.events_flagged) == (4, 1) and row.recall == 0.25
    assert row.median_lead_min == 20  # first matching flag at tick 80, wait at 100
    assert row.episodes == 4 and row.episodes_real == 2  # c-A-B, and c-E-F (a flag at 299 <= start 300 matches)
    assert row.precision == 0.5


def test_flags_older_than_the_lookahead_do_not_count() -> None:
    obs = Observations([wait("A", "B", start=100)], 200, {30: {"c-A-B": flags(40, 60, 100)}})  # 40+ min ahead
    assert score([obs], lookahead=30, min_wait=1).events_flagged == 0


def test_short_waits_can_be_left_out() -> None:
    obs = Observations([wait("A", "B", 100, length=2), wait("C", "D", 200, length=6)], 300, {15: {}})
    assert score([obs], 15, min_wait=1).events == 2
    assert score([obs], 15, min_wait=3).events == 1


def test_any_blocker_of_a_long_wait_can_match() -> None:
    event = WaitEvent("A", "BHP-GNK-1", 100, ["X", "B"], 130)
    obs = Observations([event], 200, {60: {"c-A-B": flags(70, 90, 105)}})
    assert score([obs], 60, 1).events_flagged == 1


def test_nothing_to_score_is_perfect_not_a_crash() -> None:
    row = score([Observations([], 100, {60: {}})], 60, 1)
    assert (row.recall, row.precision) == (1.0, 1.0)


@pytest.mark.parametrize("lookahead", [15, 60])
def test_observe_on_a_real_run(lookahead: int) -> None:
    network = build_corridor()
    detectors = {lookahead: ConflictDetector(network, lookahead)}
    obs = observe(Scenario(seed=1, intensity=Intensity.MEDIUM), network, detectors)
    row = score([obs], lookahead, min_wait=3)
    assert row.events > 0 and row.episodes > 0
    assert 0.0 <= row.recall <= 1.0 and 0.0 <= row.precision <= 1.0
    # the detector is useful: it flags most real waits in advance and most flags come true
    assert row.recall >= 0.8 and row.precision >= 0.5
