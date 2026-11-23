"""Tests for the network model and the fictional demo corridor."""

import pytest

from app.models.corridor import SEGMENTS, STATIONS, build_corridor
from app.models.network import (
    Block,
    Direction,
    LineType,
    Network,
    Segment,
    Station,
    split_into_blocks,
)

MAIN_LINE_KM = 348.0


@pytest.fixture(scope="module")
def net() -> Network:
    return build_corridor()


def test_station_count_and_junctions(net: Network) -> None:
    assert len(net.stations) == 15
    assert {s.code for s in net.junctions()} == {"VDJ", "RMJ"}


def test_platform_counts(net: Network) -> None:
    assert all(s.platforms >= 2 for s in net.stations)
    assert all(s.platforms >= 5 for s in net.junctions())


def test_main_line_distance(net: Network) -> None:
    route = net.shortest_route("SGP", "ARC")
    assert route[0] == "SGP" and route[-1] == "ARC"
    assert net.route_length_km(route) == pytest.approx(MAIN_LINE_KM)


def test_branch_route_goes_through_junction(net: Network) -> None:
    route = net.shortest_route("TLK", "ARC")
    assert route[:4] == ["TLK", "KSG", "PTK", "VDJ"]


def test_block_count_and_max_length(net: Network) -> None:
    assert len(net.blocks) == 45
    assert all(b.length_km <= 12.0 for b in net.blocks)
    assert len({b.id for b in net.blocks}) == len(net.blocks)


def test_blocks_add_up_to_segment_length() -> None:
    for segment in SEGMENTS:
        blocks = split_into_blocks(segment)
        assert sum(b.length_km for b in blocks) == pytest.approx(segment.length_km)


def test_single_and_double_lines(net: Network) -> None:
    by_prefix = {b.id.rsplit("-", 1)[0]: b for b in net.blocks}
    assert by_prefix["SGP-DVG"].line is LineType.DOUBLE
    assert by_prefix["BHP-GNK"].line is LineType.SINGLE
    assert by_prefix["VDJ-PTK"].line is LineType.SINGLE  # branch


def test_resource_key_single_vs_double() -> None:
    single = Block("X-Y-1", "X", "Y", 10, LineType.SINGLE, 100)
    double = Block("X-Y-2", "X", "Y", 10, LineType.DOUBLE, 100)
    assert single.resource_key(Direction.FORWARD) == single.resource_key(Direction.REVERSE)
    assert double.resource_key(Direction.FORWARD) != double.resource_key(Direction.REVERSE)


def test_route_blocks_forward_and_reverse(net: Network) -> None:
    forward = net.route_blocks(["SGP", "DVG", "KLP"])
    backward = net.route_blocks(["KLP", "DVG", "SGP"])
    assert all(d is Direction.FORWARD for _, d in forward)
    assert all(d is Direction.REVERSE for _, d in backward)
    assert [b.id for b, _ in backward] == [b.id for b, _ in reversed(forward)]


def test_route_blocks_rejects_non_adjacent(net: Network) -> None:
    with pytest.raises(ValueError):
        net.route_blocks(["SGP", "KLP"])


def test_goods_yard_is_freight_only(net: Network) -> None:
    assert net.station("RGY").freight_only
    assert not net.station("SGP").freight_only


def test_duplicate_station_rejected() -> None:
    with pytest.raises(ValueError):
        Network([Station("A", "A", 1, 2), Station("A", "A2", 1, 2)], [])


def test_unknown_station_in_segment_rejected() -> None:
    with pytest.raises(ValueError):
        Network([Station("A", "A", 1, 2)], [Segment("A", "Z", 10, LineType.DOUBLE, 100)])


def test_disconnected_network_rejected() -> None:
    with pytest.raises(ValueError):
        Network([Station("A", "A", 1, 2), Station("B", "B", 1, 2)], [])


def test_junction_needs_three_connections() -> None:
    stations = [Station("A", "A", 1, 2), Station("J", "J", 1, 5, is_junction=True), Station("B", "B", 1, 2)]
    segments = [Segment("A", "J", 10, LineType.DOUBLE, 100), Segment("J", "B", 10, LineType.DOUBLE, 100)]
    with pytest.raises(ValueError):
        Network(stations, segments)


def test_station_codes_unique() -> None:
    codes = [s.code for s in STATIONS]
    assert len(codes) == len(set(codes))
