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
