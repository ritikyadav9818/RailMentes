"""The CP-SAT model: decide holds and precedence for one ``Problem``.

Variables (all whole minutes), for every train ``t`` and hop ``h``:
    * ``hold[t,h]``  extra minutes the train is held at the station where the hop starts (an ACTION).
    * ``wait[t,h]``  extra minutes the train simply has to wait for a free track (NOT an action; this is
      what happens anyway when two trains want the same track, and it keeps the model always feasible).
    * ``shift[t,h]`` = sum of hold + wait over hops 0..h: how much later than predicted every visit
      of the hop happens.
For every group (leader, follower) there is one yes/no variable ``leader_first``.

Constraints:
    * Exclusive use: for each pair of visits on one resource, one train exits (plus the headway) before the
      other enters. The order is the group's ``leader_first`` choice, the same for all its blocks, so trains
      never pass each other between stations.
    * Single line: head-on trains are separated the same way (the problem contains a visit for the whole
      segment).
    * The follower may only go first if the leader is held (hold >= 1 before the resource, and no mere
      waiting up to that point: the leader's whole delay is then a hold). Our only tool is to make the
      leader wait at a station.
    * hold <= cap (maximum hold per action; 0 if the train has already left the station).

Objective (minimise): sum of priority x predicted final delay + ``action_penalty`` per hold + ``hold_penalty``
per hold minute. The delay of a train is ``max(0, predicted delay + shift)`` at the end of the window, so a
train that has slack does not pay for being shifted.

Determinism: one worker, fixed seed, and the effort limit is CP-SAT's *deterministic time*, not wall-clock.
A wall-clock limit is only a backstop (it is the only part that can differ between machines).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.optimizer.cpsat.problem import Params, Problem

SCALE = 20  # integer cost units per priority-weighted delay minute
STATUS_OK = ("OPTIMAL", "FEASIBLE")


@dataclass(frozen=True)
class Plan:
    """The solver's answer for one problem."""

    status: str  # OPTIMAL, FEASIBLE (best found within the limit), or UNKNOWN / INFEASIBLE / MODEL_INVALID
    holds: Mapping[tuple[int, int], int]  # (train index, hop) -> extra hold minutes (only > 0)
    waits: Mapping[tuple[int, int], int]  # (train index, hop) -> passive waiting minutes (only > 0)
    flipped: tuple[int, ...]  # group indexes where the follower goes first
    delays: tuple[int, ...]  # predicted final delay of each train under the plan (min, never negative)
    weighted_delay: int  # sum of priority x delay (min)
    plain_delay: int  # sum of delay (min)
    cost: int  # objective value (scaled)

    @property
    def usable(self) -> bool:
        """Return True if the plan can be acted on."""
        return self.status in STATUS_OK


def solve(
    problem: Problem,
    params: Params,
    caps: Mapping[tuple[int, int], int] | None = None,
    pinned: Mapping[tuple[int, int], int] | None = None,
) -> Plan:
    """Solve ``problem``.

    ``caps`` overrides the hold cap of (train, hop) slots (0 = no hold allowed); ``pinned`` fixes the hold of
    slots to an exact value. Both are used to compare the plan with "do nothing" and "without this action".
    """
    model = cp_model.CpModel()
    hold, wait, used = {}, {}, {}
    wait_cap = _wait_cap(problem, params)
    for t, train in enumerate(problem.trains):
        for h, cap in enumerate(train.hold_caps):
            cap = (caps or {}).get((t, h), cap)
            hold[t, h] = model.new_int_var(0, cap, f"hold_{t}_{h}")
            wait[t, h] = model.new_int_var(0, wait_cap, f"wait_{t}_{h}")
            used[t, h] = model.new_bool_var(f"used_{t}_{h}")
            model.add(hold[t, h] <= cap * used[t, h])
            model.add(hold[t, h] >= used[t, h])
            if pinned and (t, h) in pinned:
                model.add(hold[t, h] == pinned[t, h])
    shift = {}
    for t, train in enumerate(problem.trains):
        total = 0
        for h in range(len(train.hold_caps)):
            total = total + hold[t, h] + wait[t, h]
            shift[t, h] = total
    first = [model.new_bool_var(f"leader_first_{g}") for g in range(len(problem.groups))]
    for g, group in enumerate(problem.groups):
        _add_group(model, problem, group, first[g], shift, hold, wait)
    delay_vars = []
    for t, train in enumerate(problem.trains):
        last = len(train.hold_caps) - 1
        z = model.new_int_var(0, 10_000, f"delay_{t}")
        model.add(z >= train.final_delay + shift[t, last])
        delay_vars.append(z)
    weighted = sum(problem.trains[t].priority * z for t, z in enumerate(delay_vars))
    action_cost = round(params.action_penalty * SCALE)
    hold_cost = round(params.hold_penalty * SCALE)
    model.minimize(SCALE * weighted + action_cost * sum(used.values()) + hold_cost * sum(hold.values()))
    for var in first:
        model.add_hint(var, 1)

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.linearization_level = (
        2  # much stronger bounds for these big-M style models (60x faster here)
    )
    solver.parameters.max_time_in_seconds = params.time_limit_s
    solver.parameters.max_deterministic_time = params.det_time_limit
    status = solver.solve(model)
    name = solver.status_name(status)
    if name not in STATUS_OK:
        return Plan(name, {}, {}, (), (), 0, 0, 0)
    delays = tuple(solver.value(z) for z in delay_vars)
    holds = {slot: solver.value(v) for slot, v in hold.items() if solver.value(v) > 0}
    return Plan(
        name,
        holds,
        {slot: solver.value(v) for slot, v in wait.items() if solver.value(v) > 0},
        tuple(g for g, var in enumerate(first) if not solver.value(var)),
        delays,
        sum(problem.trains[t].priority * d for t, d in enumerate(delays)),
        sum(delays),
        round(solver.objective_value),
    )


def _add_group(model, problem, group, first, shift, hold, wait) -> None:  # noqa: ANN001
    """Add the exclusive-use constraints of one leader/follower group."""
    lead, follow, headway = group.leader, group.follower, problem.headway
    for lv, fv in group.pairs:
        a, b = problem.visits[lv], problem.visits[fv]
        s_a, s_b = shift[lead, a.hop], shift[follow, b.hop]
        model.add(a.exit + s_a + headway <= b.enter + s_b).only_enforce_if(first)
        model.add(b.exit + s_b + headway <= a.enter + s_a).only_enforce_if(first.negated())
    # Going against the natural order is only possible by holding the leader at a station before the resource.
    held_before = sum(hold[lead, h] for h in range(group.leader_hop + 1))
    model.add(held_before >= 1).only_enforce_if(first.negated())
    for h in range(group.leader_hop + 1):  # no passive waiting before it: the delay must be a real hold
        model.add(wait[lead, h] == 0).only_enforce_if(first.negated())


def _wait_cap(problem: Problem, params: Params) -> int:
    """Longest passive wait that can pay off: more than the whole window plus the headways is pointless."""
    if not problem.visits:
        return 0
    span = max(v.exit for v in problem.visits) - min(v.enter for v in problem.visits)
    return min(params.wait_cap_min, span + problem.headway * len(problem.trains))
