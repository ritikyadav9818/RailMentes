"""Mutable per-train state used by the engine (the Pydantic TrainState is built from it)."""

from dataclasses import dataclass, field
from enum import StrEnum

from app.models.network import Block, Direction, Network
from app.simulation.timetable import TrainPlan


class Phase(StrEnum):
    """Where a train is in its life."""

    NOT_STARTED = "not_started"
    AT_STATION = "at_station"
    IN_BLOCK = "in_block"
    FINISHED = "finished"


@dataclass
class WaitEvent:
    """One time a train had to wait because the next track resource was not available."""

    train_id: str
    block_id: str  # the block it wanted to enter
    start: int  # first tick it was refused
    blockers: list[str] = field(
        default_factory=list
    )  # trains that kept it out, in order (empty = block closed)
    end: int | None = None  # tick it got going again (None while still waiting)

    @property
    def blocker(self) -> str | None:
        """The first train that kept it out (None if only a closed block did)."""
        return self.blockers[0] if self.blockers else None


@dataclass
class TrainRuntime:
    """Everything the engine tracks about one train."""

    plan: TrainPlan
    hops: list[list[tuple[Block, Direction]]]  # blocks to cross between consecutive stations
    phase: Phase = Phase.NOT_STARTED
    station_idx: int = 0  # current station (AT_STATION) or the one just left (IN_BLOCK)
    block_idx: int = 0  # index inside hops[station_idx] while IN_BLOCK
    offset_km: float = 0.0  # distance covered inside the current block
    arrived_tick: int = 0
    ready_tick: int = 0  # earliest departure while AT_STATION
    blocked_since: int | None = None  # tick the train started waiting for a resource
    open_wait: WaitEvent | None = None  # the wait being logged right now
    moving: bool = False
    extra_delay: int = 0  # late-departure disruption: minutes added to the origin departure
    recorded_delay: float = 0.0  # last measured delay vs timetable (min)
    last_arrival_delay: float = 0.0  # delay when the train reached the station it last visited
    pending_holds: dict[str, int] = field(default_factory=dict)  # station -> minutes
    yields: dict[str, str] = field(default_factory=dict)  # station -> train that must pass first

    @classmethod
    def create(cls, plan: TrainPlan, network: Network) -> "TrainRuntime":
        """Build the runtime for a plan, pre-computing the blocks of every hop."""
        route = plan.route
        hops = [network.route_blocks([route[i], route[i + 1]]) for i in range(len(route) - 1)]
        return cls(plan=plan, hops=hops)

    @property
    def current_block(self) -> tuple[Block, Direction]:
        """The block the train is in (only valid while IN_BLOCK)."""
        return self.hops[self.station_idx][self.block_idx]

    def station_index(self, station: str) -> int | None:
        """Index of ``station`` on this train's route, or None."""
        for i, stop in enumerate(self.plan.stops):
            if stop.station == station:
                return i
        return None

    def has_passed(self, station: str) -> bool:
        """Return True if the train has finished, or has already left ``station``."""
        k = self.station_index(station)
        if k is None or self.phase is Phase.FINISHED:
            return True
        return self.station_idx > k or (self.station_idx == k and self.phase is Phase.IN_BLOCK)
