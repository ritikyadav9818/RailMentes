"""Tick-based simulation engine (1 tick = 1 simulated minute).

How a tick works (``step``):
    1. Queued control actions (hold / precedence) take effect.
    2. Every train is advanced one minute, in first-come-first-served order
       (trains that have waited longest for a resource go first).

Movement rules:
    * A train drives through its blocks at min(block limit, its own top speed).
    * To enter the next block it must claim it (see ``blocks.py``). If the block is
      taken, the train waits at the end of its current block (still holding it), or
      at the station if it was about to leave one.
    * Stopping trains halt for their halt time and never leave before the timetable.
    * Trains are points: length is ignored and a block is released as soon as the
      train enters the next one. Stations have no platform limit in this phase.

Disruptions (see ``disruptions.py``) only change two things: the speed on a block and whether
a block may be entered. Delay then spreads to other trains through the normal block rules.
"""

import random
from collections.abc import Callable
from datetime import datetime, timedelta

from app.models.network import Block, Direction, Network
from app.models.schemas import (
    KPI,
    Action,
    ActionKind,
    BlockOccupancy,
    Disruption,
    DisruptionKind,
    Position,
    StateSnapshot,
    StationStop,
    StrategyName,
    TrainState,
    TrainStatus,
)
from app.models.train import TrainCategory, get_train_type
from app.simulation.blocks import BlockTracker
from app.simulation.disruptions import (
    CRAWL_FACTOR,
    DEFAULT_FACTORS,
    block_speed_factor,
    is_active,
    validate_disruption,
)
from app.simulation.runtime import Phase, TrainRuntime, WaitEvent
from app.simulation.timetable import TrainPlan, generate_timetable

DwellExtra = Callable[[TrainCategory, str, int], int]  # (category, station, tick) -> extra halt minutes

SIM_START = datetime(2026, 1, 15, 0, 0)  # tick 0 is 00:00 on this (synthetic) day
MAX_YIELD_MIN = 60  # a precedence wait is abandoned after this long (safety net)
NEXT_STATIONS_SHOWN = 4
PUNCTUAL_LIMIT_MIN = 5
EPS = 1e-9


