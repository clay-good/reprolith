"""An abstention on sample size says how large a sample would settle it.

Two checks in this package refuse to judge a claim because the sample it rests on is too noisy: the
stochastic class's ensemble and the population class's variability draw. Both said "N is too few"
and stopped there, which is the shape the pre-submission spec names as the one thing a fix line must
never be — the finding restated under a heading that says to fix it. The author is left to guess
whether the next run needs twice the sample or two hundred times it, and those are different
decisions.

The arithmetic was already in the repository for the *judged* case (`ensemble_to_settle`, which
sizes a run against the margin to a claim's verdict line). An abstention cannot use that one: it is
abstaining because its own answer is not trustworthy, so the residual is the wrong ruler. It is
sized against the **check's own bar** instead — the half-threshold at which each of these two stops
abstaining — which is a property of the check and not of the number under suspicion.

What these tests hold is that the count is not decorative: re-running the same check at the size it
names actually stops the abstention.
"""

from __future__ import annotations

from reprolith.enums import Verdict
from reprolith.oracle import (
    RESOLVING_ERROR_SHARE,
    resolving_sample_clause,
    sample_to_resolve,
)
from reprolith.stochastic import _SPREAD_IS_EVIDENCE, unresolvable_ensemble_reason
from test_population_variability_claim import _certificate, _subjects


def _count_in(reason: str) -> int:
    """The trajectory or subject count an abstention names, parsed back out of its own sentence."""
    import re

    match = re.search(r"~([\d,]+) (?:trajectories|subjects)", reason)
    assert match is not None, f"no resolving count in: {reason}"
    return int(match.group(1).replace(",", ""))


# --- the stochastic ensemble ----------------------------------------------------------------------


def test_a_noisy_ensemble_says_how_many_trajectories_would_resolve_it() -> None:
    reason = unresolvable_ensemble_reason(reported_mean=10.0, variance=9.0, trajectories=10)
    assert reason is not None
    needed = _count_in(reason)
    # Not asserted against a hard-coded number: the claim is that re-running the *same* check at the
    # size it names no longer abstains. A count that were merely plausible would fail here.
    assert unresolvable_ensemble_reason(
        reported_mean=10.0, variance=9.0, trajectories=needed
    ) is None
    # And it is not extravagant: within half again of the bare 1/sqrt(n) figure, which is the whole
    # allowance the count carries for an error bar that is itself an estimate.
    assert needed <= 1.5 * 10 * (0.0949 / 0.025) ** 2


def test_an_ensemble_that_resolves_its_claim_is_told_nothing() -> None:
    # There is nothing to buy, and a sentence recommending more trajectories to a reader who does
    # not need them is noise dressed as advice — the same rule the judged-claim settling clause
    # holds to.
    assert unresolvable_ensemble_reason(
        reported_mean=10.0, variance=9.0, trajectories=4000
    ) is None


def test_a_zero_spread_ensemble_names_the_size_a_zero_becomes_a_measurement_at() -> None:
    # This branch abstains for a different reason — no spread at all, at a size where zero is as
    # likely an accident as a measurement — so the 1/sqrt(n) arithmetic does not apply and the bar
    # itself is the answer. It was the branch left out of the first version of this work, which is
    # the shape ("covers every case it was written for but one") this repository keeps catching.
    reason = unresolvable_ensemble_reason(reported_mean=10.0, variance=0.0, trajectories=3)
    assert reason is not None
    assert f"at {_SPREAD_IS_EVIDENCE} trajectories" in reason


# --- the population draw --------------------------------------------------------------------------


def test_a_noisy_population_says_how_many_subjects_would_resolve_it() -> None:
    # The count the naive 1/sqrt(n) arithmetic gives here is 1,034, where this sample's error bar
    # reads 2.54% against a 2.5% target — an author who followed that advice would be abstained on
    # a second time. That is what the allowance is for, and it is why this test re-runs the check
    # rather than checking the sentence contains a number.
    certificate = _certificate(values=_subjects(0.3, n=500))
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    needed = _count_in(assessment.root_cause)
    # Same test as the ensemble's: draw that many subjects at the same spread and the check judges.
    resolved = _certificate(values=_subjects(0.3, n=needed))
    assert resolved.assessments[0].verdict is not Verdict.NOT_EVALUABLE


