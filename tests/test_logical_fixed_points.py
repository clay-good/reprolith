"""Reproduce the expected fixed-point count of a random Boolean network (roadmap #9).

A striking, exact result complementary to the Derrida phase transition: a random Boolean network
of unbiased functions has, on average, **exactly one** fixed point — independent of the number of
nodes N and of the connectivity K. The proof is a one-liner: each of the 2^N states is a fixed
point when every node's rule returns that state's own value there, which for unbiased rules happens
with probability 2^-N per state, so the expected count is 2^N · 2^-N = 1 for every N and K.

Where the Derrida slope tests the *dynamics* (how perturbations spread), this tests the *static*
structure the production `fixed_points()` computes, over ensembles of random networks. Non-circular:
the reference is the combinatorial theorem, a number the engine never encodes. Pure stdlib.
"""

from __future__ import annotations

import random

from reprolith import BooleanNetwork

# Sampling override, not the 5% default: an ensemble mean of a near-Poisson(1) count, so the
# tolerance follows the sample size (standard error ~0.02 for the ensembles below), not solver
# precision.
_ABS_TOL = 0.08


def _random_network(rng: random.Random, n: int, k: int) -> BooleanNetwork:
    """A random Boolean network: each node has ``k`` inputs and an unbiased random truth table."""
    names = [f"n{i}" for i in range(n)]

    def make_rule(inputs: list[str], table: list[int]):
        def rule(state, _inputs=tuple(inputs), _table=table):
            index = 0
            for name in _inputs:
                index = (index << 1) | (1 if state[name] else 0)
            return _table[index]
        return rule

    return BooleanNetwork({
        name: make_rule(rng.sample(names, k), [rng.randint(0, 1) for _ in range(2**k)])
        for name in names
    })


def _mean_fixed_points(rng: random.Random, *, n: int, k: int, nets: int) -> float:
    return sum(len(_random_network(rng, n, k).fixed_points()) for _ in range(nets)) / nets


def test_expected_fixed_point_count_is_one_independent_of_size() -> None:
    # Vary the number of nodes with fully random node functions (k = n): the ensemble mean stays 1.
    rng = random.Random(20260807)
    for n in (2, 3, 4, 5):
        mean = _mean_fixed_points(rng, n=n, k=n, nets=2500)
        assert abs(mean - 1.0) < _ABS_TOL, f"N={n}: mean fixed points {mean:.3f} != 1"


def test_expected_fixed_point_count_is_independent_of_connectivity() -> None:
    # Hold N fixed and vary the in-degree K from ordered (1) to chaotic (5): the *dynamics* change
    # completely across this range (Derrida), yet the expected number of fixed points is still 1.
    rng = random.Random(11)
    for k in (1, 2, 3, 4, 5):
        mean = _mean_fixed_points(rng, n=6, k=k, nets=2500)
        assert abs(mean - 1.0) < _ABS_TOL, f"K={k}: mean fixed points {mean:.3f} != 1"
