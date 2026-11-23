"""First-come-first-served: the train that reaches the contested track first goes first; the other waits."""

from app.models.schemas import StrategyName, TrainState
from app.optimizer.conflicts import Contention
from app.optimizer.resolve import RuleStrategy


class FirstComeFirstServed(RuleStrategy):
    """Order of arrival decides, whatever the trains are."""

    name = StrategyName.FCFS
    acts_in_natural_order = True  # the later train is told to wait
    uses_precedence = False  # a plain hold for the predicted wait

    def goes_first(self, a: TrainState, b: TrainState, contention: Contention) -> TrainState:
        """Return ``a``: by definition it is the train that arrives first."""
        return a

    def rule_text(self, winner: TrainState, loser: TrainState) -> str:
        """Name the rule."""
        return f"First come, first served: {winner.name} arrives first."
