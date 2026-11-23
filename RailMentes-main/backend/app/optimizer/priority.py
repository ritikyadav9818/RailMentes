"""Priority rule: the higher-priority train goes first; a tie goes to the train that is more delayed."""

from app.models.schemas import StrategyName, TrainState
from app.optimizer.conflicts import Contention
from app.optimizer.resolve import RuleStrategy


class PriorityRule(RuleStrategy):
    """Premium > express > passenger > freight. Equal priority: the more delayed train goes first."""

    name = StrategyName.PRIORITY

    def goes_first(self, a: TrainState, b: TrainState, contention: Contention) -> TrainState:
        """Return the higher priority; on a tie the larger delay; still tied: ``a`` (arrives first)."""
        if a.priority != b.priority:
            return a if a.priority > b.priority else b
        if a.delay_min != b.delay_min:
            return a if a.delay_min > b.delay_min else b
        return a

    def rule_text(self, winner: TrainState, loser: TrainState) -> str:
        """Name the rule and the reason it applied."""
        if winner.priority != loser.priority:
            return (
                f"Priority rule: {winner.name} (priority {winner.priority}) "
                f"outranks {loser.name} ({loser.priority})."
            )
        if winner.delay_min != loser.delay_min:
            return (
                f"Priority rule: equal priority, {winner.name} is more delayed ({winner.delay_min:.0f} min)."
            )
        return f"Priority rule: equal priority and delay, {winner.name} arrives first."