# --- the shared arithmetic ------------------------------------------------------------------------


def test_the_count_is_the_one_the_error_bar_implies() -> None:
    # A standard error falls as 1/sqrt(n), so quartering it costs sixteen times the sample: 1,600
    # bare. The count is 1,835 because the error bar it extrapolates from is itself known only to
    # about 1/sqrt(2n) of itself at this size, and a count sized to land exactly on the bar lands
    # under it about half the time.
    assert sample_to_resolve(relative_error_bar=0.1, size=100, pass_threshold=0.05) == 1835
    assert RESOLVING_ERROR_SHARE * 0.05 == 0.025


def test_the_allowance_shrinks_as_the_sample_grows() -> None:
    # A larger sample knows its own error bar better, so it needs less headroom. Held because the
    # allowance is derived from the sample size rather than chosen as a constant, and a constant
    # would be indistinguishable from it at any single size.
    small = sample_to_resolve(relative_error_bar=0.1, size=100, pass_threshold=0.05)
    large = sample_to_resolve(relative_error_bar=0.1, size=10_000, pass_threshold=0.05)
    assert small is not None and large is not None
    assert small / 100 > large / 10_000 > 16.0


def test_nothing_is_offered_where_there_is_nothing_to_buy() -> None:
    assert sample_to_resolve(relative_error_bar=0.01, size=100, pass_threshold=0.05) is None
    assert sample_to_resolve(relative_error_bar=0.1, size=0, pass_threshold=0.05) is None
    assert sample_to_resolve(relative_error_bar=0.0, size=100, pass_threshold=0.05) is None
    assert resolving_sample_clause(
        relative_error_bar=0.01, size=100, pass_threshold=0.05, noun="trajectories"
    ) == ""


def test_the_two_abstentions_state_the_rule_the_same_way() -> None:
    # One implementation, so the two surfaces cannot come to word the same arithmetic differently —
    # the inline-vs-certificate differential this repository runs on every shared rule.
    ensemble = unresolvable_ensemble_reason(reported_mean=10.0, variance=9.0, trajectories=10)
    population = _certificate(values=_subjects(0.3, n=500)).assessments[0].root_cause
    tail = "would bring that error bar under half the threshold, which is where this check stops"
    assert ensemble is not None and tail in ensemble
    assert tail in population


# --- the spatial domain ---------------------------------------------------------------------------


def test_a_domain_too_coarse_to_judge_says_how_much_longer_would_do_it() -> None:
    """The third abstention of this shape, and the one that stated a *direction* rather than nothing.

    "A longer domain holds more modes and measures finer" is true of every domain ever discretized,
    exactly as "a larger ensemble" is true of every ensemble. The arithmetic is simpler here than
    for a sample: the finest gap near mode `m` is `1/(m+1)` of the wavelength under either wall, so
    a pass width of `w` needs a mode of at least `ceil(1/w) - 1`, and a fixed physical wavelength
    reaches that mode in a domain longer by the ratio of the two.
    """
    from reprolith.spatial import _domain_to_resolve
    from test_spatial_pattern_claim import _claim, _judge_pattern

    short = _claim(length=40.0, points=201, dt=0.24 * (40.0 / 200) ** 2 / 40.0, steps=100,
                   confirm_steps=100)
    reason = _judge_pattern(short).root_cause
    assert "needs mode 19 or higher" in reason
    assert "about 3.8x as long" in reason
    # And the count is the one the rule implies rather than a number pasted into a sentence: mode 19
    # is the first whose 1/(m+1) spacing is inside a 5% pass width, and mode 18's is not.
    assert 1.0 / (19 + 1) <= 0.05 < 1.0 / (18 + 1)
    # Nothing is claimed where the arithmetic has nothing to say, and the direction survives there.
    assert _domain_to_resolve(short, 0, 0.05) == "a longer domain holds more modes and measures finer"


# --- the digitized reading ------------------------------------------------------------------------


