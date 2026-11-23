"""Timetable generation: who runs where, when, and which stations they stop at.

A ``TrainPlan`` lists every station on a train's route with scheduled arrival and
departure times (minutes since scenario start). Running times use the train's own
speed plus a 5% margin, so a train that is never blocked arrives slightly early.

All trains and times are synthetic.
"""

import random
from dataclasses import dataclass

from app.models.network import Network
from app.models.train import TRAIN_TYPES, TrainCategory, TrainType, get_train_type, run_minutes, stops_at

RUNNING_MARGIN = 1.05  # timetable allows 5% more than the minimum running time
MIN_ORIGIN_SPACING_MIN = 10  # two trains never leave the same station closer than this


@dataclass(frozen=True)
class StopPlan:
    """One station on a train's route."""

    station: str
    arrive_min: int
    depart_min: int
    stops: bool  # True if the train halts here (origin and destination always do)


@dataclass(frozen=True)
class TrainPlan:
    """A train's identity and full timetable."""

    id: str
    name: str
    category: TrainCategory
    stops: tuple[StopPlan, ...]

    @property
    def route(self) -> list[str]:
        """Station codes in running order."""
        return [s.station for s in self.stops]

    @property
    def departure_min(self) -> int:
        """Scheduled departure from the origin."""
        return self.stops[0].depart_min


# (category, origin, destination, earliest departure, latest departure) in minutes after 00:00.
# 4 premium + 7 express + 8 passenger + 6 freight = 25 trains per sim-day.
TEMPLATES: list[tuple[TrainCategory, str, str, int, int]] = [
    (TrainCategory.PREMIUM, "SGP", "ARC", 480, 540),
    (TrainCategory.PREMIUM, "ARC", "SGP", 510, 570),
    (TrainCategory.PREMIUM, "SGP", "ARC", 1020, 1080),
    (TrainCategory.PREMIUM, "ARC", "SGP", 1050, 1110),
    (TrainCategory.EXPRESS, "SGP", "ARC", 300, 360),
    (TrainCategory.EXPRESS, "ARC", "SGP", 420, 480),
    (TrainCategory.EXPRESS, "SGP", "TLK", 600, 660),
    (TrainCategory.EXPRESS, "TLK", "SGP", 690, 750),
    (TrainCategory.EXPRESS, "SGP", "ARC", 780, 840),
    (TrainCategory.EXPRESS, "ARC", "SGP", 900, 960),
    (TrainCategory.EXPRESS, "SGP", "ARC", 1140, 1200),
    (TrainCategory.PASSENGER, "SGP", "ARC", 270, 330),
    (TrainCategory.PASSENGER, "ARC", "SGP", 330, 390),
    (TrainCategory.PASSENGER, "VDJ", "TLK", 420, 480),
    (TrainCategory.PASSENGER, "TLK", "VDJ", 540, 600),
    (TrainCategory.PASSENGER, "SGP", "ARC", 660, 720),
    (TrainCategory.PASSENGER, "ARC", "SGP", 780, 840),
    (TrainCategory.PASSENGER, "VDJ", "TLK", 960, 1020),
    (TrainCategory.PASSENGER, "TLK", "VDJ", 1080, 1140),
    (TrainCategory.FREIGHT, "SGP", "ARC", 30, 90),
    (TrainCategory.FREIGHT, "ARC", "SGP", 60, 120),
    (TrainCategory.FREIGHT, "SGP", "RGY", 150, 210),
    (TrainCategory.FREIGHT, "RGY", "ARC", 660, 720),
    (TrainCategory.FREIGHT, "SGP", "ARC", 1230, 1290),
    (TrainCategory.FREIGHT, "ARC", "SGP", 1200, 1260),
]

_ID_PREFIX = {
    TrainCategory.PREMIUM: ("12", 951, "Vande"),
    TrainCategory.EXPRESS: ("22", 401, "Express"),
    TrainCategory.PASSENGER: ("54", 301, "Passenger"),
    TrainCategory.FREIGHT: ("F7", 701, "Goods"),
}


def _hop_minutes(network: Network, a: str, b: str, train_type: TrainType) -> float:
    """Scheduled running time between two adjacent stations."""
    blocks = network.route_blocks([a, b])
    minimum = sum(run_minutes(blk.length_km, blk.speed_limit_kmph, train_type) for blk, _ in blocks)
    return minimum * RUNNING_MARGIN


def build_plan(
    network: Network, train_id: str, name: str, category: TrainCategory, route: list[str], departure_min: int
) -> TrainPlan:
    """Compute the full timetable for one train on a given route."""
    if len(route) < 2:
        raise ValueError("a route needs at least two stations")
    train_type = get_train_type(category)
    for code in route:
        if network.station(code).freight_only and category is not TrainCategory.FREIGHT:
            raise ValueError(f"{category.value} trains cannot use freight-only station {code}")

    stops = [StopPlan(route[0], departure_min, departure_min, True)]
    clock = float(departure_min)
    for i in range(1, len(route)):
        clock += _hop_minutes(network, route[i - 1], route[i], train_type)
        arrive = round(clock)
        is_end = i == len(route) - 1
        halts = not is_end and stops_at(train_type, network.station(route[i]).size)
        if halts:
            clock += train_type.halt_minutes
        stops.append(StopPlan(route[i], arrive, round(clock) if halts else arrive, halts or is_end))
    return TrainPlan(train_id, name, category, tuple(stops))


def generate_timetable(network: Network, seed: int) -> list[TrainPlan]:
    """Generate the ~25 trains of one sim-day. Same seed, same timetable."""
    rng = random.Random(seed)
    counters = dict.fromkeys(TRAIN_TYPES, 0)
    drafts: list[tuple[int, TrainCategory, str, str]] = []
    for category, origin, destination, earliest, latest in TEMPLATES:
        drafts.append((rng.randint(earliest, latest), category, origin, destination))
    drafts.sort(key=lambda d: d[0])

    last_departure: dict[str, int] = {}
    plans: list[TrainPlan] = []
    for departure, category, origin, destination in drafts:
        departure = max(departure, last_departure.get(origin, -999) + MIN_ORIGIN_SPACING_MIN, 1)
        last_departure[origin] = departure
        prefix, first, label = _ID_PREFIX[category]
        train_id = f"{prefix}{first + counters[category]}"
        counters[category] += 1
        route = network.shortest_route(origin, destination)
        plans.append(build_plan(network, train_id, f"{label} {train_id}", category, route, departure))
    return plans
