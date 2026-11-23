"""CP-SAT optimizer: optimality against brute force, constraints, fallback, determinism, fairness."""

import itertools
import random

import pytest
from toys import overtake_at_dvg, snapshot

from app.models.corridor import build_corridor
from app.models.schemas import ActionKind, StrategyName
from app.optimizer.closed_loop import predicted_snapshot, run_closed_loop
from app.optimizer.conflicts import ConflictDetector
from app.optimizer.cpsat import strategy as strategy_module
from app.optimizer.cpsat.problem import Params, PGroup, Problem, PTrain, PVisit, build_components
from app.optimizer.cpsat.solver import SCALE, Plan, solve
from app.optimizer.cpsat.strategy import CpSatStrategy
from app.optimizer.priority import PriorityRule
from app.optimizer.registry import make_strategy
from app.simulation.disruptions import Intensity
from app.simulation.scenario import Scenario


@pytest.fixture(scope="module")
def network():
    return build_corridor()


# ---- an independent evaluator of the model, used for brute force -----------------------------------------
def cumulative(problem: Problem, holds, waits) -> dict:
    """Shift of every (train, hop): the sum of hold and wait over the hops so far."""
    shift = {}
    for t, train in enumerate(problem.trains):
        total = 0
        for h in range(len(train.hold_caps)):
            total += holds.get((t, h), 0) + waits.get((t, h), 0)
            shift[t, h] = total
    return shift


def feasible(problem: Problem, holds, waits) -> bool:
    """Return True if every group can be ordered (leader first, or follower first by holding the leader)."""
    shift = cumulative(problem, holds, waits)
    for group in problem.groups:
        lead, follow = group.leader, group.follower
        normal = flipped = True
        for lv, fv in group.pairs:
            a, b = problem.visits[lv], problem.visits[fv]
            s_a, s_b = shift[lead, a.hop], shift[follow, b.hop]
            normal &= a.exit + s_a + problem.headway <= b.enter + s_b
            flipped &= b.exit + s_b + problem.headway <= a.enter + s_a
        held = sum(holds.get((lead, h), 0) for h in range(group.leader_hop + 1))
        no_wait = all(waits.get((lead, h), 0) == 0 for h in range(group.leader_hop + 1))
        if not (normal or (flipped and held >= 1 and no_wait)):
            return False
    return True


def cost(problem: Problem, params: Params, holds, waits) -> int:
    """The objective of the model, written out again."""
    shift = cumulative(problem, holds, waits)
    total = 0
    for t, train in enumerate(problem.trains):
        delay = max(0, train.final_delay + shift[t, len(train.hold_caps) - 1])
        total += SCALE * train.priority * delay
    total += round(params.action_penalty * SCALE) * sum(1 for v in holds.values() if v > 0)
    return total + round(params.hold_penalty * SCALE) * sum(holds.values())


def brute_force(problem: Problem, params: Params) -> int:
    """Try every hold and wait combination; return the cheapest feasible cost."""
    slots = [(t, h) for t, train in enumerate(problem.trains) for h in range(len(train.hold_caps))]
    domains = []
    for t, h in slots:
        domains.append(list(range(problem.trains[t].hold_caps[h] + 1)))
        domains.append(list(range(params.wait_cap_min + 1)))
    best = None
    for values in itertools.product(*domains):
        holds = {slot: values[2 * k] for k, slot in enumerate(slots)}
        waits = {slot: values[2 * k + 1] for k, slot in enumerate(slots)}
        if feasible(problem, holds, waits):
            value = cost(problem, params, holds, waits)
            best = value if best is None else min(best, value)
    assert best is not None
    return best


def random_problem(rng: random.Random, trains: int, hops: int, max_cap: int) -> Problem:
    """A tiny random problem: each hop has its own resource; trains use it at random times."""
    ptrains = tuple(
        PTrain(f"T{k}", rng.randint(1, 4), tuple(rng.randint(0, max_cap) for _ in range(hops)), rng.randint(-2, 8))
        for k in range(trains)
    )
    visits: list[PVisit] = []
    for t in range(trains):
        for hop in range(hops):
            if rng.random() < 0.85:
                enter = rng.randint(0, 8) + 10 * hop
                visits.append(PVisit(t, hop, f"R{hop}", enter, enter + rng.randint(2, 5)))
    groups = []
    for hop in range(hops):
        here = [(k, v) for k, v in enumerate(visits) if v.hop == hop]
        for (ka, a), (kb, b) in itertools.combinations(here, 2):
            lead, follow = ((ka, a), (kb, b)) if (a.enter, a.train) <= (b.enter, b.train) else ((kb, b), (ka, a))
            groups.append(PGroup(lead[1].train, follow[1].train, hop, ((lead[0], follow[0]),)))
    return Problem(ptrains, tuple(visits), tuple(groups), 1)


