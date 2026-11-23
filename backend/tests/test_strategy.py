"""The Strategy interface is abstract: it cannot be used without an implementation."""

import pytest

from app.models.schemas import Action, Conflict, StateSnapshot, StrategyName
from app.optimizer.strategy import Strategy


def test_strategy_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Strategy()  # type: ignore[abstract]


def test_subclass_must_implement_decide() -> None:
    class Incomplete(Strategy):
        name = StrategyName.FCFS

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_minimal_implementation_works() -> None:
    class DoNothing(Strategy):
        name = StrategyName.NO_CONTROL

        def decide(self, state: StateSnapshot, conflicts: list[Conflict]) -> list[Action]:
            return []

    assert DoNothing().name is StrategyName.NO_CONTROL
