"""Strategy interface: the single seam every control strategy plugs into.

NoControl, FCFS, Priority and the CP-SAT optimizer (later phases) all implement
``Strategy``. The live engine and the benchmark call the same method, which keeps
the strategy comparison honest.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.schemas import Action, Conflict, StateSnapshot, StrategyName


@dataclass(frozen=True)
class Proposal:
    """An action plus the context the alerts feed needs (which conflicts it handles, what it saves)."""

    action: Action
    conflict_ids: list[str] = field(default_factory=list)
    expected_delay_saved_min: float = 0.0


class Strategy(ABC):
    """Turns the current state and detected conflicts into control actions."""

    name: StrategyName

    @abstractmethod
    def decide(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Action]:
        """Return the actions to take now (empty list = do nothing)."""

    def propose(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Proposal]:
        """Return the same actions as ``decide``, with context for the controller (override to add detail)."""
        return [Proposal(action) for action in self.decide(state, conflicts)]