# ---- optimality ----------------------------------------------------------------------------------------
def test_slow_leader_gives_way_to_a_priority_follower() -> None:
    """Freight (priority 1) is first on the track, a premium train (4) right behind: the freight is held."""
    params = Params()
    trains = (PTrain("freight", 1, (10,), 0), PTrain("premium", 4, (10,), 0))
    visits = (PVisit(0, 0, "R", 0, 10), PVisit(1, 0, "R", 2, 8))
    problem = Problem(trains, visits, (PGroup(0, 1, 0, ((0, 1),)),), 1)
    plan = solve(problem, params)
    assert plan.status == "OPTIMAL" and plan.flipped == (0,)
    assert plan.holds == {(0, 0): 9}  # freight waits until the premium train has gone (+ headway)
    assert plan.delays == (9, 0)
    assert plan.cost == brute_force(problem, params)


def test_a_high_priority_leader_is_left_alone() -> None:
    params = Params()
    trains = (PTrain("premium", 4, (10,), 0), PTrain("freight", 1, (10,), 0))
    visits = (PVisit(0, 0, "R", 0, 10), PVisit(1, 0, "R", 2, 8))
    problem = Problem(trains, visits, (PGroup(0, 1, 0, ((0, 1),)),), 1)
    plan = solve(problem, params)
    assert plan.holds == {} and plan.flipped == ()
    assert plan.cost == brute_force(problem, params)


def test_no_needless_action_for_a_tiny_gain() -> None:
    """Swapping saves 1 weighted minute but an action costs more, so nothing is done."""
    trains = (PTrain("a", 2, (10,), 0), PTrain("b", 3, (10,), 0))
    visits = (PVisit(0, 0, "R", 0, 3), PVisit(1, 0, "R", 2, 5))
    problem = Problem(trains, visits, (PGroup(0, 1, 0, ((0, 1),)),), 1)
    assert solve(problem, Params()).holds == {}


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("trains", [2, 3])
def test_matches_brute_force_on_random_tiny_problems(seed, trains) -> None:
    rng = random.Random(1000 * trains + seed)
    params = Params(wait_cap_min=7, action_penalty=rng.choice([0.5, 3.0, 10.0]), hold_penalty=rng.choice([0.0, 0.5]))
    problem = random_problem(rng, trains, hops=1, max_cap=3)
    plan = solve(problem, params)
    assert plan.status == "OPTIMAL"
    assert plan.cost == brute_force(problem, params)
    assert feasible(problem, plan.holds, plan.waits)


@pytest.mark.parametrize("seed", range(6))
def test_matches_brute_force_with_two_hops(seed) -> None:
    rng = random.Random(77 + seed)
    params = Params(wait_cap_min=5, action_penalty=2.0, hold_penalty=0.5)
    problem = random_problem(rng, trains=2, hops=2, max_cap=2)
    plan = solve(problem, params)
    assert plan.cost == brute_force(problem, params)


@pytest.mark.parametrize("seed", range(8))
def test_plans_respect_the_caps_and_the_constraints(seed) -> None:
    rng = random.Random(seed)
    problem = random_problem(rng, trains=4, hops=2, max_cap=6)
    plan = solve(problem, Params())
    assert plan.usable and feasible(problem, plan.holds, plan.waits)
    for (t, h), minutes in plan.holds.items():
        assert 0 < minutes <= problem.trains[t].hold_caps[h]


def test_a_train_that_cannot_be_held_is_never_held() -> None:
    trains = (PTrain("freight", 1, (0,), 0), PTrain("premium", 4, (10,), 0))  # the freight has left its station
    visits = (PVisit(0, 0, "R", 0, 10), PVisit(1, 0, "R", 2, 8))
    plan = solve(Problem(trains, visits, (PGroup(0, 1, 0, ((0, 1),)),), 1), Params())
    assert plan.holds.get((0, 0), 0) == 0 and plan.flipped == ()
    assert plan.delays[1] > 0  # so the premium train simply waits behind it


def test_headway_is_respected() -> None:
    trains = (PTrain("a", 2, (0,), 0), PTrain("b", 2, (0,), 0))
    visits = (PVisit(0, 0, "R", 0, 5), PVisit(1, 0, "R", 3, 8))
    problem = Problem(trains, visits, (PGroup(0, 1, 0, ((0, 1),)),), headway=3)
    plan = solve(problem, Params())
    assert plan.waits == {(1, 0): 5}  # exit 5 + headway 3 = 8, enter 3 -> wait 5


