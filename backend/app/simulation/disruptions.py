"""Disruptions: what can go wrong, how it affects blocks, and how random ones are generated.

Meaning of the shared ``Disruption`` schema fields (see ``docs/API.md``):
    * FOG / WEATHER_SLOWDOWN: ``speed_factor`` (> 0) multiplies train speed on the target
      blocks while ``start_tick <= tick < end_tick``.
    * SIGNAL_FAILURE: same, but factor 0 means the block cannot be entered at all.
    * BLOCK_CLOSURE / MAINTENANCE: factor 0; the block cannot be entered. A train that is
      already inside crawls out (the engine uses a small crawl speed).
    * LATE_DEPARTURE: ``target_ids = [train_id]``; ``end_tick - start_tick`` is how many
      minutes late the train leaves its origin (the window starts at its scheduled departure).
    * ``target_ids`` may hold block ids or station codes (a station affects the blocks that
      touch it). An empty list means the whole network.

Random disruptions use the engine's seeded RNG, so the same seed always gives the same day.
Durations are capped so every train can still finish.
"""

import random
from dataclasses import dataclass
from enum import StrEnum

from app.models.network import Block, Network
from app.models.schemas import Disruption, DisruptionKind
from app.simulation.timetable import TrainPlan

FOG_MONTHS = frozenset({11, 12, 1, 2})  # fog is likely in these months
FOG_PROBABILITY_IN_SEASON = 0.9
FOG_PROBABILITY_OFF_SEASON = 0.1

MAX_WEATHER_MIN = 120  # fog / weather slowdown / signal failure never last longer
MAX_CLOSURE_MIN = 90
CRAWL_FACTOR = 0.3  # speed factor for a train already inside a block that gets closed

CLOSING_KINDS = frozenset({DisruptionKind.BLOCK_CLOSURE, DisruptionKind.MAINTENANCE})
SLOWING_KINDS = frozenset({DisruptionKind.FOG, DisruptionKind.WEATHER_SLOWDOWN})

DEFAULT_FACTORS = {
    DisruptionKind.FOG: 0.6,
    DisruptionKind.WEATHER_SLOWDOWN: 0.8,
    DisruptionKind.SIGNAL_FAILURE: 0.3,
    DisruptionKind.BLOCK_CLOSURE: 0.0,
    DisruptionKind.MAINTENANCE: 0.0,
    DisruptionKind.LATE_DEPARTURE: 1.0,
}


