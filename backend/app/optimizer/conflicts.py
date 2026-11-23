"""Conflict detector: looks a few minutes ahead and flags trains that will fight for the same track.

How it works (three steps, no magic):
    1. TIMELINE. For every train, list the blocks it will use in the next ``lookahead_min`` minutes and
       when it enters and leaves each one. The times come from the snapshot: the predicted arrival at
       each upcoming station (from the ML delay model, or from "the delay stays what it is" when there is
       no model; the snapshot already contains whichever it is). Between two stations the train spends
       its running time spread over the blocks in proportion to their free-running time. A train that
       halts at a station never leaves before its timetable allows (scheduled arrival at the next
       station minus the planned running time).
    2. COMPARE. Two trains using the same track resource at overlapping times means the one arriving
       second has to wait. Only waits of at least ``min_wait_min`` count.
    3. CLASSIFY. Opposing trains on a single-line stretch are a ``single_line_meeting``; a faster train
       arriving behind a slower one in the same direction is ``overtaking`` (nobody can pass between
       stations); anything else on the same block (e.g. two lines merging at a junction) is ``block``.

Severity = predicted wait (minutes) x highest priority involved (premium 4 ... freight 1):
    < 6 low, < 15 medium, < 30 high, otherwise critical.

Known simplifications: disruptions are not modelled separately (the predicted arrival times already
contain their effect); trains are points; stations have no platform limit, so there is no platform conflict.

All data is synthetic.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from itertools import combinations

from app.models.network import Block, Direction, LineType, Network
from app.models.schemas import (
    Conflict,
    ConflictKind,
    Severity,
    StateSnapshot,
    StationStop,
    TrainState,
    TrainStatus,
)
from app.models.train import TrainCategory, get_train_type, stops_at
from app.simulation.timetable import RUNNING_MARGIN

DEFAULT_LOOKAHEAD_MIN = 60
DEFAULT_MIN_WAIT_MIN = 1.0
SEVERITY_LIMITS = ((6.0, Severity.LOW), (15.0, Severity.MEDIUM), (30.0, Severity.HIGH))


@dataclass(frozen=True)
class Visit:
    """One train using one block: from ``enter`` to ``exit`` (simulation minutes)."""

    train_id: str
    block: Block
    direction: Direction
    enter: float
    exit: float
    speed_kmph: float  # free-running speed of this train on this block
    hop_start: float  # time the train leaves ``hop_from`` (or now, if it already has)
    hop_from: str  # station the train leaves before this block
    hop_to: str  # station at the end of the hop
    left_station: bool  # True if the train has already left ``hop_from`` (cannot be held there any more)

    @property
    def resource(self) -> str:
        """Key of the physical track resource (shared by both directions on a single line)."""
        return self.block.resource_key(self.direction)


@dataclass(frozen=True)
class Contention:
    """A detected conflict plus the details strategies need (who arrives first, where to hold)."""

    conflict: Conflict
    leader: Visit  # the train that reaches the resource first
    follower: Visit  # the train that would have to wait
    wait_min: float  # how long the follower waits when it first reaches the contested track
    loss_min: (
        float  # total delay it would suffer (bigger than ``wait_min`` when it is stuck behind a slower train)
    )


@dataclass(frozen=True)
class _Candidate:
    leader: Visit
    follower: Visit
    wait_min: float
    loss_min: float
    kind: ConflictKind


@dataclass(frozen=True)
class _Hop:
    """Part of a train's journey: from a station to the next one."""

    start_station: str
    end: StationStop
    blocks: list[tuple[Block, Direction]]
    first_fraction: float  # share of the first block still ahead (1 = all of it)
    left_station: bool


def _free_speed(category: TrainCategory, block: Block) -> float:
    return float(min(block.speed_limit_kmph, get_train_type(category).max_speed_kmph))


