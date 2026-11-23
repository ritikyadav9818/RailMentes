"""The ONE place where model features are computed.

``build_features`` turns a ``StateSnapshot`` plus one train into a flat feature row. The data
generator (training) and the live API (prediction) both call this exact function, so there is no
train/serve skew. It looks only at what a controller could see at that instant: the snapshot, the
static network and the delay the train had when it reached the station it last visited. It never
reads future information (planned-but-inactive disruptions are not in a snapshot).

All data is synthetic.
"""

import functools
from typing import Final

from app.models.network import Block, Direction, LineType, Network
from app.models.schemas import DisruptionKind, StateSnapshot, StationStop, TrainState, TrainStatus
from app.simulation.disruptions import affects_block

LOOKAHEAD_BLOCKS: Final = 6  # "the next few blocks" used for congestion and disruption features
STATIONS_AHEAD: Final = 3  # how many upcoming stations get a schedule/distance feature and a target

FEATURE_COLUMNS: Final = (
    # the train
    "train_category",  # premium / express / passenger / freight
    "priority",  # 4 (premium) ... 1 (freight)
    "speed_kmph",  # current speed
    # the clock
    "hour",  # hour of day, 0-23
    "day_of_week",  # 0 = Monday ... 6 = Sunday
    "month",  # 1-12
    # delay so far
    "delay_now",  # minutes late right now (negative = early)
    "delay_last_arrival",  # minutes late when it reached the station it last visited
    # what is ahead
    "stations_ahead",  # how many upcoming stations are known (1-4)
    "next_will_stop",  # 1 if the next station is a halt
    "sched_to_s1",  # scheduled minutes from now until arrival at the next station
    "sched_to_s2",  # ... second next station (missing near the end of the route)
    "sched_to_s3",  # ... third next station
    "dist_to_s1_km",  # kilometres to the next station
    "dist_to_s2_km",
    "dist_to_s3_km",
    # congestion and track
    "trains_in_next_blocks",  # other trains in the next few blocks
    "opposing_trains_in_next_blocks",  # of those, opposing trains on single-line blocks
    "next_hop_single_line",  # 1 if the stretch to the next station has single-line blocks
    "single_line_blocks_ahead",  # single-line blocks among the next few
    # active disruptions touching the next few blocks
    "fog_active",  # fog (mostly Nov-Feb)
    "weather_slowdown_active",  # heavy rain or similar
    "signal_failure_active",
    "closure_active",
    "min_speed_factor",  # slowest active speed factor there (1 = none, 0 = closed)
)
OPTIONAL_FEATURES: Final = ("sched_to_s2", "sched_to_s3", "dist_to_s2_km", "dist_to_s3_km")
REQUIRED_FEATURES: Final = tuple(c for c in FEATURE_COLUMNS if c not in OPTIONAL_FEATURES)
TARGET_COLUMNS: Final = tuple(f"target_delay_{k}" for k in range(1, STATIONS_AHEAD + 1))
META_COLUMNS: Final = (
    "scenario_id",
    "day",
    "seed",
    "intensity",
    "train_id",
    "station",
    "station_idx",
    "tick",
)
ALL_COLUMNS: Final = META_COLUMNS + FEATURE_COLUMNS + TARGET_COLUMNS

FeatureRow = dict[str, float | int | str | None]
Path = list[tuple[Block, Direction]]

_CLOSURE_KINDS = frozenset({DisruptionKind.BLOCK_CLOSURE, DisruptionKind.MAINTENANCE})


@functools.cache
def _block_index(network: Network) -> dict[str, Block]:
    return {b.id: b for b in network.blocks}


@functools.cache
def _hop(network: Network, start: str, end: str) -> tuple[tuple[Block, Direction], ...]:
    """Blocks between two adjacent stations, in travel order."""
    return tuple(network.route_blocks([start, end]))


def is_predictable(train: TrainState) -> bool:
    """Return True if the train is on the line and has stations ahead."""
    on_line = train.status not in (TrainStatus.NOT_STARTED, TrainStatus.FINISHED)
    return on_line and train.position is not None and bool(train.next_stations)


