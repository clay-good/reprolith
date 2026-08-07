"""The stochastic (Gillespie SSA) model class (spec: stochastic-class).

Self-validated non-circularly against systems whose stochastic result is known in closed form — no
external tool, no fabricated data. The SSA is pure Python and deterministic under a pinned seed, so
these run in the core CI job and reproduce byte-for-byte.
"""

from __future__ import annotations

import math
import random

import pytest
from reprolith import (
    PercentileBand,
    Reaction,
    ReferenceKind,
    Verdict,
    ensemble_final_counts,
    ensemble_percentile_bands,
    gillespie,
    judge_distribution,
    judge_scalar,
    species_mean_variance,
)


def _poisson_quantile(lam: float, percentile: float) -> float:
    """The nearest-rank quantile of a Poisson(lam) distribution — pure-Python closed form."""
    if lam <= 0.0:
        return 0.0
    target = percentile / 100.0
    cdf = 0.0
    term = math.exp(-lam)
    k = 0
    while True:
        cdf += term
        if cdf >= target - 1e-12:
            return float(k)
        k += 1
        term *= lam / k


def _immigration_death(k: float, gamma: float) -> list[Reaction]:
    # ∅ -(k)-> A  (zero-order birth) ; A -(gamma)-> ∅  (first-order death).
    return [
        Reaction(rate=k, reactants=(), products=((0, 1),)),
        Reaction(rate=gamma, reactants=((0, 1),), products=()),
    ]


def test_immigration_death_reproduces_the_poisson_stationary_mean_and_variance() -> None:
    # The immigration-death process has a Poisson stationary distribution with mean = variance = k/γ.
    k, gamma = 10.0, 1.0
    analytic = k / gamma  # = 10 for both mean and variance
    ensemble = ensemble_final_counts(
        1, _immigration_death(k, gamma), [0], duration=40.0, trajectories=400, seed=20260807
    )
    mean, variance = species_mean_variance(ensemble, species=0)

    # Judge the reproduced mean against the closed-form value with the oracle, at a finite-sample
    # tolerance (SE of the mean ~ sqrt(10/400) ≈ 0.16, so ~5% covers it comfortably).
    verdict = judge_scalar(
        claim_id="A-mean", quantity="stationary mean copy number", source_location="closed-form Poisson",
        reported=analytic, predicted=mean,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    # The Poisson signature — variance equals the mean — is reproduced too (looser: variance is noisier).
    assert abs(variance - analytic) / analytic < 0.20


def test_transient_poisson_percentile_envelope_is_reproduced() -> None:
    # Immigration-death started empty is Poisson at every time t with mean λ(t) = (k/γ)(1 - e^{-γt}).
    # So the analytical percentile envelope over time is exact — an independent, closed-form ground
    # truth for the distributional (population) oracle applied to a stochastic reproduction.
    k, gamma = 8.0, 1.0
    reactions = _immigration_death(k, gamma)
    times = [1.0, 2.0, 4.0, 7.0, 12.0]
    percentiles = [10.0, 50.0, 90.0]
    lam = [k / gamma * (1 - math.exp(-gamma * t)) for t in times]
    analytic = tuple(
        PercentileBand(p, tuple(_poisson_quantile(x, p) for x in lam)) for p in percentiles
    )
    simulated = ensemble_percentile_bands(
        1, reactions, [0], times, species=0,
        percentiles=percentiles, trajectories=2000, seed=42,
    )
    # A stochastic percentile envelope carries Monte-Carlo and discrete-count noise, so it is judged
    # at the distributional figure tolerance — under which it reproduces the closed-form envelope.
    verdict = judge_distribution(
        claim_id="A-envelope", quantity="transient percentile envelope",
        source_location="closed-form transient Poisson", reference=analytic, predicted=simulated,
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    assert verdict.assumption_qualified is True  # a population reproduction is qualified by default
    # The median band matches the analytical Poisson median exactly at every sample time.
    sim_median = next(b for b in simulated if b.percentile == 50.0)
    analytic_median = next(b for b in analytic if b.percentile == 50.0)
    assert sim_median.curve == analytic_median.curve


def test_reversible_reaction_reproduces_the_binomial_equilibrium_mean() -> None:
    # A <-> B with total N conserved: at equilibrium B ~ Binomial(N, kf/(kf+kr)), mean = N*kf/(kf+kr).
    n_total, kf, kr = 50, 3.0, 1.0
    reactions = [
        Reaction(rate=kf, reactants=((0, 1),), products=((1, 1),)),  # A -> B
        Reaction(rate=kr, reactants=((1, 1),), products=((0, 1),)),  # B -> A
    ]
    analytic_b = n_total * kf / (kf + kr)  # = 37.5
    ensemble = ensemble_final_counts(
        2, reactions, [n_total, 0], duration=30.0, trajectories=400, seed=1234
    )
    mean_b, _ = species_mean_variance(ensemble, species=1)
    verdict = judge_scalar(
        claim_id="B-eq", quantity="equilibrium mean of B", source_location="closed-form binomial",
        reported=analytic_b, predicted=mean_b,
    )
    assert verdict.verdict is Verdict.REPRODUCED


def test_conservation_is_respected_every_trajectory() -> None:
    # A <-> B conserves A+B on every single trajectory — a structural invariant of the SSA.
    reactions = [
        Reaction(rate=2.0, reactants=((0, 1),), products=((1, 1),)),
        Reaction(rate=1.0, reactants=((1, 1),), products=((0, 1),)),
    ]
    ensemble = ensemble_final_counts(2, reactions, [30, 0], duration=10.0, trajectories=50, seed=7)
    assert all(a + b == 30 for a, b in ensemble)


def test_pinned_seed_is_byte_reproducible() -> None:
    reactions = _immigration_death(5.0, 1.0)
    a = ensemble_final_counts(1, reactions, [0], duration=20.0, trajectories=100, seed=99)
    b = ensemble_final_counts(1, reactions, [0], duration=20.0, trajectories=100, seed=99)
    assert a == b  # identical ensembles from the same seed — the reproducible-sampling contract


def test_absorbing_state_halts_the_trajectory() -> None:
    # Pure death with no birth drains to zero and then cannot fire — the run must terminate cleanly.
    death_only = [Reaction(rate=1.0, reactants=((0, 1),), products=())]
    final = gillespie(1, death_only, [5], duration=1e6, rng=random.Random(0))
    assert final == [0]


def test_dimerization_propensity_uses_the_falling_factorial() -> None:
    # 2A -> A2: propensity = rate * n(n-1)/2. With n=4 and rate=1, that is 6.
    dimerize = Reaction(rate=1.0, reactants=((0, 2),), products=((1, 1),))
    assert dimerize.propensity([4, 0]) == pytest.approx(6.0)
    assert dimerize.propensity([1, 0]) == 0.0  # cannot fire with a single molecule
