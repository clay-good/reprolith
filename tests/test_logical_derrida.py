"""Reproduce the order–chaos phase transition of random Boolean networks (roadmap #9).

The single most famous quantitative result in Boolean-network theory is Kauffman's critical
connectivity: a random network of unbiased Boolean functions is *ordered* (small perturbations
die out) when each node has one input, *chaotic* (perturbations spread) when it has three, and
sits exactly at the *critical* boundary at two inputs. Derrida & Pomeau (1986) made this exact
with the annealed approximation: the slope at the origin of the Derrida map — the expected
Hamming distance one synchronous step after a single-node perturbation — is

    s = 2·p·(1−p)·K

for K inputs per node and bias p (the fraction of 1s in the truth tables). Order/criticality/
chaos is s < 1 / s = 1 / s > 1, so at p = ½ the critical connectivity is Kc = 2.

This reproduces that slope *empirically* from the production synchronous update
(:meth:`BooleanNetwork.step`) over ensembles of random K-input networks, and matches it to the
closed form. Non-circular by construction: the reference is Derrida's theorem, a mathematical
law this engine never encodes — the step function knows nothing of connectivity or sensitivity.
Pure stdlib, no external tool, no fabricated data.
"""

from __future__ import annotations

import random

from reprolith import BooleanNetwork

# Sampling override, not the 5% default: the Derrida slope is an *ensemble mean* estimated by Monte
# Carlo, so the tolerance is set by the sample size, not by solver precision. With the ensemble
# below the standard error of the mean is ~0.02, so 0.08 is a safe, principled band.
_ABS_TOL = 0.08


def _random_k_network(rng: random.Random, n: int, k: int, p: float) -> BooleanNetwork:
    """A random Boolean network: every node has exactly ``k`` inputs and a ``p``-biased truth table.

    Each node draws ``k`` distinct inputs uniformly from all ``n`` nodes (self-inputs allowed, as in
    the classic Kauffman ensemble), and a truth table whose entries are 1 with probability ``p``.
    Drawing inputs uniformly from all nodes is what makes the expected number of nodes downstream of
    any given node exactly ``k`` — the fact the annealed slope 2p(1−p)K rests on.
    """
    names = [f"n{i}" for i in range(n)]

    def make_rule(inputs: list[str], table: list[int]):
        def rule(state, _inputs=tuple(inputs), _table=table):
            index = 0
            for name in _inputs:
                index = (index << 1) | (1 if state[name] else 0)
            return _table[index]
        return rule

    rules = {}
    for name in names:
        inputs = rng.sample(names, k)
        table = [1 if rng.random() < p else 0 for _ in range(2**k)]
        rules[name] = make_rule(inputs, table)
    return BooleanNetwork(rules)


def _derrida_slope(rng: random.Random, *, n: int, k: int, p: float,
                   nets: int, states_per_net: int) -> float:
    """Empirical Derrida slope: mean Hamming distance one sync step after a single-node flip.

    Starts from Hamming distance 1 (one flipped node), advances both states one synchronous step
    with the production update, and averages the resulting distance over the ensemble. This is the
    origin slope of the Derrida map, which the annealed theory predicts is 2p(1−p)K.
    """
    total = 0
    trials = 0
    for _ in range(nets):
        net = _random_k_network(rng, n, k, p)
        nodes = net.nodes
        for _ in range(states_per_net):
            state = {node: (1 if rng.random() < 0.5 else 0) for node in nodes}
            flipped = dict(state)
            j = rng.choice(nodes)
            flipped[j] = 1 - flipped[j]
            a = net.step(state)
            b = net.step(flipped)
            total += sum(1 for node in nodes if a[node] != b[node])
            trials += 1
    return total / trials


def test_derrida_slope_matches_the_annealed_law_2p1mpk() -> None:
    # The full closed form s = 2p(1-p)K, checked across connectivities and biases so the match is to
    # the *law*, not to a single lucky point. Each case names its analytical slope.
    rng = random.Random(20260807)
    cases = [
        # (k, p, predicted slope 2p(1-p)k)
        (1, 0.5, 0.5),
        (2, 0.5, 1.0),
        (3, 0.5, 1.5),
        (4, 0.5, 2.0),
        (3, 0.25, 2 * 0.25 * 0.75 * 3),  # biased table lowers sensitivity: 1.125
    ]
    for k, p, predicted in cases:
        measured = _derrida_slope(rng, n=22, k=k, p=p, nets=24, states_per_net=220)
        assert abs(measured - predicted) < _ABS_TOL, (
            f"K={k}, p={p}: measured slope {measured:.3f} != annealed {predicted:.3f}"
        )


def test_critical_connectivity_is_two_for_unbiased_networks() -> None:
    # The qualitative phase transition the slope encodes: at p=1/2, one input is ordered (perturbations
    # shrink, s<1), three inputs is chaotic (perturbations grow, s>1), and two inputs is critical
    # (s=1) — the Kc=2 boundary. This is Kauffman's canonical result, read straight off the slopes.
    rng = random.Random(11)
    ordered = _derrida_slope(rng, n=22, k=1, p=0.5, nets=24, states_per_net=220)
    critical = _derrida_slope(rng, n=22, k=2, p=0.5, nets=24, states_per_net=220)
    chaotic = _derrida_slope(rng, n=22, k=3, p=0.5, nets=24, states_per_net=220)

    assert ordered < 1.0  # subcritical: a perturbation contracts, the network is ordered
    assert chaotic > 1.0  # supercritical: a perturbation expands, the network is chaotic
    assert abs(critical - 1.0) < _ABS_TOL  # the Kc=2 critical boundary, slope exactly 1
    assert ordered < critical < chaotic  # monotone in connectivity, as the law demands