# ---- building problems from real snapshots -------------------------------------------------------------
def test_overtake_toy_gives_a_precedence(network) -> None:
    state = overtake_at_dvg()
    conflicts = ConflictDetector(network).detect(state)
    (proposal,) = CpSatStrategy(network).propose(state, conflicts)
    action = proposal.action
    assert action.kind is ActionKind.PRECEDENCE and action.train_id == "F1" and action.other_train_id == "E1"
    assert action.reason.startswith("CP-SAT plan:") and "saves" in action.reason and "weighted" in action.reason
    assert proposal.conflict_ids == [conflicts[0].id] and proposal.expected_delay_saved_min > 0


def test_no_conflicts_no_actions(network) -> None:
    assert CpSatStrategy(network).propose(snapshot([]), []) == []


def test_unrelated_trains_end_up_in_separate_components(network) -> None:
    state = overtake_at_dvg()
    detector = ConflictDetector(network)
    components = build_components(state, detector.timelines(state), {"F1", "E1"}, Params())
    assert len(components) == 1 and {t.id for t in components[0].problem.trains} == {"F1", "E1"}
    assert build_components(state, detector.timelines(state), set(), Params()) == []


def test_a_train_that_left_its_station_gets_no_hold(network) -> None:
    state = overtake_at_dvg()
    detector = ConflictDetector(network)
    (component,) = build_components(state, detector.timelines(state), {"F1", "E1"}, Params())
    names = [t.id for t in component.problem.trains]
    express = names.index("E1")
    assert component.hops[express, 0].left and component.problem.trains[express].hold_caps[0] == 0


# ---- fallback ------------------------------------------------------------------------------------------
def bad_plan(status: str) -> Plan:
    return Plan(status, {}, {}, (), (), 0, 0, 0)


@pytest.mark.parametrize("failure", ["UNKNOWN", "INFEASIBLE", "raise"])
def test_fallback_to_the_priority_rule(network, monkeypatch, failure) -> None:
    def fake_solve(*args, **kwargs):
        if failure == "raise":
            raise RuntimeError("boom")
        return bad_plan(failure)

    monkeypatch.setattr(strategy_module, "solve", fake_solve)
    state = overtake_at_dvg()
    conflicts = ConflictDetector(network).detect(state)
    strategy = CpSatStrategy(network)
    proposals = strategy.propose(state, conflicts)
    expected = PriorityRule(network).propose(state, conflicts)
    assert [p.action.train_id for p in proposals] == [p.action.train_id for p in expected] != []
    assert [p.action.kind for p in proposals] == [p.action.kind for p in expected]
    assert all("fallback to the priority rule" in p.action.reason for p in proposals)
    assert all(p.action.reason.endswith(e.action.reason) for p, e in zip(proposals, expected, strict=True))
    assert strategy.stats["fallbacks"] == 1


def test_a_real_timeout_with_no_solution_falls_back(network) -> None:
    """With no time at all CP-SAT may return nothing; whatever it returns, the strategy still answers."""
    state = overtake_at_dvg()
    conflicts = ConflictDetector(network).detect(state)
    strategy = CpSatStrategy(network, params=Params(time_limit_s=1e-9, det_time_limit=1e-9))
    proposals = strategy.propose(state, conflicts)
    assert proposals and all(p.action.reason for p in proposals)


# ---- whole days ----------------------------------------------------------------------------------------
def test_registry_builds_it(network) -> None:
    strategy = make_strategy(StrategyName.CPSAT, network)
    assert isinstance(strategy, CpSatStrategy) and strategy.name is StrategyName.CPSAT == "cpsat"


def day_proposals(network, seed=3, intensity=Intensity.MEDIUM, params=None):
    """Run a day with the optimizer applying its actions; return every non-empty proposal list with its tick."""
    engine = Scenario(seed=seed, intensity=intensity).build(network)
    strategy = CpSatStrategy(network, params=params)
    detector = ConflictDetector(network)
    seen = []
    handled: set[str] = set()
    while not engine.is_done():
        state = predicted_snapshot(engine, network, None)
        conflicts = detector.detect(state)
        for proposal in strategy.propose(state, conflicts):
            seen.append((state, proposal))
            if handled.isdisjoint(proposal.conflict_ids):
                try:
                    engine.apply_action(proposal.action)
                except ValueError:
                    continue
                handled.update(proposal.conflict_ids)
        engine.step()
    return seen


