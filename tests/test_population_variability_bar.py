"""What the variability abstention's bar is worth, measured rather than asserted.

The rule is that a spread statistic whose own error bar exceeds **half** the pass threshold cannot
tell a reproduction from the draw. Its justification lived in a docstring — "the regime where a
correct model misses routinely and a wrong one passes" — and the only test of it drew its population
from a deterministic inverse-CDF quantile grid, which has no draw-to-draw variation at all. A
fixture like that confirms whatever it is asked about sampling: it can show the check *fires*, and
it cannot show the bar sits in the right place.

The stochastic class measured its analogue and published the numbers (at ten trajectories a provably
correct immigration-death model misses its 5% claim on most seeds; 2 of 200 at three standard
errors). This is the same measurement for the population class: draw genuinely random populations
from a log-normal whose true coefficient of variation is known, judge each against that true value,
and count how often a **correct** model would be published as a miss.

The answer, over 1,000 draws per size — 200 each under five seeds, aggregated rather than pinned to
one, because a single seed's false-miss count at 1,500 ranges from 2 to 12 across seeds and a test
asserting one of them is a CI flake dressed as a measurement:

| subjects | abstained | judged pass | false miss |
|---------:|----------:|------------:|-----------:|
|      250 |      100% |          0% |         0% |
|      500 |      100% |          0% |         0% |
|    1,000 |     59.1% |       38.4% |       2.5% |
|    1,500 |      6.8% |       91.6% |       1.6% |
|    3,000 |        0% |       99.8% |       0.2% |

Two things it settles. Below a thousand subjects the check never reaches a verdict at all, so the
regime the docstring worries about is one the bar keeps it *out of* rather than one it survives. And
at the 1,500 the worked example uses, a correct model is falsely published as a miss on 1.6% of
draws — the same order as the 1% the stochastic class accepted for the same kind of guard. The bar
is not moved on the strength of this; it is recorded, which is what the loop record asks for.

The assertions below are about the mechanism and not about these exact counts: the shape that holds
under every seed is that the bar keeps a small population out of a verdict entirely, and that where
it does let one through, correct models pass it by two orders of magnitude more often than they fail.
"""

from __future__ import annotations

import math
import random

from reprolith.oracle import (
    ComparisonMethod,
    ReferenceKind,
    SpreadStatistic,
    default_tolerance,
    spread_standard_error,
    spread_statistic,
)

_CV = 0.3
_STATISTIC = SpreadStatistic.COEFFICIENT_OF_VARIATION
_DRAWS = 200
#: Five, not one. A single seed's false-miss count at 1,500 subjects ranges from 2 to 12 across
#: seeds, so a bound tight enough to say anything about one of them fails on another.
_SEEDS = (1, 7, 99, 20260101, 5551212)


def _outcomes(subjects: int) -> tuple[int, int, int]:
    """``(abstained, judged pass, false miss)`` over ``_DRAWS`` correct populations per seed."""
    tolerance = default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC)
    omega = math.sqrt(math.log(1.0 + _CV * _CV))
    abstained = passed = missed = 0
    for seed in _SEEDS:
        draws = random.Random(seed)
        for _ in range(_DRAWS):
            values = [10.0 * math.exp(draws.gauss(0.0, omega)) for _ in range(subjects)]
            error_bar = spread_standard_error(values, _STATISTIC)
            # The certifier's own condition, spelled the same way: the bar is half the pass
            # threshold, taken against the *reported* value — here the population's true CV.
            if error_bar is not None and error_bar > tolerance.reproduced_within * _CV / 2.0:
                abstained += 1
            elif (
                abs(spread_statistic(values, _STATISTIC) - _CV) / _CV
                <= tolerance.reproduced_within
            ):
                passed += 1
            else:
                missed += 1
    return abstained, passed, missed


def test_below_a_thousand_subjects_the_check_never_reaches_a_verdict() -> None:
    """So the regime a correct model would routinely miss in is one the bar keeps it out of."""
    for subjects in (250, 500):
        abstained, passed, missed = _outcomes(subjects)
        assert (passed, missed) == (0, 0)
        assert abstained == _DRAWS * len(_SEEDS)


def test_at_the_size_the_worked_example_uses_a_correct_model_is_rarely_accused() -> None:
    """1.6% at 1,500 subjects, the same order as the 1% the stochastic class accepted."""
    _abstained, passed, missed = _outcomes(1500)
    assert passed > missed * 20
    assert missed / (_DRAWS * len(_SEEDS)) < 0.05


def test_a_large_enough_population_neither_abstains_nor_accuses() -> None:
    abstained, passed, missed = _outcomes(3000)
    # No abstention at all is the mechanism: the error bar of a 30% CV at 3,000 subjects is well
    # inside half the pass threshold on every draw. A rare false miss survives — it is a 5% band
    # around a sampled statistic, not a guarantee — and is bounded rather than assumed away.
    assert abstained == 0
    assert missed / (_DRAWS * len(_SEEDS)) < 0.01
    assert passed > missed * 100
