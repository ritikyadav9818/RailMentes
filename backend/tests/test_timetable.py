"""Tests for timetable generation."""

from collections import Counter

import pytest

from app.models.corridor import build_corridor
from app.models.network import Network
from app.models.train import TrainCategory, get_train_type, stops_at
from app.simulation.timetable import MIN_ORIGIN_SPACING_MIN, build_plan, generate_timetable


@pytest.fixture(scope="module")
def net() -> Network:
    return build_corridor()


def test_train_mix(net: Network) -> None:
    plans = generate_timetable(net, 42)
    counts = Counter(p.category for p in plans)
    assert len(plans) == 25
    assert counts == {
        TrainCategory.PREMIUM: 4,
        TrainCategory.EXPRESS: 7,
        TrainCategory.PASSENGER: 8,
        TrainCategory.FREIGHT: 6,
    }


def test_same_seed_same_timetable_and_different_seed_differs(net: Network) -> None:
    assert generate_timetable(net, 1) == generate_timetable(net, 1)
    assert generate_timetable(net, 1) != generate_timetable(net, 2)


def test_ids_unique_and_departures_positive(net: Network) -> None:
    plans = generate_timetable(net, 5)
    assert len({p.id for p in plans}) == 25
    assert all(p.departure_min >= 1 for p in plans)


def test_times_never_go_backwards(net: Network) -> None:
    for plan in generate_timetable(net, 3):
        clock = plan.stops[0].depart_min
        for stop in plan.stops[1:]:
            assert stop.arrive_min >= clock
            assert stop.depart_min >= stop.arrive_min
            clock = stop.depart_min


def test_stopping_patterns_follow_train_type(net: Network) -> None:
    for plan in generate_timetable(net, 3):
        ttype = get_train_type(plan.category)
        for stop in plan.stops[1:-1]:
            assert stop.stops == stops_at(ttype, net.station(stop.station).size)
        assert plan.stops[0].stops and plan.stops[-1].stops
        if plan.category is TrainCategory.FREIGHT:
            assert not any(s.stops for s in plan.stops[1:-1])


def test_departures_from_one_station_are_spaced(net: Network) -> None:
    last: dict[str, int] = {}
    for plan in sorted(generate_timetable(net, 9), key=lambda p: p.departure_min):
        origin = plan.stops[0].station
        if origin in last:
            assert plan.departure_min - last[origin] >= MIN_ORIGIN_SPACING_MIN
        last[origin] = plan.departure_min


def test_only_freight_uses_goods_yard(net: Network) -> None:
    for plan in generate_timetable(net, 3):
        if "RGY" in plan.route:
            assert plan.category is TrainCategory.FREIGHT
    with pytest.raises(ValueError):
        build_plan(net, "X", "x", TrainCategory.EXPRESS, ["RMJ", "RGY"], 10)


def test_route_needs_two_stations(net: Network) -> None:
    with pytest.raises(ValueError):
        build_plan(net, "X", "x", TrainCategory.EXPRESS, ["SGP"], 10)
