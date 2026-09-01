"""What a *flawless* re-fit costs, before the optimizer or the model is at fault.

The estimation-level tolerance — 10% pass, 25% partial — is declared rather than measured, and the
loop record says so: no estimation-level claim has been certified. One component of it can be
measured today with no paper and no engine, and it is the component nobody can optimise away.

A re-fit recovers parameters from *noisy* data. Fit the same experiment twice, with the same
correct model and a perfect optimizer, and the estimates move — because the data moved. So generate
observations from a model whose parameters are known, add assay noise, recover the parameters by
exact least squares, and compare them against the values they were generated from. Nothing is wrong
with the model or the optimizer in that comparison: whatever error comes back is the data.

This measures the statistical floor that any correct optimizer shares, not `refit_parameters`'
implementation of one: the fit here is a closed-form log-linear regression, which is the exact
least-squares solution for this model and needs no engine. `tests/test_estimation_refit.py` is
where the shipped optimizer is checked.

The answer has an asymmetry worth knowing: rates are recovered tightly and scales are not.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

#: The estimation-level class default: pass at 0.10, partial at 0.25.
_PASS = 0.10
_REPLICATES = 600
#: The population this generates from: a one-compartment bolus, read over a day.
_TRUE_SCALE, _TRUE_RATE, _WINDOW = 10.0, 0.25, 24.0


def _recover(times: list[float], noise: float, draws: random.Random) -> tuple[float, float]:
    """The exact least-squares estimate of (scale, rate) from one noisy realization.

    Multiplicative log-normal assay noise makes `ln C` linear in `t`, so the least-squares fit is
    a straight-line regression with a closed form — the optimum itself, with no optimizer between
    the data and the estimate.
    """
    standard = NormalDist()
    log_observed = [
        math.log(_TRUE_SCALE * math.exp(-_TRUE_RATE * t)) + noise * standard.inv_cdf(draws.random())
        for t in times
    ]
    n = len(times)
    mean_t, mean_y = sum(times) / n, sum(log_observed) / n
    spread = sum((t - mean_t) ** 2 for t in times)
    slope = sum((t - mean_t) * (y - mean_y) for t, y in zip(times, log_observed)) / spread
    return math.exp(mean_y - slope * mean_t), -slope


def _errors(points: int, noise: float, *, seed: int = 5) -> tuple[float, float, float]:
    """Median relative error of each parameter, and how often the worse one misses the budget."""
    draws = random.Random(seed)
    times = [_WINDOW * i / (points - 1) for i in range(points)]
    scales, rates, missed = [], [], 0
    for _ in range(_REPLICATES):
        scale, rate = _recover(times, noise, draws)
        scales.append(abs(scale - _TRUE_SCALE) / _TRUE_SCALE)
        rates.append(abs(rate - _TRUE_RATE) / _TRUE_RATE)
        if max(scales[-1], rates[-1]) > _PASS:
            missed += 1
    scales.sort(), rates.sort()
    return scales[_REPLICATES // 2], rates[_REPLICATES // 2], missed / _REPLICATES


def test_a_rate_is_recovered_tightly_and_a_scale_is_not() -> None:
    """The asymmetry: the same data that pins the elimination rate to 3% leaves the scale at 10%.

    An estimation verdict therefore says much more about a paper's rate constants than about its
    volumes or doses, and the tolerance has to cover the looser of the two.
    """
    scale, rate, _ = _errors(points=8, noise=0.20)
    assert rate < 0.03
    assert scale > 3 * rate


def test_realistic_assay_noise_spends_the_whole_budget_on_itself() -> None:
    """At a 20% assay CV, a re-fit that is right about everything misses the 10% pass budget about
    half the time — the model is exact, the optimizer is the closed-form optimum, and the
    disagreement is the data."""
    _, _, missed = _errors(points=8, noise=0.20)
    assert missed > 0.4

    # At a 5% CV — a clean in-vitro assay — it essentially never happens.
    assert _errors(points=8, noise=0.05)[2] < 0.02


def test_more_data_helps_and_does_not_rescue_a_noisy_assay() -> None:
    """Worth stating because the intuition is wrong: quadrupling the observations cuts the scale's
    error by about a third, not by half, so the noise level governs rather than the sample size."""
    missed = [_errors(points=n, noise=0.20)[2] for n in (5, 8, 12, 20)]
    assert missed == sorted(missed, reverse=True)
    assert missed[-1] > 0.15  # twenty points, and it still misses one time in four

    coarse, fine = _errors(points=5, noise=0.20)[0], _errors(points=20, noise=0.20)[0]
    assert 0.5 < fine / coarse < 0.8
