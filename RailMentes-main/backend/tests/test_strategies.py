"""NoControl, FCFS and priority strategies on hand-built toy snapshots."""

import pytest
from toys import at_station, opposing_on_single_line, overtake_at_dvg, snapshot, stop, train

from app.models.corridor import build_corridor
from app.models.schemas import Action, ActionKind, StrategyName
from app.models.train import TrainCategory
from app.optimizer.conflicts import ConflictDetector
from app.optimizer.fcfs import FirstComeFirstServed
from app.optimizer.no_control import NoControl
from app.optimizer.priority import PriorityRule
from app.optimizer.registry import IMPLEMENTED_STRATEGIES, make_strategy


@pytest.fixture(scope="module")
def network():
    return build_corridor()


def decide(strategy, state, network):
    return strategy.decide(state, ConflictDetector(network).detect(state))


# ---- no control ---------------------------------------------------------------------------------
def test_no_control_does_nothing(network) -> None:
    state = opposing_on_single_line()
    assert decide(NoControl(), state, network) == []
    assert NoControl().name is StrategyName.NO_CONTROL


# ---- FCFS ------------------------------------------------------------------------------------------------
def test_fcfs_holds_the_train_that_arrives_second(network) -> None:
    state = overtake_at_dvg()  # the freight (F1) reaches DVG-KLP-1 first; the express (E1) comes after
    (action,) = decide(FirstComeFirstServed(network), state, network)
    Action.model_validate(action.model_dump())
    assert action.kind is ActionKind.HOLD and action.train_id == "E1" and action.at_station == "DVG"
    assert 1 <= (action.hold_minutes or 0) <= 30
    assert "First come, first served" in action.reason and "F1" in action.reason


def test_fcfs_on_a_meeting_holds_the_later_one_at_its_station(network) -> None:
    (action,) = decide(FirstComeFirstServed(network), opposing_on_single_line(), network)
    # A and B enter at the same time; ties go to the train id, so B is held at GNK for the wait
    assert (action.kind, action.train_id, action.at_station) == (ActionKind.HOLD, "B", "GNK")
    assert action.hold_minutes == 20


def test_fcfs_waits_until_the_train_is_about_to_leave(network) -> None:
    far = overtake_at_dvg(shift=20)  # everything happens 20 minutes later
    assert decide(FirstComeFirstServed(network), far, network) == []


# ---- priority --------------------------------------------------------------------------------------
def test_priority_lets_the_express_pass_the_freight(network) -> None:
    state = overtake_at_dvg()
    (action,) = decide(PriorityRule(network), state, network)
    Action.model_validate(action.model_dump())
    assert action.kind is ActionKind.PRECEDENCE
    assert (action.train_id, action.at_station, action.other_train_id) == ("F1", "DVG", "E1")
    assert "outranks" in action.reason and "priority" in action.reason.lower()


def test_priority_does_nothing_when_the_order_is_already_right(network) -> None:
    # the express is first at the contested track anyway
    express = train("E1", TrainCategory.EXPRESS, at_station("DVG"), [stop("KLP", 19)])
    freight = train("F1", TrainCategory.FREIGHT, at_station("DVG"), [stop("KLP", 36)])
    state = snapshot([express, freight])
    assert ConflictDetector(network).detect(state)  # there is a conflict ...
    assert decide(PriorityRule(network), state, network) == []  # ... but the express already goes first


def test_priority_does_not_wait_for_a_far_away_train(network) -> None:
    # the express reaches DVG only 40 minutes after the freight wants to leave: not worth holding the freight
    state = overtake_at_dvg()
    express = state.trains[1].model_copy(
        update={"next_stations": [stop("DVG", 40, will_stop=False), stop("KLP", 59)]}
    )
    late = snapshot([state.trains[0], express])
    assert all(a.kind is not ActionKind.PRECEDENCE for a in decide(PriorityRule(network), late, network))


def test_priority_tie_goes_to_the_more_delayed_train(network) -> None:
    strategy = PriorityRule(network)
    state = overtake_at_dvg()
    contention = ConflictDetector(network).find(state)[0]
    a = train("T1", TrainCategory.EXPRESS, None, [], delay=4.0)
    b = train("T2", TrainCategory.EXPRESS, None, [], delay=9.0)
    assert strategy.goes_first(a, b, contention) is b
    assert strategy.goes_first(b, a, contention) is b
    same = train("T3", TrainCategory.EXPRESS, None, [], delay=4.0)
    assert strategy.goes_first(a, same, contention) is a  # still tied: the first to arrive
    freight = train("T4", TrainCategory.FREIGHT, None, [], delay=90.0)
    assert strategy.goes_first(freight, a, contention) is a  # priority beats delay
    assert "more delayed" in strategy.rule_text(b, a)


# ---- shared ------------------------------------------------------------------------------------------
def test_strategies_return_the_conflict_they_resolve(network) -> None:
    state = overtake_at_dvg()
    conflicts = ConflictDetector(network).detect(state)
    for strategy in (FirstComeFirstServed(network), PriorityRule(network)):
        (proposal,) = strategy.propose(state, conflicts)
        assert proposal.conflict_ids == [conflicts[0].id]
    (priority,) = PriorityRule(network).propose(state, conflicts)
    assert priority.expected_delay_saved_min > 0  # the express avoids waiting behind the freight
    (fcfs,) = FirstComeFirstServed(network).propose(state, conflicts)
    assert fcfs.expected_delay_saved_min == 0  # FCFS only keeps the natural order


def test_no_conflicts_no_actions(network) -> None:
    for strategy in (FirstComeFirstServed(network), PriorityRule(network)):
        assert strategy.decide(snapshot([]), []) == []


def test_registry(network) -> None:
    assert [make_strategy(name, network).name for name in IMPLEMENTED_STRATEGIES] == list(IMPLEMENTED_STRATEGIES)
    assert StrategyName.CPSAT in IMPLEMENTED_STRATEGIES
