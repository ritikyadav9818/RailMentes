"""Which strategies exist, and how to build them by name."""

from typing import Final

from app.models.network import Network
from app.models.schemas import StrategyName
from app.optimizer.conflicts import DEFAULT_LOOKAHEAD_MIN
from app.optimizer.cpsat.strategy import CpSatStrategy
from app.optimizer.fcfs import FirstComeFirstServed
from app.optimizer.no_control import NoControl
from app.optimizer.priority import PriorityRule
from app.optimizer.strategy import Strategy

IMPLEMENTED_STRATEGIES: Final = (
    StrategyName.NO_CONTROL,
    StrategyName.FCFS,
    StrategyName.PRIORITY,
    StrategyName.CPSAT,
)


def make_strategy(
    name: StrategyName, network: Network, lookahead_min: int = DEFAULT_LOOKAHEAD_MIN
) -> Strategy:
    """Build the strategy called ``name``. Raises ValueError for one that is not implemented yet."""
    if name is StrategyName.NO_CONTROL:
        return NoControl()
    if name is StrategyName.FCFS:
        return FirstComeFirstServed(network, lookahead_min)
    if name is StrategyName.PRIORITY:
        return PriorityRule(network, lookahead_min)
    if name is StrategyName.CPSAT:
        return CpSatStrategy(network, lookahead_min)
    raise ValueError(f"strategy '{name.value}' is not implemented yet")