class SimulationEngine:
    """Runs a set of train plans on a network, one minute per ``step``."""

    def __init__(
        self,
        network: Network,
        plans: list[TrainPlan],
        seed: int = 0,
        sim_start: datetime = SIM_START,
        dwell_extra: DwellExtra | None = None,
    ) -> None:
        if len({p.id for p in plans}) != len(plans):
            raise ValueError("train ids must be unique")
        self.network = network
        self.seed = seed
        self.rng = random.Random(seed)  # drives random disruptions
        self.sim_start = sim_start
        self.dwell_extra = dwell_extra  # optional extra halt time (see realism.py); None = exact timetable
        self.on_departure: Callable[[str, int, int], None] | None = None  # (train_id, station_idx, tick)
        self.tick = 0
        self.running = False
        self.strategy = StrategyName.NO_CONTROL
        self.tracker = BlockTracker()
        self.arrival_log: dict[str, list[tuple[str, int]]] = {}
        self.wait_events: list[WaitEvent] = []  # every refusal of a block
        self._queue: list[Action] = []
        self._disruptions: list[Disruption] = []
        self._manual_count = 0
        self._trains: dict[str, TrainRuntime] = {
            p.id: TrainRuntime.create(p, network) for p in sorted(plans, key=lambda p: p.id)
        }

    @classmethod
    def from_seed(cls, network: Network, seed: int) -> "SimulationEngine":
        """Engine with the generated sim-day timetable for ``seed``."""
        return cls(network, generate_timetable(network, seed), seed)

    # ---- read-only helpers -----------------------------------------------------
    @property
    def plans(self) -> dict[str, TrainPlan]:
        """Timetable of every train, by id."""
        return {train_id: t.plan for train_id, t in self._trains.items()}

    def last_arrival_delay(self, train_id: str) -> float:
        """Return the delay (min) the train had when it reached the station it last visited."""
        return self._trains[train_id].last_arrival_delay

    # ---- public control -------------------------------------------------------
    def is_done(self) -> bool:
        """Return True when every train has finished its route."""
        return all(t.phase is Phase.FINISHED for t in self._trains.values())

    def step(self) -> None:
        """Advance the simulation by one minute."""
        self._apply_queued_actions()
        now = self.tick + 1
        for train in self._processing_order(now):
            self._advance(train, now)
        self.tick = now

    def run_until_done(self, max_ticks: int = 4000) -> int:
        """Step until all trains finish. Returns the final tick; raises if it never ends."""
        while not self.is_done():
            if self.tick >= max_ticks:
                raise RuntimeError(f"simulation not finished after {max_ticks} ticks (deadlock?)")
            self.step()
        return self.tick

    def apply_action(self, action: Action) -> None:
        """Queue a hold or precedence action; it takes effect at the start of the next tick."""
        train = self._trains.get(action.train_id)
        if train is None:
            raise ValueError(f"unknown train {action.train_id}")
        k = train.station_index(action.at_station)
        if k is None:
            raise ValueError(f"{action.train_id} does not call at {action.at_station}")
        if train.has_passed(action.at_station):
            raise ValueError(f"{action.train_id} has already left {action.at_station}")
        if action.kind is ActionKind.PRECEDENCE:
            if action.other_train_id not in self._trains or action.other_train_id == action.train_id:
                raise ValueError(f"invalid other train {action.other_train_id}")
        self._queue.append(action)

    # ---- disruptions -----------------------------------------------------------------
    @property
    def disruptions(self) -> list[Disruption]:
        """All disruptions known to the engine (past, active and future)."""
        return list(self._disruptions)

    def add_disruption(self, disruption: Disruption) -> None:
        """Register a disruption (validated). Late departures apply to the train immediately."""
        validate_disruption(disruption, self.network, set(self._trains))
        if any(d.id == disruption.id for d in self._disruptions):
            raise ValueError(f"duplicate disruption id {disruption.id}")
        if disruption.kind is DisruptionKind.LATE_DEPARTURE:
            self._delay_departure(disruption)
        self._disruptions.append(disruption)

    def inject_disruption(
        self,
        kind: DisruptionKind,
        duration_min: int,
        target_ids: list[str] | None = None,
        speed_factor: float | None = None,
        description: str | None = None,
    ) -> Disruption:
        """Start a manual disruption now (for the dashboard inject button)."""
        if duration_min <= 0:
            raise ValueError("duration_min must be positive")
        targets = list(target_ids or [])
        start = self.tick
        if kind is DisruptionKind.LATE_DEPARTURE and targets and targets[0] in self._trains:
            start = self._trains[targets[0]].plan.departure_min
        disruption = Disruption(
            id="m-pending",
            kind=kind,
            start_tick=start,
            end_tick=start + duration_min,
            target_ids=targets,
            speed_factor=DEFAULT_FACTORS[kind] if speed_factor is None else speed_factor,
            description=description or f"Manual {kind.value.replace('_', ' ')} for {duration_min} min.",
        )
        return self.add_manual_disruption(disruption)

    def add_manual_disruption(self, disruption: Disruption) -> Disruption:
        """Register a manual disruption under the next free id (m-001, m-002, ...)."""
        numbered = disruption.model_copy(update={"id": f"m-{self._manual_count + 1:03d}"})
        self.add_disruption(numbered)
        self._manual_count += 1
        return numbered

    def _delay_departure(self, disruption: Disruption) -> None:
        train = self._trains[disruption.target_ids[0]]
        minutes = disruption.end_tick - disruption.start_tick
        if train.phase is Phase.NOT_STARTED:
            train.extra_delay = max(train.extra_delay, minutes)
        elif train.phase is Phase.AT_STATION and train.station_idx == 0:
            train.extra_delay = max(train.extra_delay, minutes)
            train.ready_tick = max(train.ready_tick, train.plan.departure_min + minutes)
        else:
            raise ValueError(f"{train.plan.id} has already left its origin")

    def _block_factor(self, block: Block, tick: int) -> float:
        return block_speed_factor(self._disruptions, block, tick)

    def _can_enter(self, block: Block, direction: Direction, train_id: str, now: int) -> bool:
        """Return True if the block is open and free for this train."""
        if self._block_factor(block, now) == 0.0:
            return False
        return self.tracker.can_claim(block, direction, train_id)

    # ---- actions ----------------------------------------------------------------
    def _apply_queued_actions(self) -> None:
        for action in self._queue:
            train = self._trains[action.train_id]
            if action.kind is ActionKind.HOLD:
                self._apply_hold(train, action)
            elif action.other_train_id is not None:
                train.yields[action.at_station] = action.other_train_id
        self._queue.clear()

    def _apply_hold(self, train: TrainRuntime, action: Action) -> None:
        minutes = action.hold_minutes or 0
        here = train.phase is Phase.AT_STATION and train.station_idx == train.station_index(action.at_station)
        if here:
            train.ready_tick = max(train.ready_tick, self.tick + minutes)
        else:
            known = train.pending_holds.get(action.at_station, 0)
            train.pending_holds[action.at_station] = max(known, minutes)

    # ---- per-train advance ---------------------------------------------------------
    def _processing_order(self, now: int) -> list[TrainRuntime]:
        """First come, first served: longest-waiting trains act first."""

        def key(t: TrainRuntime) -> tuple[int, str]:
            return (t.blocked_since if t.blocked_since is not None else now + 1, t.plan.id)

        return sorted(self._trains.values(), key=key)

    def _advance(self, train: TrainRuntime, now: int) -> None:
        if train.phase is Phase.NOT_STARTED and now >= train.plan.departure_min:
            self._on_arrive(train, now)
        elif train.phase is Phase.AT_STATION:
            self._try_depart(train, now)
        elif train.phase is Phase.IN_BLOCK:
            self._drive(train, now)

    def _on_arrive(self, train: TrainRuntime, now: int) -> bool:
        """Train reaches (or, for idx 0, appears at) a station. True = rolls straight through."""
        idx = train.station_idx
        stop = train.plan.stops[idx]
        self.arrival_log.setdefault(train.plan.id, []).append((stop.station, now))
        train.recorded_delay = 0.0 if idx == 0 else float(now - stop.arrive_min)
        train.last_arrival_delay = train.recorded_delay
        train.arrived_tick = now
        self._unblock(train, now)
        train.moving = False
        if idx == len(train.plan.stops) - 1:
            train.phase = Phase.FINISHED
            return False
        train.phase = Phase.AT_STATION
        hold = train.pending_holds.pop(stop.station, 0)
        forced = hold > 0 or stop.station in train.yields
        halt = get_train_type(train.plan.category).halt_minutes
        if idx == 0:
            ready = stop.depart_min + train.extra_delay
        elif stop.stops:
            extra = self.dwell_extra(train.plan.category, stop.station, now) if self.dwell_extra else 0
            ready = max(now + halt + extra, stop.depart_min)
        else:
            ready = now
        train.ready_tick = max(ready, now + hold) if hold else ready
        return idx > 0 and not stop.stops and not forced

    def _try_depart(self, train: TrainRuntime, now: int) -> None:
        """Leave the station if the dwell is over, no one must go first, and the track is free."""
        if now <= train.ready_tick or not self._yield_satisfied(train, now):
            return
        if not self._enter_hop(train, now):
            return
        stop = train.plan.stops[train.station_idx]
        train.recorded_delay = float((now - 1) - stop.depart_min)
        self._emit_departure(train, now)
        self._drive(train, now)

    def _yield_satisfied(self, train: TrainRuntime, now: int) -> bool:
        station = train.plan.stops[train.station_idx].station
        other_id = train.yields.get(station)
        if other_id is None:
            return True
        waited = now - train.arrived_tick
        if self._trains[other_id].has_passed(station) or waited >= MAX_YIELD_MIN:
            del train.yields[station]
            return True
        return False

    def _enter_hop(self, train: TrainRuntime, now: int) -> bool:
        """Claim the first block after the current station. False = must keep waiting."""
        block, direction = train.hops[train.station_idx][0]
        if not self._can_enter(block, direction, train.plan.id, now):
            return self._block_train(train, now, block, direction)
        self.tracker.claim(block, direction, train.plan.id)
        train.phase = Phase.IN_BLOCK
        train.block_idx = 0
        train.offset_km = 0.0
        self._unblock(train, now)
        train.moving = True
        return True

    def _block_train(self, train: TrainRuntime, now: int, block: Block, direction: Direction) -> bool:
        if train.blocked_since is None:
            train.blocked_since = now
            train.open_wait = WaitEvent(train.plan.id, block.id, now)
            self.wait_events.append(train.open_wait)
        closed = self._block_factor(block, now) == 0.0
        blocker = None if closed else self.tracker.blocker(block, direction, train.plan.id)
        if train.open_wait is not None and blocker is not None and blocker not in train.open_wait.blockers:
            train.open_wait.blockers.append(blocker)  # the train in the way can change during a long wait
        train.moving = False
        return False

    def _unblock(self, train: TrainRuntime, now: int) -> None:
        """Close the wait being logged: the train is moving again (or has arrived)."""
        train.blocked_since = None
        if train.open_wait is not None:
            train.open_wait.end = now
            train.open_wait = None

    def _drive(self, train: TrainRuntime, now: int) -> None:
        """Move the train for one minute, crossing block boundaries as far as it can."""
        minutes = 1.0
        train.moving = True
        while minutes > EPS:
            block, _ = train.current_block
            speed = self._speed(train, block, now)
            to_end = block.length_km - train.offset_km
            reach = speed * minutes / 60.0
            if reach < to_end:
                train.offset_km += reach
                self._unblock(train, now)
                return
            minutes -= to_end / speed * 60.0
            train.offset_km = block.length_km
            if not self._enter_next(train, now):
                return

    def _enter_next(self, train: TrainRuntime, now: int) -> bool:
        """At the end of a block: claim the next one or arrive. True = keep driving."""
        hop = train.hops[train.station_idx]
        block, direction = hop[train.block_idx]
        if train.block_idx + 1 < len(hop):
            nxt, nxt_dir = hop[train.block_idx + 1]
            if not self._can_enter(nxt, nxt_dir, train.plan.id, now):
                return self._block_train(train, now, nxt, nxt_dir)
            self.tracker.release(block, direction, train.plan.id)
            self.tracker.claim(nxt, nxt_dir, train.plan.id)
            train.block_idx += 1
            train.offset_km = 0.0
            self._unblock(train, now)
            return True
        self.tracker.release(block, direction, train.plan.id)
        train.station_idx += 1
        if not self._on_arrive(train, now):
            return False
        if not self._enter_hop(train, now):  # passing through: roll on if the track is free
            return False
        self._emit_departure(train, now)
        return True

    def _emit_departure(self, train: TrainRuntime, now: int) -> None:
        """Tell the optional listener that a train just started the hop after station ``station_idx``."""
        if self.on_departure is not None:
            self.on_departure(train.plan.id, train.station_idx, now)

    def _speed(self, train: TrainRuntime, block: Block, tick: int) -> float:
        """Speed in km/h: min(block limit, train top speed), scaled by any active disruption."""
        base = float(min(block.speed_limit_kmph, get_train_type(train.plan.category).max_speed_kmph))
        factor = self._block_factor(block, tick)
        return base * (factor if factor > 0 else CRAWL_FACTOR)

    # ---- delay -------------------------------------------------------------------------
    def _delay(self, train: TrainRuntime) -> float:
        """Return the delay: last measurement, or more if the train is already overdue."""
        if train.phase is Phase.NOT_STARTED:
            return 0.0
        if train.phase is Phase.FINISHED:
            return train.recorded_delay
        stops = train.plan.stops
        due = stops[train.station_idx].depart_min if train.phase is Phase.AT_STATION else stops[
            train.station_idx + 1
        ].arrive_min
        return max(train.recorded_delay, float(self.tick - due))

    # ---- snapshot ------------------------------------------------------------------------
    def snapshot(self) -> StateSnapshot:
        """Return the current state as the shared contract."""
        trains = [self._train_state(t) for t in self._trains.values()]
        return StateSnapshot(
            tick=self.tick,
            sim_time=self.sim_start + timedelta(minutes=self.tick),
            running=self.running,
            strategy=self.strategy,
            trains=trains,
            blocks=self._block_occupancy(),
            disruptions=[d for d in self._disruptions if is_active(d, self.tick)],
            conflicts=[],
            recommendations=[],
            kpis=self._kpis(trains),
        )

    def _block_occupancy(self) -> list[BlockOccupancy]:
        """List claimed blocks (a row per claim) and free blocks that are closed."""
        rows = [
            BlockOccupancy(
                block_id=c.block.id,
                train_id=c.train_id,
                direction=c.direction,
                closed=self._block_factor(c.block, self.tick) == 0.0,
            )
            for c in self.tracker.claims()
        ]
        claimed = {row.block_id for row in rows}
        rows += [
            BlockOccupancy(block_id=block.id, closed=True)
            for block in self.network.blocks
            if block.id not in claimed and self._block_factor(block, self.tick) == 0.0
        ]
        return sorted(rows, key=lambda row: (row.block_id, row.direction.value if row.direction else ""))

    def _train_state(self, train: TrainRuntime) -> TrainState:
        delay = self._delay(train)
        category = train.plan.category
        speed = self._speed(train, train.current_block[0], self.tick) if train.moving else 0.0
        return TrainState(
            id=train.plan.id,
            name=train.plan.name,
            category=category,
            priority=get_train_type(category).priority,
            position=self._position(train),
            speed_kmph=round(speed, 1),
            delay_min=round(delay, 1),
            status=self._status(train),
            next_stations=self._next_stations(train, delay),
            delay_factors=[],
        )

    def _position(self, train: TrainRuntime) -> Position | None:
        if train.phase is Phase.IN_BLOCK:
            block, direction = train.current_block
            offset = round(min(train.offset_km, block.length_km), 2)
            return Position(block_id=block.id, offset_km=offset, direction=direction)
        if train.phase is Phase.AT_STATION:
            return Position(at_station=train.plan.stops[train.station_idx].station)
        return None

    def _status(self, train: TrainRuntime) -> TrainStatus:
        if train.phase is Phase.NOT_STARTED:
            return TrainStatus.NOT_STARTED
        if train.phase is Phase.FINISHED:
            return TrainStatus.FINISHED
        if train.phase is Phase.IN_BLOCK:
            return TrainStatus.RUNNING if train.moving else TrainStatus.WAITING_FOR_SIGNAL
        if self.tick <= train.ready_tick:
            return TrainStatus.HALTED_AT_STATION
        return TrainStatus.WAITING_FOR_SIGNAL

    def _next_stations(self, train: TrainRuntime, delay: float) -> list[StationStop]:
        """Upcoming stations. Predicted time = scheduled + current delay (placeholder until ML)."""
        if train.phase is Phase.FINISHED:
            return []
        first = 0 if train.phase is Phase.NOT_STARTED else train.station_idx + 1
        upcoming = train.plan.stops[first : first + NEXT_STATIONS_SHOWN]
        return [
            StationStop(
                station=s.station,
                will_stop=s.stops,
                scheduled_min=s.arrive_min,
                predicted_min=s.arrive_min + round(delay),
            )
            for s in upcoming
        ]

    def _kpis(self, trains: list[TrainState]) -> KPI:
        """Compute simple live KPIs over started trains (early trains count as 0 delay)."""
        started = [t for t in trains if t.status is not TrainStatus.NOT_STARTED]
        delays = [max(t.delay_min, 0.0) for t in started]
        finished = sum(1 for t in trains if t.status is TrainStatus.FINISHED)
        return KPI(
            strategy=self.strategy,
            avg_delay_min=round(sum(delays) / len(delays), 2) if delays else 0.0,
            punctuality_pct=round(100 * sum(d <= PUNCTUAL_LIMIT_MIN for d in delays) / len(delays), 1)
            if delays
            else 100.0,
            throughput_per_hour=round(finished / (self.tick / 60), 2) if self.tick else 0.0,
            conflicts_avoided=0,
        )
