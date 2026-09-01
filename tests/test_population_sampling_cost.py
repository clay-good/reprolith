"""What a *flawless* reproduction of a population costs, before the model disagrees at all.

The distributional tolerance — 15% pass, 35% partial against a printed envelope — is declared
rather than measured, and the loop record says so: no population claim has been certified, so
nothing has exercised the widening. One component of it can be measured today with no paper, no
picture, and no engine, and it is the component that decides whether a verdict means anything.

A population envelope is percentiles of a finite sample. Draw the *same* population twice and the
5th percentile moves. So take a between-subject variability model whose true percentiles are known
in closed form, draw N subjects from it, and compare the sample envelope against the population it
was drawn from. Nothing is wrong with the reconstruction in that comparison, because it is the
right population: whatever error comes back is the ensemble size.

The answer is that under a hundred subjects, the verdict is mostly the sample.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

#: The class default for a printed population envelope: pass at 0.15, partial at 0.35.
_PASS = 0.15
#: The bands `simulate_population` reports by default.
_BANDS = (5.0, 50.0, 95.0)
_REPLICATES = 400


def _omega(cv: float) -> float:
    """The log-scale spread of the median-preserving log-normal `simulate_population` draws."""
    return math.sqrt(math.log(1.0 + cv * cv))


def _true_multiplier(cv: float, percentile: float) -> float:
    return math.exp(_omega(cv) * NormalDist().inv_cdf(percentile / 100.0))


def _sample_percentile(values: list[float], percentile: float) -> float:
    """Linearly interpolated between order statistics — the definition the run publishes."""
    values = sorted(values)
    position = (len(values) - 1) * percentile / 100.0
    below = math.floor(position)
    above = min(below + 1, len(values) - 1)
    return values[below] + (values[above] - values[below]) * (position - below)


def _worst_band_error(cv: float, subjects: int, *, seed: int = 11) -> list[float]:
    """Per replicate: the worst of the three bands, as a fraction of that band's true value.

    The worst band governs the verdict — a good median cannot mask a divergent tail — so it is the
    statistic to measure. This is one time point; the judge takes the worst over every time point
    as well, so the real cost is higher than what is measured here, never lower.
    """
    draws = random.Random(seed)
    standard = NormalDist()
    spread = _omega(cv)
    truth = {p: _true_multiplier(cv, p) for p in _BANDS}
    errors = []
    for _ in range(_REPLICATES):
        sample = [math.exp(spread * standard.inv_cdf(draws.random())) for _ in range(subjects)]
        errors.append(max(
            abs(_sample_percentile(sample, p) - truth[p]) / truth[p] for p in _BANDS
        ))
    return sorted(errors)


def _failure_rate(cv: float, subjects: int) -> float:
    """How often a flawless reproduction of the right population misses the pass budget."""
    errors = _worst_band_error(cv, subjects)
    return sum(1 for error in errors if error > _PASS) / len(errors)


def test_a_small_ensemble_fails_against_the_population_it_was_drawn_from() -> None:
    """The number worth publishing: at twenty subjects and a 30% CV, a reproduction that is right
    about everything misses the 15% band about half the time, and at a 50% CV four times in five.

    There is no model error in this comparison. The disagreement is the ensemble.
    """
    assert _failure_rate(0.3, 20) > 0.4
    assert _failure_rate(0.5, 20) > 0.7


def test_the_cost_falls_with_the_ensemble_and_is_small_by_two_hundred_and_fifty() -> None:
    """What a modeller can act on: the subject count is not a free parameter."""
    rates = [_failure_rate(0.3, n) for n in (20, 50, 100, 250)]
    assert rates == sorted(rates, reverse=True)
    assert rates[1] > 0.05          # 12% at fifty
    assert rates[2] < 0.05          # 2% at a hundred
    assert rates[3] == 0.0          # none in four hundred replicates at two hundred and fifty

    # A wider population needs a bigger one: the same 15% budget, twice the spread.
    assert _failure_rate(0.5, 100) > 0.15
    assert _failure_rate(0.5, 250) < 0.10


def test_the_closed_form_the_run_publishes_matches_the_measurement() -> None:
    """`percentile_sampling_error` states this in the protocol, so it has to be the same number.

    The asymptotic standard error of a sample quantile understates the tails at small N — which is
    the safe direction for a number a reader compares against a tolerance only if it is not read as
    a bound. It is published as a scale, and this pins how far it is from the measurement.
    """
    from reprolith.population import percentile_sampling_error

    for cv in (0.3, 0.5):
        for subjects in (50, 100, 250, 1000):
            stated = percentile_sampling_error(cv=cv, percentile=5.0, subjects=subjects)
            measured = _worst_band_error(cv, subjects)[_REPLICATES // 2]
            # The stated scale is a standard error and the measurement is a median worst-of-three,
            # so they are close rather than equal. Within a factor of two, both ways.
            assert 0.5 < stated / measured < 2.0