class Intensity(StrEnum):
    """How many random disruptions a sim-day gets."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Counts:
    """Number of random disruptions of each family for one intensity level."""

    weather: int
    signal: int
    late: int
    closure: int


INTENSITY_COUNTS = {
    Intensity.NONE: Counts(0, 0, 0, 0),
    Intensity.LOW: Counts(1, 1, 2, 0),
    Intensity.MEDIUM: Counts(1, 2, 4, 1),
    Intensity.HIGH: Counts(2, 3, 7, 2),
}


# ---- effect on the simulation ---------------------------------------------------------
def is_active(d: Disruption, tick: int) -> bool:
    """Return True while the disruption is in force."""
    return d.start_tick <= tick < d.end_tick


def affects_block(d: Disruption, block: Block) -> bool:
    """Return True if this disruption changes how trains use ``block``."""
    if d.kind is DisruptionKind.LATE_DEPARTURE:
        return False
    if not d.target_ids:
        return True
    targets = set(d.target_ids)
    return block.id in targets or block.from_code in targets or block.to_code in targets


def block_speed_factor(disruptions: list[Disruption], block: Block, tick: int) -> float:
    """Return the speed factor in force on ``block`` (1.0 = normal, 0.0 = closed)."""
    factors = [d.speed_factor for d in disruptions if is_active(d, tick) and affects_block(d, block)]
    return min(factors, default=1.0)


def validate_disruption(d: Disruption, network: Network, train_ids: set[str]) -> None:
    """Raise ValueError if the disruption does not make sense for this network."""
    if d.end_tick <= d.start_tick:
        raise ValueError("a disruption must end after it starts")
    if d.kind is DisruptionKind.LATE_DEPARTURE:
        if len(d.target_ids) != 1 or d.target_ids[0] not in train_ids:
            raise ValueError("late_departure needs exactly one known train id as target")
        return
    known = {b.id for b in network.blocks} | {s.code for s in network.stations}
    unknown = [t for t in d.target_ids if t not in known]
    if unknown:
        raise ValueError(f"unknown block or station: {unknown}")
    if d.kind in CLOSING_KINDS and (d.speed_factor != 0 or not d.target_ids):
        raise ValueError("closures need speed_factor 0 and at least one target")
    if d.kind in SLOWING_KINDS and d.speed_factor <= 0:
        raise ValueError("fog and weather slowdowns need speed_factor above 0")


# ---- random generation ----------------------------------------------------------------------
def _make(
    kind: DisruptionKind, start: int, duration: int, targets: list[str], factor: float, text: str
) -> Disruption:
    return Disruption(
        id="tmp",
        kind=kind,
        start_tick=start,
        end_tick=start + duration,
        target_ids=targets,
        speed_factor=factor,
        description=text,
    )


def _weather(network: Network, rng: random.Random, month: int) -> Disruption:
    """Fog (mostly in season) or a weather slowdown over a stretch of the main line."""
    route = network.shortest_route("SGP", "ARC")
    length = rng.randint(3, 7)
    first = rng.randint(0, len(route) - length)
    stretch = route[first : first + length]
    blocks = [
        block.id
        for left, right in zip(stretch, stretch[1:], strict=False)
        for block, _ in network.route_blocks([left, right])
    ]
    chance = FOG_PROBABILITY_IN_SEASON if month in FOG_MONTHS else FOG_PROBABILITY_OFF_SEASON
    foggy = rng.random() < chance
    start = rng.randint(0, 1000)
    if foggy:
        factor, duration, kind, name = (
            round(rng.uniform(0.5, 0.8), 2),
            rng.randint(60, MAX_WEATHER_MIN),
            DisruptionKind.FOG,
            "Fog",
        )
    else:
        factor, duration, kind, name = (
            round(rng.uniform(0.7, 0.9), 2),
            rng.randint(30, 90),
            DisruptionKind.WEATHER_SLOWDOWN,
            "Heavy rain",
        )
    text = f"{name} between {stretch[0]} and {stretch[-1]}: speeds reduced to {round(factor * 100)}%."
    return _make(kind, start, duration, blocks, factor, text)


def _signal_failure(network: Network, rng: random.Random) -> Disruption:
    """Draw a failed signal: a block that is unusable or slow, or slow running around a station."""
    start = rng.randint(0, 1100)
    if rng.random() < 1 / 3:
        station = rng.choice(sorted(s.code for s in network.stations))
        text = f"Signal failure at {station}: trains approach and leave at 40% speed."
        return _make(
            DisruptionKind.SIGNAL_FAILURE, start, rng.randint(20, MAX_WEATHER_MIN), [station], 0.4, text
        )
    block = rng.choice(sorted(b.id for b in network.blocks))
    if rng.random() < 0.5:
        return _make(
            DisruptionKind.SIGNAL_FAILURE,
            start,
            rng.randint(15, 60),
            [block],
            0.0,
            f"Signal failure: {block} unusable.",
        )
    return _make(
        DisruptionKind.SIGNAL_FAILURE,
        start,
        rng.randint(20, MAX_WEATHER_MIN),
        [block],
        0.3,
        f"Signal failure: {block} at 30% speed.",
    )


def _closure(network: Network, rng: random.Random) -> Disruption:
    """Draw a block closure for maintenance or after an incident."""
    block = rng.choice(sorted(b.id for b in network.blocks))
    kind = rng.choice([DisruptionKind.MAINTENANCE, DisruptionKind.BLOCK_CLOSURE])
    label = "Track maintenance" if kind is DisruptionKind.MAINTENANCE else "Block closure"
    return _make(
        kind,
        rng.randint(150, 1100),
        rng.randint(30, MAX_CLOSURE_MIN),
        [block],
        0.0,
        f"{label}: {block} closed.",
    )


def late_departure(plan: TrainPlan, minutes: int) -> Disruption:
    """Build a late-departure disruption for one train."""
    start = plan.departure_min
    return _make(
        DisruptionKind.LATE_DEPARTURE,
        start,
        minutes,
        [plan.id],
        1.0,
        f"{plan.id} departs {minutes} min late.",
    )


def generate_disruptions(
    network: Network, plans: list[TrainPlan], rng: random.Random, intensity: Intensity, month: int
) -> list[Disruption]:
    """Draw a reproducible set of random disruptions for one sim-day.

    ``month`` (1-12) only changes how likely fog is (Nov-Feb: mostly fog).
    """
    counts = INTENSITY_COUNTS[intensity]
    found = [_weather(network, rng, month) for _ in range(counts.weather)]
    found += [_signal_failure(network, rng) for _ in range(counts.signal)]
    found += [_closure(network, rng) for _ in range(counts.closure)]
    ordered = sorted(plans, key=lambda p: p.id)
    for plan in rng.sample(ordered, k=min(counts.late, len(ordered))):
        found.append(late_departure(plan, rng.randint(10, 60)))
    found.sort(key=lambda d: (d.start_tick, d.kind.value, d.target_ids))
    return [d.model_copy(update={"id": f"d-{i:03d}"}) for i, d in enumerate(found, start=1)]
