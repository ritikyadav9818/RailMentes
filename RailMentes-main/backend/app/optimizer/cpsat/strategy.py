"""The CP-SAT strategy: plugs the optimizer into the shared ``Strategy`` interface.

One call to ``propose``:
    1. Take the trains named in the detected conflicts and look up their predicted timelines (the same
       detector and the same predicted snapshot every other strategy uses).
    2. Cut the problem into independent components (``problem.py``) and solve each one (``solver.py``).
    3. Turn each hold into an action. A hold that makes the leader give way to a train that will pass the
       same station soon becomes a PRECEDENCE ("wait until that train has passed"), which does not depend on
       exact minutes; any other hold stays a HOLD of the solved length.
    4. If a component cannot be solved (no solution, timeout with nothing, an error), the priority rule
       decides for that component and the reason says so.

The strategy is stateless: the same snapshot always gives the same answer, and it does not remember what it
proposed before (the caller applies a conflict only once, exactly as for the other strategies).

All data is synthetic.
"""

import logging
import time
from collections import Counter

from app.models.network import Network
from app.models.schemas import Action, ActionKind, Conflict, StateSnapshot, StrategyName, TrainState
from app.models.train import get_train_type
from app.optimizer.conflicts import DEFAULT_LOOKAHEAD_MIN, ConflictDetector
from app.optimizer.cpsat.problem import Component, Params, Problem, build_components
from app.optimizer.cpsat.solver import Plan, solve
from app.optimizer.priority import PriorityRule
from app.optimizer.resolve import _arrival
from app.optimizer.strategy import Proposal, Strategy

log = logging.getLogger(__name__)
CACHE_SIZE = 512
FALLBACK_NOTE = "CP-SAT fallback to the priority rule ({why})."


