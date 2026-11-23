"""Shared logic of the rule-based strategies (FCFS and priority).

Both strategies work the same way and differ in ONE thing: which of two conflicting trains goes first.
For every detected conflict:
    1. The strategy's rule picks the train that goes first and the train that must yield.
    2. The yielding train waits at the last station before the contested track:
       * PRECEDENCE ("let that train pass this station first") when the strategy uses it and the winner
         still has to come through that station, e.g. opposing trains on a single line;
       * HOLD for the predicted wait (at most ``MAX_HOLD_MIN``) otherwise.
    3. A rule that agrees with the natural order (the winner reaches the track first anyway) adds no
       action unless ``acts_in_natural_order`` is set (FCFS: the later train is told to wait).
    4. A precedence is only used if the winner reaches that station within ``MAX_YIELD_WAIT_MIN`` after the
       yielding train is ready to leave; waiting longer for a far-away train costs more than it saves.
    5. No action if the yielding train has already left that station (it can no longer be stopped there),
       or if it is still more than ``DECISION_HORIZON_MIN`` away from leaving it: decide late, when the
       predictions are fresh.
"""

import math
from abc import abstractmethod
from datetime import timedelta

from app.models.network import Network
from app.models.schemas import Action, ActionKind, Conflict, StateSnapshot, TrainState
from app.models.train import get_train_type
from app.optimizer.conflicts import DEFAULT_LOOKAHEAD_MIN, ConflictDetector, Contention, Visit
from app.optimizer.strategy import Proposal, Strategy

DECISION_HORIZON_MIN = 10
MAX_HOLD_MIN = 30
MAX_YIELD_WAIT_MIN = 15


class RuleStrategy(Strategy):
    """A strategy that settles each conflict by asking "who goes first?".

    ``decide`` and ``propose`` are pure: the same snapshot always gives the same answer. The caller
    (closed loop or live runner) makes sure a conflict is only acted on once.
    """

    acts_in_natural_order = False  # also act when the winner is the train that arrives first anyway
    uses_precedence = True  # False: always HOLD

    def __init__(
        self,
        network: Network,
        lookahead_min: int = DEFAULT_LOOKAHEAD_MIN,
        detector: ConflictDetector | None = None,
    ) -> None:
        self.network = network
        self.detector = detector or ConflictDetector(network, lookahead_min)

    @abstractmethod
    def goes_first(self, a: TrainState, b: TrainState, contention: Contention) -> TrainState:
        """Return whichever of ``a`` and ``b`` goes first (``a`` reaches the contested track first)."""

    @abstractmethod
    def rule_text(self, winner: TrainState, loser: TrainState) -> str:
        """Return one sentence naming the rule, used in the action's reason."""

    def decide(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Action]:
        """Return one hold/precedence action per yielding train and station."""
        return [p.action for p in self.propose(state, conflicts)]

    def propose(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Proposal]:
        """Return the actions with the conflict they resolve and the wait the favoured train avoids."""
        details = {c.conflict.id: c for c in self.detector.find(state)}
        trains = {t.id: t for t in state.trains}
        proposals: dict[tuple[str, str], Proposal] = {}
        for conflict in conflicts:
            contention = details.get(conflict.id)
            proposal = self._proposal(state, trains, contention) if contention else None
            if proposal is not None:
                proposals.setdefault((proposal.action.train_id, proposal.action.at_station), proposal)
        return list(proposals.values())

    def _proposal(
        self, state: StateSnapshot, trains: dict[str, TrainState], contention: Contention
    ) -> Proposal | None:
        a, b = trains[contention.leader.train_id], trains[contention.follower.train_id]
        winner = self.goes_first(a, b, contention)
        if winner is a and not self.acts_in_natural_order:
            return None
        loser = b if winner is a else a
        visit = contention.follower if loser is b else contention.leader
        if visit.left_station or visit.hop_start - state.tick > DECISION_HORIZON_MIN:
            return None
        action = self._action(state, winner, loser, visit, contention)
        if action is None:
            return None
        saved = contention.wait_min if winner is b else 0.0  # wait the favoured train avoids
        return Proposal(action, [contention.conflict.id], round(saved, 1))

    def _action(
        self,
        state: StateSnapshot,
        winner: TrainState,
        loser: TrainState,
        visit: Visit,
        contention: Contention,
    ) -> Action | None:
        station = visit.hop_from
        reason = f"{self.rule_text(winner, loser)} {self._situation(state, contention)}"
        arrival = _arrival(state, winner, station) if self.uses_precedence else None
        if arrival is not None:
            if arrival + get_train_type(winner.category).halt_minutes - visit.hop_start > MAX_YIELD_WAIT_MIN:
                return None
            return Action(
                kind=ActionKind.PRECEDENCE,
                train_id=loser.id,
                at_station=station,
                other_train_id=winner.id,
                reason=f"{reason} {loser.name} waits at {station} until {winner.name} has passed.",
            )
        minutes = min(MAX_HOLD_MIN, max(1, math.ceil(contention.wait_min)))
        return Action(
            kind=ActionKind.HOLD,
            train_id=loser.id,
            at_station=station,
            hold_minutes=minutes,
            reason=f"{reason} {loser.name} is held at {station} for {minutes} min.",
        )

    @staticmethod
    def _situation(state: StateSnapshot, contention: Contention) -> str:
        when = state.sim_time + timedelta(minutes=contention.conflict.time_min - state.tick)
        return f"Conflict at {contention.conflict.location} around {when:%H:%M}."


def _arrival(state: StateSnapshot, train: TrainState, station: str) -> float | None:
    """Predicted time the train is at ``station`` (now if it is there); None if it will not come through."""
    if train.position is not None and train.position.at_station == station:
        return float(state.tick)
    return next((float(s.predicted_min) for s in train.next_stations if s.station == station), None)
