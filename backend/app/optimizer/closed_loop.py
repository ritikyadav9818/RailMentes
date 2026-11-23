"""Closed-loop runner: run one scenario headless under one strategy, from the first tick to the last.

Each tick: build the snapshot (with the delay model's predictions, if a predictor is given) -> detect
conflicts -> ask the strategy for actions -> apply them -> advance the simulation by one minute.

Fairness: the scenario (seed, intensity, month) fixes the timetable and the disruptions, and the strategy
only ever sees the snapshot, so every strategy faces exactly the same day.

All data is synthetic.
"""

from dataclasses import dataclass

from app.ml.features import build_features, is_predictable
from app.ml.predict import DelayPredictor
from app.models.network import Network
from app.models.schemas import Action, Disruption, StateSnapshot
from app.optimizer.conflicts import DEFAULT_LOOKAHEAD_MIN, ConflictDetector
from app.optimizer.kpi import RunKpis, compute_kpis, count_blocking_events
from app.optimizer.strategy import Strategy
from app.simulation.engine import SimulationEngine
from app.simulation.scenario import Scenario


@dataclass(frozen=True)
class RunResult:
    """What a closed-loop run produced."""

    kpis: RunKpis
    applied: list[Action]  # actions that were applied, in order
    conflict_ids: frozenset[str]  # every distinct conflict the detector flagged
    final: StateSnapshot
    disruptions: tuple[Disruption, ...]  # what the day threw at the strategy (same for every strategy)
    departures: dict[str, int]  # scheduled departure of every train (same for every strategy)


def predicted_snapshot(
    engine: SimulationEngine, network: Network, predictor: DelayPredictor | None
) -> StateSnapshot:
    """Return the engine's snapshot with predicted arrival times from the delay model (if there is one)."""
    snapshot = engine.snapshot()
    if predictor is None or predictor.model is None:
        return snapshot
    features = {
        t.id: build_features(snapshot, t, network, engine.last_arrival_delay(t.id))
        for t in snapshot.trains
        if is_predictable(t)
    }
    return predictor.apply(snapshot, features)


def run_closed_loop(
    scenario: Scenario,
    strategy: Strategy,
    network: Network,
    predictor: DelayPredictor | None = None,
    lookahead_min: int = DEFAULT_LOOKAHEAD_MIN,
    max_ticks: int = 4000,
) -> RunResult:
    """Run ``scenario`` to the end under ``strategy`` and return the KPIs.

    Raises:
        RuntimeError: some train never finished within ``max_ticks`` (a deadlock).

    """
    engine = scenario.build(network)
    engine.strategy = strategy.name
    detector = ConflictDetector(network, lookahead_min)
    applied: list[Action] = []
    handled: set[str] = set()  # conflicts already acted on: each one is settled once
    used: set[tuple[str, str]] = set()  # (train, station) pairs that already carry an action
    seen: set[str] = set()
    while not engine.is_done():
        if engine.tick >= max_ticks:
            raise RuntimeError(f"simulation not finished after {max_ticks} ticks (deadlock?)")
        state = predicted_snapshot(engine, network, predictor)
        conflicts = detector.detect(state)
        seen.update(c.id for c in conflicts)
        for proposal in strategy.propose(state, conflicts):
            action = proposal.action
            slot = (action.train_id, action.at_station)
            if handled.isdisjoint(proposal.conflict_ids) and slot not in used and _try_apply(engine, action):
                handled.update(proposal.conflict_ids)
                used.add(slot)
                applied.append(action)
        engine.step()
    final = engine.snapshot()
    blocking = count_blocking_events(engine.wait_events, engine.tick)
    kpis = compute_kpis(final, strategy.name, len(seen), len(applied), blocking)
    departures = {train_id: plan.departure_min for train_id, plan in engine.plans.items()}
    return RunResult(kpis, applied, frozenset(seen), final, tuple(engine.disruptions), departures)


def _try_apply(engine: SimulationEngine, action: Action) -> bool:
    """Apply the action; False if the simulation refuses it (e.g. the train has already left that station)."""
    try:
        engine.apply_action(action)
    except ValueError:
        return False
    return True
