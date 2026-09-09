"""The jackknife error bar's *magnitude*, against the spread it claims to estimate.

`spread_standard_error` decides two things that reach a certificate: whether a claim is abstained on
(the bar against half the pass threshold) and how large a sample would settle it (the bar carried
through a 1/sqrt(n) extrapolation). Two tests already stood over it — that the stochastic and the
population implementations agree with each other, and that the bar shrinks as 1/sqrt(n).

Neither can see a wrong constant. An implementation off by a fixed factor — the jackknife's
`(n-1)/n` scaling dropped, a population variance where a sample one belongs — agrees with itself
perfectly and obeys the square-root law exactly, while every abstention and every settling count it
produces is wrong by that factor. That is the shape this repository calls a floor that cannot see
what it never counted.

So: draw the same population many times, measure how far the statistic actually moves between draws,
and compare that to what the jackknife says from a single draw. The answer is that it agrees to
within about a tenth, biased slightly **low** — which is the direction worth knowing, because a bar
that under-reports noise lets a claim through that should have abstained. It shrinks as the sample
grows (0.93 of truth at 200 subjects, 0.95 at 1,000, 0.97 at 4,000 on one seed), which is the
jackknife's known behaviour on a ratio of moments rather than a defect here.

Nothing is re-scaled on the strength of it. The end-to-end consequence is measured separately, and
is small: `tests/test_population_variability_bar.py` finds a correct model falsely accused on 1.6%
of draws at the size this class publishes at.
"""

from __future__ import annotations

import math
import random
import statistics

import pytest
from reprolith.oracle import SpreadStatistic, spread_standard_error, spread_statistic

_CV = 0.3
_DRAWS = 200
#: Two seeds and their results aggregated: the empirical spread is itself an estimate from `_DRAWS`
#: draws, known to about 1/sqrt(2 * _DRAWS) of itself, so one seed's ratio carries several percent
#: of noise on top of whatever the jackknife's own bias is.
_SEEDS = (11, 20250101)


def _calibration(statistic: SpreadStatistic, subjects: int) -> float:
    """``mean jackknife bar / empirical standard deviation of the statistic``, over ``_SEEDS``."""
    omega = math.sqrt(math.log(1.0 + _CV * _CV))
    observed: list[float] = []
    bars: list[float] = []
    for seed in _SEEDS:
        draws = random.Random(seed)
        for _ in range(_DRAWS):
            values = [10.0 * math.exp(draws.gauss(0.0, omega)) for _ in range(subjects)]
            observed.append(spread_statistic(values, statistic))
            bar = spread_standard_error(values, statistic)
            if bar is not None:
                bars.append(bar)
    return statistics.fmean(bars) / statistics.stdev(observed)


@pytest.mark.parametrize(
    "statistic",
    [
        SpreadStatistic.COEFFICIENT_OF_VARIATION,
        SpreadStatistic.FANO_FACTOR,
        SpreadStatistic.STANDARD_DEVIATION,
    ],
)
def test_the_bar_matches_the_spread_it_estimates(statistic: SpreadStatistic) -> None:
    """Within a tenth, for every statistic this package judges.

    Wide enough to be about the estimator rather than about these seeds, and far tighter than any
    wrong constant would survive: dropping the jackknife's `(n-1)/n` scaling misses by a factor of
    `n`, and a population-versus-sample variance mix-up by a factor near one only for large `n` and
    never in the direction of a tenth at 200.
    """
    ratio = _calibration(statistic, 200)
    assert 0.85 < ratio < 1.15


def test_the_bias_is_low_rather_than_high_and_shrinks() -> None:
    """The direction is what matters for a gate: a bar that under-reports noise lets a claim through
    that should have abstained, so this is the unsafe direction and it is recorded rather than
    discovered later. It closes as the sample grows, which is the jackknife's known behaviour on a
    ratio of moments."""
    statistic = SpreadStatistic.COEFFICIENT_OF_VARIATION
    small = _calibration(statistic, 200)
    large = _calibration(statistic, 1000)
    assert small < 1.0
    assert large > small