class CpSatStrategy(Strategy):
    """Chooses precedence and hold times by minimising priority-weighted predicted delay."""

    name = StrategyName.CPSAT

    def __init__(
        self,
        network: Network,
        lookahead_min: int = DEFAULT_LOOKAHEAD_MIN,
        params: Params | None = None,
        detector: ConflictDetector | None = None,
    ) -> None:
        self.network = network
        self.params = params or Params(lookahead_min=lookahead_min)
        self.detector = detector or ConflictDetector(network, self.params.lookahead_min)
        self.fallback = PriorityRule(network, self.params.lookahead_min, self.detector)
        self.stats: Counter[str] = Counter()  # solves, cache_hits, fallbacks, ... (read by the benchmark)
        self.solve_seconds: list[float] = []
        self._cache: dict[Problem, Plan] = {}

    def decide(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Action]:
        """Return the optimizer's actions for the conflicts (empty = do nothing)."""
        return [p.action for p in self.propose(state, conflicts)]

    def propose(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Proposal]:
        """Return actions with the conflicts they settle and the delay they save."""
        if not conflicts:
            return []
        timelines = self.detector.timelines(state)
        seeds = {tid for c in conflicts for tid in c.train_ids}
        proposals: dict[tuple[str, str], Proposal] = {}
        for component in build_components(state, timelines, seeds, self.params):
            for proposal in self._component_proposals(state, conflicts, component):
                action = proposal.action
                proposals.setdefault((action.train_id, action.at_station), proposal)
        return list(proposals.values())

    # ---- one component ------------------------------------------------------------------
    def _component_proposals(
        self, state: StateSnapshot, conflicts: list[Conflict], component: Component
    ) -> list[Proposal]:
        ids = {t.id for t in component.problem.trains}
        mine = [c for c in conflicts if set(c.train_ids) <= ids]
        plan, why = self._plan(component)
        if plan is None or not plan.usable:
            self.stats["fallbacks"] += 1
            return self._fallback(state, mine, why)
        if plan.status != "OPTIMAL":
            self.stats["not_optimal"] += 1
        return self._proposals(state, mine, component, plan)

    def _plan(self, component: Component) -> tuple[Plan | None, str]:
        cached = self._cache.get(component.problem)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached, ""
        started = time.perf_counter()
        try:
            plan = solve(component.problem, self.params)
        except Exception as error:  # noqa: BLE001 - any solver failure must fall back, never crash the loop
            log.warning("CP-SAT failed (%s); using the priority rule", error)
            return None, "the solver raised an error"
        self.solve_seconds.append(time.perf_counter() - started)
        self.stats["solves"] += 1
        if not plan.usable:
            return plan, f"the solver found no plan: {plan.status}"
        if len(self._cache) >= CACHE_SIZE:
            self._cache.clear()
        self._cache[component.problem] = plan
        return plan, ""

    def _fallback(self, state: StateSnapshot, conflicts: list[Conflict], why: str) -> list[Proposal]:
        note = FALLBACK_NOTE.format(why=why or "no plan")
        return [
            Proposal(
                p.action.model_copy(update={"reason": f"{note} {p.action.reason}"}),
                p.conflict_ids,
                p.expected_delay_saved_min,
            )
            for p in self.fallback.propose(state, conflicts)
        ]

    # ---- plan -> actions ----------------------------------------------------------------------
    def _proposals(
        self, state: StateSnapshot, conflicts: list[Conflict], component: Component, plan: Plan
    ) -> list[Proposal]:
        problem = component.problem
        trains = {t.id: t for t in state.trains}
        baseline = solve(problem, self.params, caps={slot: 0 for slot in component.hops})
        out: list[Proposal] = []
        for (t, h), extra in sorted(plan.holds.items()):
            info = component.hops[t, h]
            if info.left or info.depart - state.tick > self.params.decision_horizon_min:
                continue  # too early to decide (predictions will be fresher later) or already gone
            winner_ids = dict.fromkeys(
                problem.trains[g.follower].id
                for k, g in enumerate(problem.groups)
                if k in plan.flipped and g.leader == t
            )
            winners = [trains[tid] for tid in winner_ids]
            ids = _conflict_ids(conflicts, problem.trains[t].id, winners)
            if not ids:
                continue
            saved = self._saving(component, plan, baseline, (t, h))
            minutes = min(self.params.max_hold_min, max(1, info.dwell + extra))
            action = self._action(
                state, trains[problem.trains[t].id], info.station, minutes, winners, info.depart, saved
            )
            out.append(Proposal(action, ids, round(saved[1], 1)))
        return out

    def _saving(
        self, component: Component, plan: Plan, baseline: Plan, slot: tuple[int, int]
    ) -> tuple[float, float]:
        """Return (weighted, plain) delay minutes this hold saves, compared with the plan without it."""
        if len(plan.holds) == 1:
            without = baseline
        else:
            keep = {s: v for s, v in plan.holds.items() if s != slot}
            without = solve(component.problem, self.params, caps={slot: 0}, pinned=keep)
        if without.usable and without.weighted_delay > plan.weighted_delay:
            return float(without.weighted_delay - plan.weighted_delay), float(
                without.plain_delay - plan.plain_delay
            )
        share = max(0, baseline.weighted_delay - plan.weighted_delay) / len(plan.holds)
        return share, max(0, baseline.plain_delay - plan.plain_delay) / len(plan.holds)

    def _action(
        self,
        state: StateSnapshot,
        loser: TrainState,
        station: str,
        minutes: int,
        winners: list[TrainState],
        depart: int,
        saved: tuple[float, float],
    ) -> Action:
        weighted = f"saves {saved[0]:.0f} weighted delay-minutes ({saved[1]:.0f} min of plain delay)"
        arrivals = [(_arrival(state, w, station), w) for w in winners]
        coming = sorted((a, w.id, w) for a, w in arrivals if a is not None)
        if coming:
            arrival, _, first = coming[0]
            wait = arrival + _halt(first) - depart
            if wait <= self.params.max_yield_wait_min:
                return Action(
                    kind=ActionKind.PRECEDENCE,
                    train_id=loser.id,
                    at_station=station,
                    other_train_id=first.id,
                    reason=(
                        f"CP-SAT plan: {loser.name} gives way at {station} until {_names(winners)} "
                        f"has passed; {weighted}."
                    ),
                )
        return Action(
            kind=ActionKind.HOLD,
            train_id=loser.id,
            at_station=station,
            hold_minutes=minutes,
            reason=(
                f"CP-SAT plan: hold {loser.name} for {minutes} min at {station} "
                f"so {_names(winners)} passes; {weighted}."
            ),
        )


def _halt(train: TrainState) -> int:
    return get_train_type(train.category).halt_minutes


def _names(trains: list[TrainState]) -> str:
    return " and ".join(t.name for t in trains)


def _conflict_ids(conflicts: list[Conflict], loser: str, winners: list[TrainState]) -> list[str]:
    """Return the detected conflicts between the loser and its winners (any conflict of the loser if none)."""
    won = {w.id for w in winners}
    pairs = [c.id for c in conflicts if loser in c.train_ids and won & set(c.train_ids)]
    return pairs or [c.id for c in conflicts if loser in c.train_ids]