def test_actions_are_valid_and_never_exceed_the_maximum_hold(network) -> None:
    seen = day_proposals(network, seed=3, intensity=Intensity.MEDIUM, params=Params(max_hold_min=12))
    assert seen
    for state, proposal in seen:
        action = proposal.action
        train = next(t for t in state.trains if t.id == action.train_id)
        if action.kind is ActionKind.HOLD:
            assert 1 <= (action.hold_minutes or 0) <= 12
        # the train has not left the station yet: it is there now, or the station is still ahead of it
        ahead = {s.station for s in train.next_stations}
        assert (train.position is not None and train.position.at_station == action.at_station) or (
            action.at_station in ahead
        )
        assert action.reason and proposal.conflict_ids


def test_no_stacked_holds_on_the_next_tick(network) -> None:
    """The strategy is stateless and repeats a proposal on the next tick; the loop must still act only once."""
    result = run_closed_loop(
        Scenario(seed=3, intensity=Intensity.HIGH), CpSatStrategy(network), network
    )
    slots = [(a.train_id, a.at_station) for a in result.applied]
    assert len(slots) == len(set(slots))
    # repeating the very same snapshot gives the very same proposal, so the loop's once-per-conflict guard works
    state = overtake_at_dvg()
    conflicts = ConflictDetector(network).detect(state)
    strategy = CpSatStrategy(network)
    assert strategy.propose(state, conflicts) == strategy.propose(state, conflicts)


def test_each_conflict_is_settled_once_even_though_proposals_repeat(network) -> None:
    engine = Scenario(seed=3, intensity=Intensity.MEDIUM).build(network)
    strategy = CpSatStrategy(network)
    detector = ConflictDetector(network)
    proposed_ticks: dict[tuple[str, str], list[int]] = {}
    while not engine.is_done():
        state = predicted_snapshot(engine, network, None)
        for p in strategy.propose(state, detector.detect(state)):
            proposed_ticks.setdefault((p.action.train_id, p.action.at_station), []).append(state.tick)
        engine.step()
    assert any(len(ticks) > 1 for ticks in proposed_ticks.values())  # proposals do repeat ...
    result = run_closed_loop(Scenario(seed=3, intensity=Intensity.MEDIUM), CpSatStrategy(network), network)
    assert len({(a.train_id, a.at_station) for a in result.applied}) == len(result.applied)  # ... but are applied once


def test_deterministic_with_a_fixed_seed(network) -> None:
    runs = [
        run_closed_loop(Scenario(seed=7, intensity=Intensity.HIGH), CpSatStrategy(network), network)
        for _ in range(2)
    ]
    assert runs[0].applied == runs[1].applied and runs[0].kpis == runs[1].kpis


def test_cpsat_faces_the_same_day_as_priority(network) -> None:
    scenario = Scenario(seed=11, intensity=Intensity.HIGH)
    a = run_closed_loop(scenario, make_strategy(StrategyName.PRIORITY, network), network)
    b = run_closed_loop(scenario, make_strategy(StrategyName.CPSAT, network), network)
    assert a.disruptions == b.disruptions and a.departures == b.departures
    assert b.kpis.strategy is StrategyName.CPSAT and b.kpis.trains_finished == b.kpis.trains_total == 25


def test_the_strategy_gets_no_extra_information(network) -> None:
    """propose() only takes the snapshot and the conflicts: identical inputs give identical answers."""
    engine = Scenario(seed=3, intensity=Intensity.HIGH).build(network)
    detector = ConflictDetector(network)
    for _ in range(400):
        engine.step()
    state = predicted_snapshot(engine, network, None)
    conflicts = detector.detect(state)
    first = CpSatStrategy(network).propose(state, conflicts)
    engine.step()  # the engine moved on, but the strategy only looks at the old snapshot
    assert CpSatStrategy(network).propose(state, conflicts) == first


def test_ties_on_entry_time_go_to_the_train_that_leaves_first() -> None:
    """Regression: three trains entering together were ordered in a circle, which made the model infeasible."""
    from app.models.network import Direction
    from app.optimizer.cpsat.problem import _leads, _Raw

    long_one = _Raw("1", 0, "R", 700, 706, Direction.REVERSE)
    short_one = _Raw("2", 0, "R", 700, 703, Direction.REVERSE)
    assert _leads("2", "1", [(short_one, long_one)]) is True  # "2" leaves first although its id is bigger
    assert _leads("1", "2", [(long_one, short_one)]) is False