def test_a_reading_with_no_interior_point_in_the_window_is_not_called_too_few() -> None:
    """Two different facts were reported under one sentence, and one of them was false.

    A reading's interpolation cost is unmeasurable for two unrelated reasons: fewer than three
    points, which is a reading too coarse to check itself anywhere; and a judged window that falls
    between two read points, which a reading of any length can hit. The citation line said "N
    points, too few to measure what its interpolation costs" for both — telling the curator of a
    five-point reading that five is too few, when five is not the problem and reading a sixth
    somewhere else would not fix it.
    """
    from reprolith.digitization import interpolation_cost
    from test_digitization import _series

    fine = _series([[0, 0.0], [2, 5.0], [6, 8.0], [12, 4.0], [24, 2.0]])
    # Judged over 12-24, whose only read points are its own endpoints: nothing interior to check.
    narrow = interpolation_cost(fine, window=(12.0, 24.0))
    assert narrow["measurable"] is False
    assert narrow["unmeasurable_because"] == "window-holds-no-interior-point"
    line = fine.source_line(window=(12.0, 24.0))
    assert "too few" not in line
    assert "none of them strictly inside the 12-24 window" in line
    assert "read a point inside that stretch" in line

    # The genuinely under-read case keeps its own sentence, and gains the bar it is measured against.
    coarse = _series([[0, 0.0], [24, 2.0]])
    assert interpolation_cost(coarse)["unmeasurable_because"] == "under-read"
    assert "three read points are the fewest" in coarse.source_line()

    # And a measurable reading carries the key too, so a consumer sees one shape rather than two.
    assert interpolation_cost(fine)["unmeasurable_because"] is None


# --- the judged claim, which is the other half of the same question --------------------------------


def test_a_judged_population_says_what_would_settle_it_as_the_ensemble_does() -> None:
    """The stochastic class tells a *judged* claim how large a sample would settle it. The
    population class shared that class's abstention rule and its jackknife error bar, and never got
    this — the "covers every case it was written for but one" shape, across two modules instead of
    two branches.

    The two questions need different rulers and both are legitimate here. An abstention is sized
    against the check's own bar because its answer is not trustworthy; a judged claim is sized
    against the margin from its answer to the nearest verdict line, because that answer *is* a
    measurement and the margin is what the reader wants to know is safe.
    """
    from reprolith.oracle import sample_to_settle
    from test_population_variability_claim import _certificate, _subjects

    protocol = _certificate().assessments[0].protocol
    assert "from the nearest verdict line" in protocol
    assert "subjects" in protocol.split("so ~")[1]

    # A claim sitting closer to its line needs a much larger population, which is the whole reason
    # for computing it rather than saying "a larger sample": these two differ by an order of
    # magnitude and read identically under the old sentence.
    near = _certificate(values=_subjects(0.31)).assessments[0].protocol
    assert int(protocol.split("so ~")[1].split()[0].replace(",", "")) < int(
        near.split("so ~")[1].split()[0].replace(",", "")
    )

    # Nothing is offered where there is nothing to buy, and no finite sample settles a claim
    # landing exactly on its threshold.
    tol = _certificate().assessments[0]
    del tol
    from reprolith.oracle import ComparisonMethod, ReferenceKind, default_tolerance

    tolerance = default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC)
    assert sample_to_settle(
        relative_error=0.0, relative_error_bar=0.0001, size=100, tolerance=tolerance
    ) is None
    assert sample_to_settle(
        relative_error=tolerance.reproduced_within, relative_error_bar=0.02, size=100,
        tolerance=tolerance,
    ) is None


def test_the_two_classes_compute_the_settling_count_with_one_function() -> None:
    """One implementation, so a stochastic ensemble and a population draw cannot come to size the
    same question differently — the inline-vs-certificate differential, across classes."""
    from reprolith.oracle import (
        ComparisonMethod,
        ReferenceKind,
        default_tolerance,
        sample_to_settle,
    )
    from reprolith.stochastic import ensemble_to_settle

    tolerance = default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC)
    assert ensemble_to_settle(
        relative_error=0.02, relative_sem=0.01, trajectories=400, tolerance=tolerance
    ) == sample_to_settle(
        relative_error=0.02, relative_error_bar=0.01, size=400, tolerance=tolerance
    )
