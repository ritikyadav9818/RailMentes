"""KPI computation from a finished or running simulation.

Definitions (the same for every strategy, so the comparison is fair):
    * average delay: mean delay (min) over trains that have started; a train running early counts as 0.
      For a finished train the delay is the one at its destination.
    * punctuality: share of those trains that are at most 5 min late.
    * throughput: trains finished per hour of simulated time so far.
    * priority-weighted delay: sum of priority x delay (min) over the same trains (premium 4x, freight 1x).
    * conflicts detected: distinct conflicts the detector flagged during the run.
    * actions applied: control actions that were applied to the simulation.
    * blocking events: times a train really had to wait for a block held by another train
      (waits of at least ``REAL_WAIT_MIN`` minutes), measured by the simulator itself.
"""

from collections.abc import Iterable

from pydantic import Field

from app.models.schemas import KPI, Contract, StateSnapshot, StrategyName, TrainStatus
from app.simulation.engine import PUNCTUAL_LIMIT_MIN
from app.simulation.runtime import WaitEvent

REAL_WAIT_MIN = 3


class RunKpis(Contract):
    """All KPIs of one run under one strategy."""

    strategy: StrategyName
    end_tick: int
    trains_total: int
    trains_finished: int
    avg_delay_min: float
    punctuality_pct: float = Field(ge=0, le=100)
    throughput_per_hour: float = Field(ge=0)
    priority_weighted_delay: float = Field(ge=0)
    conflicts_detected: int = Field(ge=0)
    actions_applied: int = Field(ge=0)
    blocking_events: int = Field(ge=0)

    def to_schema(self, baseline_blocking_events: int | None = None) -> KPI:
        """Return the shared ``KPI`` contract.

        ``conflicts_avoided`` = blocking events this run had fewer than no control (never negative).
        """
        avoided = (
            0 if baseline_blocking_events is None else max(0, baseline_blocking_events - self.blocking_events)
        )
        return KPI(
            strategy=self.strategy,
            avg_delay_min=self.avg_delay_min,
            punctuality_pct=self.punctuality_pct,
            throughput_per_hour=self.throughput_per_hour,
            conflicts_avoided=avoided,
        )


def count_blocking_events(events: Iterable[WaitEvent], now: int, min_minutes: int = REAL_WAIT_MIN) -> int:
    """Count waits caused by another train that lasted at least ``min_minutes`` (open ones until ``now``)."""
    return sum(
        1 for e in events if e.blockers and (e.end if e.end is not None else now) - e.start >= min_minutes
    )


def compute_kpis(
    state: StateSnapshot,
    strategy: StrategyName,
    conflicts_detected: int = 0,
    actions_applied: int = 0,
    blocking_events: int = 0,
) -> RunKpis:
    """Compute the KPIs of a snapshot (taken at the end of a run, or mid-run for the live picture)."""
    started = [t for t in state.trains if t.status is not TrainStatus.NOT_STARTED]
    delays = [max(t.delay_min, 0.0) for t in started]
    finished = sum(t.status is TrainStatus.FINISHED for t in state.trains)
    return RunKpis(
        strategy=strategy,
        end_tick=state.tick,
        trains_total=len(state.trains),
        trains_finished=finished,
        avg_delay_min=round(sum(delays) / len(delays), 2) if delays else 0.0,
        punctuality_pct=round(100 * sum(d <= PUNCTUAL_LIMIT_MIN for d in delays) / len(delays), 1)
        if delays
        else 100.0,
        throughput_per_hour=round(finished / (state.tick / 60), 2) if state.tick else 0.0,
        priority_weighted_delay=round(sum(t.priority * d for t, d in zip(started, delays, strict=True)), 1),
        conflicts_detected=conflicts_detected,
        actions_applied=actions_applied,
        blocking_events=blocking_events,
    )
