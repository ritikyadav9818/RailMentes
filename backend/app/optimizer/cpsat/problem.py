"""The scheduling problem the CP-SAT optimizer solves, and how it is built from a snapshot.

Words used here:
    * HOP: the part of a train's journey from one station to the next. A train can be held at the station
      where a hop starts (if it has not left yet).
    * VISIT: one train using one track resource (a block, or a whole single-line segment) from ``enter`` to
      ``exit`` minutes. Times come from the conflict detector's timelines, i.e. from the same predictions
      every other strategy sees.
    * GROUP: two trains that use a shared resource within the same pair of hops. Either the LEADER (the
      train that reaches it first by the predictions) goes first, or the FOLLOWER does. The second choice
      is only possible if the leader is held at a station before the resource.

The build step turns the detector's timelines into small independent ``Component`` problems: trains that
are tied together by groups are solved together, everything else is left alone. That keeps every model tiny.

All data is synthetic.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from app.models.network import Direction, LineType
from app.models.schemas import StateSnapshot, TrainState
from app.optimizer.conflicts import Visit


@dataclass(frozen=True)
class Params:
    """Tunable numbers of the optimizer (defaults are the tuned values, see docs/RESULTS.md section 3)."""

    lookahead_min: int = 60  # how far ahead the detector (and so the model) looks
    headway_min: int = 1  # minimum gap between two trains on one resource
    max_hold_min: int = 20  # largest hold_minutes of one action
    decision_horizon_min: int = 10  # only act on trains that leave their station within this time
    max_yield_wait_min: int = 15  # a precedence is only used if the winner arrives within this time
    pair_window_min: int = 45  # trains farther apart than this on a resource are not considered together
    wait_cap_min: int = 120  # largest passive wait the model allows (keeps the model bounded)
    action_penalty: float = 25.0  # cost of one action, in priority-weighted delay minutes
    hold_penalty: float = 0.1  # cost of one extra hold minute, in priority-weighted delay minutes
    time_limit_s: float = 2.0  # wall-clock limit of one solve (backstop)
    det_time_limit: float = 0.5  # deterministic-time limit of one solve (the limit that normally applies)


@dataclass(frozen=True)
class PTrain:
    """A train in the model."""

    id: str
    priority: int
    hold_caps: tuple[int, ...]  # per hop: most extra minutes the train may be held (0 = cannot be held)
    final_delay: int  # predicted delay at the end of the model window (min)


@dataclass(frozen=True)
class PVisit:
    """One train on one resource."""

    train: int  # index into Problem.trains
    hop: int
    resource: str
    enter: int
    exit: int


@dataclass(frozen=True)
class PGroup:
    """Leader and follower on shared resources; ``pairs`` lists (leader visit, follower visit) indexes."""

    leader: int  # train index
    follower: int
    leader_hop: int
    pairs: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Problem:
    """Everything the solver needs (plain numbers only, hashable so solutions can be cached)."""

    trains: tuple[PTrain, ...]
    visits: tuple[PVisit, ...]
    groups: tuple[PGroup, ...]
    headway: int


@dataclass(frozen=True)
class HopInfo:
    """What the action builder needs to know about a hop (not part of the maths)."""

    station: str  # where the hop starts (where a hold would happen)
    depart: int  # planned departure from that station (predicted)
    arrival: int | None  # predicted arrival at that station (None = unknown, so no hold possible)
    left: bool  # the train has already left the station

    @property
    def dwell(self) -> int:
        """Minutes the train would spend at the station anyway."""
        return 0 if self.arrival is None else max(0, self.depart - self.arrival)


@dataclass(frozen=True)
class Component:
    """One independent problem, with the extra information to turn its answer into actions."""

    problem: Problem
    hops: dict[tuple[int, int], HopInfo]  # (train index, hop) -> info


@dataclass(frozen=True)
class _Raw:
    """A visit before indexes are assigned."""

    train_id: str
    hop: int
    resource: str
    enter: int
    exit: int
    direction: Direction


def build_components(
    state: StateSnapshot,
    timelines: dict[str, list[Visit]],
    seed_ids: Iterable[str],
    params: Params,
) -> list[Component]:
    """Return the independent problems around the trains in ``seed_ids`` (trains in detected conflicts)."""
    seeds = set(seed_ids)
    trains = {t.id: t for t in state.trains}
    hop_of = {tid: _number_hops(visits) for tid, visits in timelines.items()}
    raws = [r for tid, visits in timelines.items() for r in _raws(tid, visits, hop_of[tid])]
    groups = _find_groups(raws, seeds, params)
    parent = {tid: tid for key in groups for tid in key[:2]}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, *_ in groups:
        parent[find(a)] = find(b)
    members: dict[str, list[str]] = defaultdict(list)
    for tid in parent:
        members[find(tid)].append(tid)
    components = []
    for ids in sorted(members.values(), key=min):
        components.append(_component(state, trains, timelines, hop_of, sorted(ids), groups, params))
    return components


def _number_hops(visits: list[Visit]) -> list[int]:
    """Return the hop index (0, 1, ...) of each visit; a new hop starts when the start station changes."""
    numbers, last, hop = [], None, -1
    for v in visits:
        if v.hop_from != last:
            hop, last = hop + 1, v.hop_from
        numbers.append(hop)
    return numbers


def _raws(train_id: str, visits: list[Visit], hops: list[int]) -> list[_Raw]:
    """Return the block visits plus one merged visit per single-line segment (to forbid head-on meetings)."""
    raws = [
        _Raw(train_id, h, v.resource, round(v.enter), round(v.exit), v.direction)
        for v, h in zip(visits, hops, strict=True)
    ]
    merged: dict[tuple[int, str, str], list[Visit]] = defaultdict(list)
    for v, h in zip(visits, hops, strict=True):
        if v.block.line is LineType.SINGLE:
            merged[(h, v.block.from_code, v.block.to_code)].append(v)
    for (h, a, b), vs in merged.items():
        raws.append(
            _Raw(
                train_id,
                h,
                f"seg:{a}-{b}",
                round(min(v.enter for v in vs)),
                round(max(v.exit for v in vs)),
                vs[0].direction,
            )
        )
    return raws


_GroupKey = tuple[str, str, int, int]  # (train a, train b, hop of a, hop of b) with a < b


def _find_groups(
    raws: list[_Raw], seeds: set[str], params: Params
) -> dict[_GroupKey, list[tuple[_Raw, _Raw]]]:
    """Collect pairs of visits of different trains that share a resource close in time (>= 1 seed train)."""
    by_resource: dict[str, list[_Raw]] = defaultdict(list)
    for r in raws:
        by_resource[r.resource].append(r)
    groups: dict[_GroupKey, list[tuple[_Raw, _Raw]]] = defaultdict(list)
    for resource, visits in by_resource.items():
        for a, b in combinations(sorted(visits, key=lambda r: (r.train_id, r.hop, r.enter)), 2):
            if a.train_id == b.train_id or not ({a.train_id, b.train_id} & seeds):
                continue
            if resource.startswith("seg:") and a.direction is b.direction:
                continue  # following each other through a segment is fine, only head-on is forbidden
            if max(a.enter, b.enter) - min(a.exit, b.exit) > params.pair_window_min:
                continue
            groups[(a.train_id, b.train_id, a.hop, b.hop)].append((a, b))
    return groups


def _component(
    state: StateSnapshot,
    trains: dict[str, TrainState],
    timelines: dict[str, list[Visit]],
    hop_of: dict[str, list[int]],
    ids: list[str],
    groups: dict[_GroupKey, list[tuple[_Raw, _Raw]]],
    params: Params,
) -> Component:
    index = {tid: k for k, tid in enumerate(ids)}
    hop_infos: dict[tuple[int, int], HopInfo] = {}
    ptrains = []
    for tid in ids:
        infos = _hop_infos(state, trains[tid], timelines[tid], hop_of[tid])
        hop_infos.update({(index[tid], h): info for h, info in enumerate(infos)})
        caps = tuple(_cap(info, params) for info in infos)
        ptrains.append(PTrain(tid, trains[tid].priority, caps, _final_delay(trains[tid], timelines[tid])))
    visits: dict[tuple[int, int, str, int, int], int] = {}

    def visit_index(r: _Raw) -> int:
        key = (index[r.train_id], r.hop, r.resource, r.enter, r.exit)
        return visits.setdefault(key, len(visits))

    pgroups = []
    for (a, b, hop_a, hop_b), pairs in sorted(groups.items()):
        if a not in index or b not in index:
            continue
        lead_is_a = _leads(a, b, pairs)
        leader, follower = (a, b) if lead_is_a else (b, a)
        ordered = [(x, y) if lead_is_a else (y, x) for x, y in pairs]
        pgroups.append(
            PGroup(
                index[leader],
                index[follower],
                hop_a if lead_is_a else hop_b,
                tuple(sorted({(visit_index(x), visit_index(y)) for x, y in ordered})),
            )
        )
    pvisits = tuple(
        PVisit(train, hop, resource, enter, exit_)
        for (train, hop, resource, enter, exit_), _ in sorted(visits.items(), key=lambda kv: kv[1])
    )
    return Component(Problem(tuple(ptrains), pvisits, tuple(pgroups), params.headway_min), hop_infos)


def _leads(a: str, b: str, pairs: list[tuple[_Raw, _Raw]]) -> bool:
    """Return True if train ``a`` reaches the shared resources first.

    Ties on the entry time go to the train that leaves first, then to the smaller id. (Without the exit
    tie-break, three trains entering together could be ordered in a circle, which no schedule satisfies.)
    """
    key_a = (min(x.enter for x, _ in pairs), min(x.exit for x, _ in pairs), a)
    key_b = (min(y.enter for _, y in pairs), min(y.exit for _, y in pairs), b)
    return key_a <= key_b


def _hop_infos(
    state: StateSnapshot, train: TrainState, visits: list[Visit], hops: list[int]
) -> list[HopInfo]:
    infos: list[HopInfo] = []
    for v, h in zip(visits, hops, strict=True):
        if h < len(infos):
            continue
        here = train.position is not None and train.position.at_station == v.hop_from
        stop = next((s for s in train.next_stations if s.station == v.hop_from), None)
        arrival = state.tick if here else (stop.predicted_min if stop is not None else None)
        infos.append(HopInfo(v.hop_from, round(v.hop_start), arrival, v.left_station))
    return infos


def _cap(info: HopInfo, params: Params) -> int:
    """Most extra hold minutes allowed: the action's total hold (dwell + extra) must stay <= max_hold_min."""
    if info.left or info.arrival is None:
        return 0
    return max(0, params.max_hold_min - info.dwell)


def _final_delay(train: TrainState, visits: list[Visit]) -> int:
    """Predicted delay at the last station of the window (falls back to the current delay)."""
    end = visits[-1].hop_to
    stop = next((s for s in train.next_stations if s.station == end), None)
    return round(stop.predicted_min - stop.scheduled_min) if stop is not None else round(train.delay_min)
