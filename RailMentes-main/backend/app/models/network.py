"""Railway network model: stations, segments, block sections and the graph.

Vocabulary:
    Station  - a node where trains can stop/cross (junctions are stations).
    Segment  - the track between two neighbouring stations.
    Block    - a slice of a segment; only ONE train may occupy a block at a time.
               (Double lines: one train per direction.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

import networkx as nx

DEFAULT_BLOCK_KM = 12.0


class LineType(StrEnum):
    """Single line: both directions share the track. Double: one track each way."""

    SINGLE = "single"
    DOUBLE = "double"


class Direction(StrEnum):
    """Travel direction relative to how a segment is stored (from -> to)."""

    FORWARD = "fwd"
    REVERSE = "rev"


@dataclass(frozen=True)
class Station:
    """A station. ``size``: 1 = major, 2 = medium, 3 = minor."""

    code: str
    name: str
    size: int
    platforms: int
    is_junction: bool = False
    freight_only: bool = False


@dataclass(frozen=True)
class Segment:
    """Track between two adjacent stations, as stored (from_code -> to_code)."""

    from_code: str
    to_code: str
    length_km: float
    line: LineType
    speed_limit_kmph: int


@dataclass(frozen=True)
class Block:
    """One block section. At most one train may occupy a resource at a time."""

    id: str
    from_code: str
    to_code: str
    length_km: float
    line: LineType
    speed_limit_kmph: int

    def resource_key(self, direction: Direction) -> str:
        """Key of the physical resource a train occupies in this block.

        Single line: both directions share one key (they would collide head-on).
        Double line: each direction has its own key.
        """
        if self.line is LineType.SINGLE:
            return self.id
        return f"{self.id}:{direction.value}"


def split_into_blocks(segment: Segment, target_km: float = DEFAULT_BLOCK_KM) -> list[Block]:
    """Cut a segment into equal blocks of at most ``target_km`` each."""
    count = max(1, math.ceil(segment.length_km / target_km))
    length = segment.length_km / count
    return [
        Block(
            id=f"{segment.from_code}-{segment.to_code}-{i + 1}",
            from_code=segment.from_code,
            to_code=segment.to_code,
            length_km=length,
            line=segment.line,
            speed_limit_kmph=segment.speed_limit_kmph,
        )
        for i in range(count)
    ]


class Network:
    """Stations + segments + blocks, with a networkx graph for routing."""

    def __init__(self, stations: list[Station], segments: list[Segment]) -> None:
        self._stations: dict[str, Station] = {}
        for station in stations:
            if station.code in self._stations:
                raise ValueError(f"duplicate station code: {station.code}")
            self._stations[station.code] = station

        self.graph: nx.Graph = nx.Graph()
        self.graph.add_nodes_from(self._stations)
        self._segment_blocks: dict[tuple[str, str], list[Block]] = {}
        for segment in segments:
            self._add_segment(segment)
        self._check_integrity()

    def _add_segment(self, segment: Segment) -> None:
        for code in (segment.from_code, segment.to_code):
            if code not in self._stations:
                raise ValueError(f"segment refers to unknown station: {code}")
        self.graph.add_edge(segment.from_code, segment.to_code, length_km=segment.length_km)
        self._segment_blocks[(segment.from_code, segment.to_code)] = split_into_blocks(segment)

    def _check_integrity(self) -> None:
        if not nx.is_connected(self.graph):
            raise ValueError("network is not connected")
        for station in self.junctions():
            if self.graph.degree(station.code) < 3:
                raise ValueError(f"junction {station.code} needs at least 3 connections")

    # ---- lookups ----------------------------------------------------------
    @property
    def stations(self) -> list[Station]:
        """All stations."""
        return list(self._stations.values())

    def station(self, code: str) -> Station:
        """Look up a station by code."""
        return self._stations[code]

    def junctions(self) -> list[Station]:
        """Stations flagged as junctions."""
        return [s for s in self._stations.values() if s.is_junction]

    @property
    def blocks(self) -> list[Block]:
        """Every block section in the network."""
        return [b for blocks in self._segment_blocks.values() for b in blocks]

    # ---- routing ----------------------------------------------------------
    def shortest_route(self, origin: str, destination: str) -> list[str]:
        """Station codes along the shortest path (by km)."""
        return nx.shortest_path(self.graph, origin, destination, weight="length_km")

    def route_blocks(self, route: list[str]) -> list[tuple[Block, Direction]]:
        """Ordered (block, direction) pairs a train passes along ``route``."""
        passes: list[tuple[Block, Direction]] = []
        for a, b in pairwise(route):
            if (a, b) in self._segment_blocks:
                passes.extend((blk, Direction.FORWARD) for blk in self._segment_blocks[(a, b)])
            elif (b, a) in self._segment_blocks:
                reversed_blocks = reversed(self._segment_blocks[(b, a)])
                passes.extend((blk, Direction.REVERSE) for blk in reversed_blocks)
            else:
                raise ValueError(f"no track between {a} and {b}")
        return passes

    def route_length_km(self, route: list[str]) -> float:
        """Total distance of a route in km."""
        return sum(block.length_km for block, _ in self.route_blocks(route))
