"""Detector validation: compare the flagged conflicts with what the simulator really did.

Ground truth = the simulator's own log of waits (``SimulationEngine.wait_events``): every time a train was
refused a block because another train held it (waits caused by a closed block are not counted). A long wait
can be caused by several trains one after the other; all of them are recorded.

The scenario runs with NO control, so the detector cannot change what it is trying to predict.

    recall    = real waits that the detector had flagged at least ``MIN_LEAD_MIN`` minutes before they
                started (and at most ``lookahead`` minutes before).
    precision = flagged conflict episodes (the same conflict flagged on consecutive ticks) that came true.

A flag MATCHES a real wait when all three hold: the same two trains, the same line segment (station to
station), and the flagged time is within ``TIME_TOLERANCE_MIN`` minutes of when the wait really started.
Matching on the pair alone would be far too generous: two trains close together stay flagged for hours.

All data is synthetic.
"""

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.ml.predict import DelayPredictor
from app.models.network import Network
from app.optimizer.closed_loop import predicted_snapshot
from app.optimizer.conflicts import ConflictDetector
from app.simulation.runtime import WaitEvent
from app.simulation.scenario import Scenario

MIN_LEAD_MIN = 5  # "in advance" means at least this many minutes before the wait starts
TIME_TOLERANCE_MIN = 10  # flagged time and real start may differ by this much


@dataclass(frozen=True)
class Flag:
    """One conflict as flagged at one tick."""

    tick: int  # when it was flagged
    time_min: int  # when the detector expected it to happen
    segment: str  # station-to-station segment, e.g. "BHP-GNK"


@dataclass(frozen=True)
class Episode:
    """A conflict flagged on consecutive ticks."""

    flags: list[Flag]


@dataclass(frozen=True)
class Observations:
    """What one scenario run produced: real waits and, per lookahead, the flagged episodes."""

    events: list[WaitEvent]
    end_tick: int
    seen: dict[int, dict[str, list[Flag]]]  # lookahead -> conflict id -> every time it was flagged


@dataclass(frozen=True)
class ValidationRow:
    """Recall and precision for one lookahead and one minimum wait length."""

    lookahead_min: int
    min_wait_min: int
    events: int
    events_flagged: int
    episodes: int
    episodes_real: int
    median_lead_min: float | None

    @property
    def recall(self) -> float:
        """Share of real waits flagged in advance (1.0 when there were none)."""
        return self.events_flagged / self.events if self.events else 1.0

    @property
    def precision(self) -> float:
        """Share of flagged episodes that really happened (1.0 when nothing was flagged)."""
        return self.episodes_real / self.episodes if self.episodes else 1.0


def segment_of(block_id: str) -> str:
    """Return the station pair of a block id ("BHP-GNK-2" -> "BHP-GNK")."""
    return block_id.rsplit("-", 1)[0]


def pair_id(a: str, b: str) -> str:
    """Conflict id of a pair of trains (same format the detector uses)."""
    return f"c-{'-'.join(sorted((a, b)))}"


def observe(
    scenario: Scenario,
    network: Network,
    detectors: dict[int, ConflictDetector],
    predictor: DelayPredictor | None = None,
) -> Observations:
    """Run the scenario with no control; at every tick record what each detector flags."""
    engine = scenario.build(network)
    seen: dict[int, dict[str, list[Flag]]] = {h: defaultdict(list) for h in detectors}
    while not engine.is_done():
        state = predicted_snapshot(engine, network, predictor)
        for h, detector in detectors.items():
            for conflict in detector.detect(state):
                seen[h][conflict.id].append(
                    Flag(state.tick, conflict.time_min, segment_of(conflict.location))
                )
        engine.step()
    real = [e for e in engine.wait_events if e.blockers]
    return Observations(real, engine.tick, {h: dict(v) for h, v in seen.items()})


def episodes(flags_by_conflict: dict[str, list[Flag]]) -> list[tuple[str, Episode]]:
    """Group the flags of each conflict into runs of consecutive ticks."""
    result: list[tuple[str, Episode]] = []
    for conflict_id, flags in flags_by_conflict.items():
        run = [flags[0]]
        for flag in flags[1:]:
            if flag.tick != run[-1].tick + 1:
                result.append((conflict_id, Episode(run)))
                run = []
            run.append(flag)
        result.append((conflict_id, Episode(run)))
    return result


def _duration(event: WaitEvent, end_tick: int) -> int:
    return (event.end if event.end is not None else end_tick) - event.start


def _matches(flag: Flag, event: WaitEvent) -> bool:
    return (
        flag.segment == segment_of(event.block_id) and abs(flag.time_min - event.start) <= TIME_TOLERANCE_MIN
    )


def score(observations: Sequence[Observations], lookahead: int, min_wait: int) -> ValidationRow:
    """Compute recall and precision over several runs."""
    events = flagged = n_episodes = real = 0
    leads: list[int] = []
    for obs in observations:
        waits = [e for e in obs.events if _duration(e, obs.end_tick) >= min_wait]
        by_pair: dict[str, list[WaitEvent]] = defaultdict(list)
        for e in waits:
            for blocker in e.blockers:
                by_pair[pair_id(e.train_id, blocker)].append(e)
        seen = obs.seen[lookahead]
        for e in waits:
            early = [
                f.tick
                for blocker in e.blockers
                for f in seen.get(pair_id(e.train_id, blocker), [])
                if e.start - lookahead <= f.tick <= e.start - MIN_LEAD_MIN and _matches(f, e)
            ]
            events += 1
            if early:
                flagged += 1
                leads.append(e.start - min(early))
        for conflict_id, episode in episodes(seen):
            n_episodes += 1
            if any(
                f.tick <= e.start and _matches(f, e)
                for f in episode.flags
                for e in by_pair.get(conflict_id, [])
            ):
                real += 1
    median = statistics.median(leads) if leads else None
    return ValidationRow(lookahead, min_wait, events, flagged, n_episodes, real, median)
