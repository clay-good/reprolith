"""Property-based validation of the logical oracle over random Boolean networks (roadmap #9).

A novel algorithm earns trust before real ground truth arrives by two independent means: a
*differential* check (the production attractor computation must agree with a deliberately different
reference implementation) and the *mathematical invariants* that define an attractor (closure,
strong connectivity, exhaustive basins, scheme-invariance of fixed points). Both are checked here
over a deterministic sweep of random networks, so a regression in `BooleanNetwork` surfaces as a
concrete failing seed rather than a silent wrong verdict. Pure stdlib — no external tool, no
fabricated data.
"""

from __future__ import annotations

import random
from itertools import product

from reprolith import BooleanNetwork, UpdateScheme

_STATES_CACHE: dict[int, list[tuple[int, ...]]] = {}


def _random_network(rng: random.Random, n: int) -> BooleanNetwork:
    """A random Boolean network: each node gets a random truth table over the n-node state."""
    names = [chr(ord("a") + i) for i in range(n)]
    order = tuple(names)  # BooleanNetwork sorts its rules; these are already sorted

    def make_rule(table: list[int]):
        def rule(state, _table=table, _order=order):
            index = 0
            for name in _order:
                index = (index << 1) | (1 if state[name] else 0)
            return _table[index]
        return rule

    return BooleanNetwork({name: make_rule([rng.randint(0, 1) for _ in range(2**n)]) for name in names})


def _all_states(net: BooleanNetwork) -> list[tuple[int, ...]]:
    n = len(net.nodes)
    if n not in _STATES_CACHE:
        _STATES_CACHE[n] = [tuple(bits) for bits in product((0, 1), repeat=n)]
    return _STATES_CACHE[n]


def _t(net: BooleanNetwork, state_dict: dict[str, int]) -> tuple[int, ...]:
    return tuple(state_dict[n] for n in net.nodes)


def _sync_step(net: BooleanNetwork, s: tuple[int, ...]) -> tuple[int, ...]:
    return _t(net, net.step(dict(zip(net.nodes, s))))


def _reference_sync_attractors(net: BooleanNetwork) -> set[frozenset[tuple[int, ...]]]:
    """An independent reference: iterate 2**n steps to land *on* the cycle, then read it off.

    Deliberately unlike the production trail-and-index method — after 2**n synchronous steps any
    trajectory is inside its cycle, so following from there until a repeat yields the exact cycle.
    """
    horizon = 2 ** len(net.nodes)
    found: set[frozenset[tuple[int, ...]]] = set()
    for start in _all_states(net):
        s = start
        for _ in range(horizon):  # walk deep enough to be certainly on the cycle
            s = _sync_step(net, s)
        cycle = [s]
        t = _sync_step(net, s)
        while t != s:
            cycle.append(t)
            t = _sync_step(net, t)
        found.add(frozenset(cycle))
    return found


def _production_ids(net: BooleanNetwork, scheme: UpdateScheme) -> set[frozenset[tuple[int, ...]]]:
    return {frozenset(_t(net, st) for st in cycle) for cycle in net.attractors(scheme)}


def _async_successors(net: BooleanNetwork, s: tuple[int, ...]) -> list[tuple[int, ...]]:
    target = _sync_step(net, s)
    out = []
    for i in range(len(s)):
        if s[i] != target[i]:
            flipped = list(s)
            flipped[i] = target[i]
            out.append(tuple(flipped))
    return out


def _reachable(net: BooleanNetwork, s: tuple[int, ...]) -> set[tuple[int, ...]]:
    seen = {s}
    stack = [s]
    while stack:
        cur = stack.pop()
        for nxt in _async_successors(net, cur):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def test_sync_attractors_match_an_independent_reference() -> None:
    rng = random.Random(20260807)
    for _ in range(400):
        net = _random_network(rng, rng.randint(1, 4))
        assert _production_ids(net, UpdateScheme.SYNCHRONOUS) == _reference_sync_attractors(net)


def test_every_state_flows_into_exactly_one_sync_attractor() -> None:
    rng = random.Random(11)
    for _ in range(200):
        net = _random_network(rng, rng.randint(1, 4))
        attractors = _production_ids(net, UpdateScheme.SYNCHRONOUS)
        for start in _all_states(net):
            s = start
            for _ in range(2 ** len(net.nodes)):
                s = _sync_step(net, s)  # certainly on the cycle now
            hits = [a for a in attractors if s in a]
            assert len(hits) == 1  # the landing state belongs to exactly one attractor


def test_sync_attractors_are_closed_cycles() -> None:
    rng = random.Random(22)
    for _ in range(200):
        net = _random_network(rng, rng.randint(1, 4))
        for attractor in net.attractors(UpdateScheme.SYNCHRONOUS):
            states = [_t(net, s) for s in attractor]
            # Each state's synchronous successor is the next state in the cycle (closure + period).
            for i, s in enumerate(states):
                assert _sync_step(net, s) == states[(i + 1) % len(states)]


def test_async_attractors_are_closed_and_strongly_connected() -> None:
    rng = random.Random(33)
    for _ in range(200):
        net = _random_network(rng, rng.randint(1, 4))
        for attractor in net.attractors(UpdateScheme.ASYNCHRONOUS):
            members = {_t(net, s) for s in attractor}
            for s in members:
                # closed: no async successor escapes the set
                assert set(_async_successors(net, s)) <= members
                # strongly connected: s reaches every member (and, by symmetry over the set, back)
                assert members <= _reachable(net, s)


def test_fixed_points_are_scheme_invariant_and_are_singleton_attractors() -> None:
    rng = random.Random(44)
    for _ in range(200):
        net = _random_network(rng, rng.randint(1, 4))
        fixed = {_t(net, fp) for fp in net.fixed_points()}
        sync_singletons = {next(iter(a)) for a in _production_ids(net, UpdateScheme.SYNCHRONOUS)
                           if len(a) == 1}
        async_singletons = {next(iter(a)) for a in _production_ids(net, UpdateScheme.ASYNCHRONOUS)
                            if len(a) == 1}
        assert fixed == sync_singletons == async_singletons
