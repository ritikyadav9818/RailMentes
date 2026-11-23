"""No control: the baseline. Conflicts are left to sort themselves out through the normal block rules."""

from app.models.schemas import Action, Conflict, StateSnapshot, StrategyName
from app.optimizer.strategy import Strategy


class NoControl(Strategy):
    """Does nothing, so every strategy shares one interface and the comparison has a true baseline."""

    name = StrategyName.NO_CONTROL

    def decide(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Action]:
        """Return no actions."""
        return []