class ConflictDetector:
    """Detects upcoming conflicts in a ``StateSnapshot``."""

    def __init__(
        self,
        network: Network,
        lookahead_min: int = DEFAULT_LOOKAHEAD_MIN,
        min_wait_min: float = DEFAULT_MIN_WAIT_MIN,
    ) -> None:
        if lookahead_min <= 0:
            raise ValueError("lookahead_min must be positive")
        self.network = network
        self.lookahead_min = lookahead_min
        self.min_wait_min = min_wait_min
        self._blocks = {b.id: b for b in network.blocks}

    # ---- public ------------------------------------------------------------
    def detect(self, state: StateSnapshot) -> list[Conflict]:
        """Return the conflicts expected within the look-ahead, earliest first."""
        return [c.conflict for c in self.find(state)]

    def find(self, state: StateSnapshot) -> list[Contention]:
        """Like ``detect`` but with the details (leader, follower, wait) that strategies need."""
        timelines = self.timelines(state)
        trains = {t.id: t for t in state.trains}
        best: dict[tuple[str, str], _Candidate] = {}
        for cand in [*self._block_candidates(timelines), *self._meeting_candidates(timelines)]:
            ids = sorted((cand.leader.train_id, cand.follower.train_id))
            pair = (ids[0], ids[1])
            old = best.get(pair)
            if old is None or cand.follower.enter < old.follower.enter:
                best[pair] = cand
        found = [self._contention(state, trains, cand) for cand in best.values()]
        return sorted(found, key=lambda c: (c.conflict.time_min, c.conflict.id))

    def timelines(self, state: StateSnapshot) -> dict[str, list[Visit]]:
        """Return, per train, the blocks it will use in the look-ahead window."""
        return {t.id: self._timeline(t, state.tick) for t in state.trains}

    # ---- step 1: timelines ------------------------------------------------------
    def _timeline(self, train: TrainState, now: int) -> list[Visit]:
        if train.status is TrainStatus.FINISHED or not train.next_stations:
            return []
        halt = get_train_type(train.category).halt_minutes
        limit = now + self.lookahead_min
        visits: list[Visit] = []
        clock = float(train.next_stations[0].predicted_min)  # only used before the train has started
        halts_here = self._halts_at_start(train)
        for index, hop in enumerate(self._hops(train)):
            speeds = [_free_speed(train.category, b) for b, _ in hop.blocks]
            minutes = [
                b.length_km * (hop.first_fraction if k == 0 else 1.0) / speeds[k] * 60.0
                for k, (b, _) in enumerate(hop.blocks)
            ]
            free = sum(minutes)
            start = self._hop_start(train, index, hop, free, clock, now)
            if halts_here and not hop.left_station:  # waits for the timetable, never leaves early
                start = max(start, hop.end.scheduled_min - RUNNING_MARGIN * free)
            if start > limit:
                break
            window = max(hop.end.predicted_min - start, free)  # never faster than free running
            at = start
            for (block, direction), speed, share in zip(hop.blocks, speeds, minutes, strict=True):
                length = window * share / free if free > 0 else 0.0
                visits.append(
                    Visit(
                        train.id,
                        block,
                        direction,
                        at,
                        at + length,
                        speed,
                        start,
                        hop.start_station,
                        hop.end.station,
                        hop.left_station,
                    )
                )
                at += length
            clock = start + window + (halt if hop.end.will_stop else 0)
            halts_here = hop.end.will_stop
        return [v for v in visits if v.enter <= limit]

    def _halts_at_start(self, train: TrainState) -> bool:
        """Return True if the station the train is at (or about to start from) is a timetable halt for it."""
        position = train.position
        if position is None:
            return False  # not started: the origin time is already the scheduled departure
        if position.at_station is None:
            return False
        station = self.network.station(position.at_station)
        return stops_at(get_train_type(train.category), station.size)

    @staticmethod
    def _hop_start(train: TrainState, index: int, hop: _Hop, free: float, clock: float, now: int) -> float:
        """Time the train leaves the hop's first station (or, if already between stations, now)."""
        if index > 0:
            return clock
        if hop.left_station:
            return float(now)
        if train.position is None:  # not started: leaves its origin at the scheduled time
            return max(float(now), clock)
        return max(float(now), hop.end.predicted_min - free)

    def _hops(self, train: TrainState) -> list[_Hop]:
        """Split the train's remaining journey into station-to-station hops."""
        stops = list(train.next_stations)
        position = train.position
        skip, fraction, left = 0, 1.0, False
        if position is None:  # not started: the first "next station" is the origin
            first_station, stops = stops[0].station, stops[1:]
        elif position.at_station is not None:
            first_station = position.at_station
        else:
            assert position.block_id is not None and position.direction is not None  # noqa: S101
            block = self._blocks[position.block_id]
            first_station, end = block.from_code, block.to_code
            if position.direction is Direction.REVERSE:
                first_station, end = end, first_station
            if stops[0].station != end:
                return []
            path = self.network.route_blocks([first_station, end])
            skip = next(k for k, (b, d) in enumerate(path) if b.id == block.id and d is position.direction)
            fraction = max(0.0, 1.0 - position.offset_km / block.length_km)
            left = True
        hops: list[_Hop] = []
        previous = first_station
        for k, stop in enumerate(stops):
            blocks = self.network.route_blocks([previous, stop.station])[skip if k == 0 else 0 :]
            hops.append(_Hop(previous, stop, blocks, fraction if k == 0 else 1.0, left and k == 0))
            previous = stop.station
        return hops

    # ---- step 2: compare ---------------------------------------------------------
    def _block_candidates(self, timelines: dict[str, list[Visit]]) -> list[_Candidate]:
        """Find trains in the same direction on the same block at overlapping times."""
        by_resource: dict[str, list[Visit]] = defaultdict(list)
        for visits in timelines.values():
            for visit in visits:
                by_resource[visit.resource].append(visit)
        found: list[_Candidate] = []
        for visits in by_resource.values():
            for a, b in combinations(sorted(visits, key=lambda v: (v.enter, v.train_id)), 2):
                wait = a.exit - b.enter
                if a.train_id == b.train_id or a.direction is not b.direction or wait < self.min_wait_min:
                    continue
                if b.speed_kmph > a.speed_kmph:
                    loss = max(wait, self._catch_up_loss(a, b, timelines))
                    found.append(_Candidate(a, b, wait, loss, ConflictKind.OVERTAKING))
                else:
                    found.append(_Candidate(a, b, wait, wait, ConflictKind.BLOCK))
        return found

    @staticmethod
    def _catch_up_loss(leader: Visit, follower: Visit, timelines: dict[str, list[Visit]]) -> float:
        """Return how much later the faster train leaves the blocks it shares with the slower one."""
        leader_exit = {
            v.block.id: v.exit for v in timelines[leader.train_id] if v.direction is leader.direction
        }
        losses = [
            leader_exit[v.block.id] - v.exit
            for v in timelines[follower.train_id]
            if v.block.id in leader_exit and v.enter >= follower.enter
        ]
        return max(losses, default=0.0)

    def _meeting_candidates(self, timelines: dict[str, list[Visit]]) -> list[_Candidate]:
        """Opposing trains whose time on one single-line segment overlaps (the engine never allows that)."""
        by_segment: dict[tuple[str, str], list[Visit]] = defaultdict(list)
        for visits in timelines.values():
            for visit in self._segment_visits(visits):
                by_segment[(visit.block.from_code, visit.block.to_code)].append(visit)
        found: list[_Candidate] = []
        for visits in by_segment.values():
            for a, b in combinations(sorted(visits, key=lambda v: (v.enter, v.train_id)), 2):
                wait = a.exit - b.enter
                if a.direction is not b.direction and wait >= self.min_wait_min:
                    found.append(_Candidate(a, b, wait, wait, ConflictKind.SINGLE_LINE_MEETING))
        return found

    @staticmethod
    def _segment_visits(visits: list[Visit]) -> list[Visit]:
        """Merge a train's consecutive blocks on one single-line segment into one visit."""
        merged: dict[tuple[str, str, str], Visit] = {}
        for v in visits:
            if v.block.line is not LineType.SINGLE:
                continue
            key = (v.block.from_code, v.block.to_code, v.direction.value)
            old = merged.get(key)
            if old is None:
                merged[key] = v
            else:
                merged[key] = Visit(
                    v.train_id,
                    old.block,
                    v.direction,
                    old.enter,
                    v.exit,
                    old.speed_kmph,
                    old.hop_start,
                    old.hop_from,
                    old.hop_to,
                    old.left_station,
                )
        return list(merged.values())

    # ---- step 3: describe -----------------------------------------------------------
    def _contention(
        self, state: StateSnapshot, trains: dict[str, TrainState], cand: _Candidate
    ) -> Contention:
        first, second = trains[cand.leader.train_id], trains[cand.follower.train_id]
        block = cand.follower.block
        time_min = math.ceil(cand.follower.enter)
        clock = (state.sim_time + timedelta(minutes=time_min - state.tick)).strftime("%H:%M")
        where = f"{block.from_code}-{block.to_code}"
        text = {
            ConflictKind.SINGLE_LINE_MEETING: f"{first.name} and {second.name} run in opposite directions "
            f"on the single line {where} at {clock}.",
            ConflictKind.OVERTAKING: f"Faster {second.name} catches slower {first.name} on {where} around "
            f"{clock}; there is no overtaking between stations.",
            ConflictKind.BLOCK: f"{first.name} and {second.name} both need block {block.id} around {clock}.",
        }[cand.kind]
        meeting = cand.kind is ConflictKind.SINGLE_LINE_MEETING
        conflict = Conflict(
            id=f"c-{'-'.join(sorted((first.id, second.id)))}",
            kind=cand.kind,
            severity=self._severity(cand.loss_min, max(first.priority, second.priority)),
            train_ids=[first.id, second.id],
            location=f"{where}-1" if meeting else block.id,
            time_min=time_min,
            description=f"{text} {second.name} would lose about {cand.loss_min:.0f} min.",
        )
        return Contention(conflict, cand.leader, cand.follower, cand.wait_min, cand.loss_min)

    @staticmethod
    def _severity(wait_min: float, top_priority: int) -> Severity:
        score = wait_min * top_priority
        return next((level for limit, level in SEVERITY_LIMITS if score < limit), Severity.CRITICAL)