def _first_hop(network: Network, train: TrainState) -> tuple[Path, float]:
    """Return the blocks still to cross before the next station, and the km already done in the first."""
    position = train.position
    assert position is not None  # checked by the caller
    stops = train.next_stations
    if position.block_id is None:
        assert position.at_station is not None
        return list(_hop(network, position.at_station, stops[0].station)), 0.0
    block = _block_index(network)[position.block_id]
    start, end = (
        (block.from_code, block.to_code)
        if position.direction is Direction.FORWARD
        else (block.to_code, block.from_code)
    )
    if end != stops[0].station:
        raise ValueError(f"train {train.id} is in {block.id} but its next station is {stops[0].station}")
    hop = list(_hop(network, start, end))
    index = next(i for i, (b, _) in enumerate(hop) if b.id == block.id)
    return hop[index:], position.offset_km


def _path_ahead(network: Network, train: TrainState) -> tuple[Path, list[float], int]:
    """Return the blocks ahead, the km to each upcoming station, and how many blocks lead to the next one."""
    first, done_km = _first_hop(network, train)
    stops = train.next_stations
    blocks: Path = list(first)
    distances = [sum(b.length_km for b, _ in first) - done_km]
    for here, there in zip(stops, stops[1:], strict=False):
        hop = list(_hop(network, here.station, there.station))
        blocks += hop
        distances.append(distances[-1] + sum(b.length_km for b, _ in hop))
    return blocks, distances, len(first)


def _sched_to(stops: list[StationStop], k: int, tick: int) -> int | None:
    return stops[k].scheduled_min - tick if k < len(stops) else None


def build_features(
    snapshot: StateSnapshot, train: TrainState, network: Network, last_arrival_delay: float
) -> FeatureRow:
    """Build the feature row for ``train`` from what is visible in ``snapshot``.

    Args:
        snapshot: The state at one instant.
        train: One of ``snapshot.trains`` that is on the line (see ``is_predictable``).
        network: The static network.
        last_arrival_delay: Delay (min) the train had when it reached the station it last
            visited. Not part of the snapshot, so the caller reads it from the engine.

    Raises:
        ValueError: if the train is not on the line or has no stations ahead.

    """
    if not is_predictable(train):
        raise ValueError(f"train {train.id} is not on the line")
    stops = train.next_stations
    blocks, distances, first_len = _path_ahead(network, train)
    window = blocks[:LOOKAHEAD_BLOCKS]
    window_ids = {b.id for b, _ in window}
    single_ids = {b.id: d for b, d in window if b.line is LineType.SINGLE}

    others = [t.position for t in snapshot.trains if t.id != train.id and t.position and t.position.block_id]
    in_window = [p for p in others if p.block_id in window_ids]
    opposing = [
        p for p in in_window if p.block_id in single_ids and p.direction is not single_ids[p.block_id]
    ]

    active = [d for d in snapshot.disruptions if any(affects_block(d, b) for b, _ in window)]
    factors = [d.speed_factor for d in active]
    when = snapshot.sim_time

    def dist(k: int) -> float | None:
        return round(distances[k], 3) if k < len(distances) else None

    return {
        "train_category": train.category.value,
        "priority": train.priority,
        "speed_kmph": train.speed_kmph,
        "hour": when.hour,
        "day_of_week": when.weekday(),
        "month": when.month,
        "delay_now": train.delay_min,
        "delay_last_arrival": last_arrival_delay,
        "stations_ahead": len(stops),
        "next_will_stop": int(stops[0].will_stop),
        "sched_to_s1": _sched_to(stops, 0, snapshot.tick),
        "sched_to_s2": _sched_to(stops, 1, snapshot.tick),
        "sched_to_s3": _sched_to(stops, 2, snapshot.tick),
        "dist_to_s1_km": dist(0),
        "dist_to_s2_km": dist(1),
        "dist_to_s3_km": dist(2),
        "trains_in_next_blocks": len(in_window),
        "opposing_trains_in_next_blocks": len(opposing),
        "next_hop_single_line": int(any(b.line is LineType.SINGLE for b, _ in blocks[:first_len])),
        "single_line_blocks_ahead": len(single_ids),
        "fog_active": int(any(d.kind is DisruptionKind.FOG for d in active)),
        "weather_slowdown_active": int(any(d.kind is DisruptionKind.WEATHER_SLOWDOWN for d in active)),
        "signal_failure_active": int(any(d.kind is DisruptionKind.SIGNAL_FAILURE for d in active)),
        "closure_active": int(any(d.kind in _CLOSURE_KINDS for d in active)),
        "min_speed_factor": min(factors, default=1.0),
    }
