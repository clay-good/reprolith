"""A reported inter-individual variability metric — the other thing a population paper prints.

The class spec asks for it in as many words: a population claim is "a percentile envelope,
prediction interval, or a reported inter-individual variability metric", and the oracle is to judge
"a percentile envelope by its worst-matched band and a variability scalar by relative error". The
envelope half has been built for a long time. The scalar half was judgeable — `judge_scalar` was
always there — and *unproducible*: `simulate_population` computed each subject's trajectory, took
percentiles of them, and threw the subjects away, so the one thing a %CV of AUC is a statistic of
did not survive the run.

The error bar is the same one the stochastic class needed for the same shape of quantity, and it is
now the same code: a CV is a ratio of moments, so its sampling error is not a mean's, and the closed
forms that exist assume the distribution the claim is about.
"""

from __future__ import annotations

import math

import pytest
from reprolith import PaperIdentity, certify_population
from reprolith.certify import VariabilityClaim
from reprolith.enums import OverallVerdict, Verdict
from reprolith.oracle import SpreadStatistic, spread_standard_error, spread_statistic
from reprolith.stochastic import solver_pin

#: What a variability claim costs, measured rather than chosen: the standard error of a 30% CV is
#: 3.6% of it at 500 subjects — the size a percentile envelope is simulated at — against a 5% pass
#: threshold, so the claim is abstained on there. It resolves at 1,500 (2.1%). A **spread** needs
#: about three times the population its **envelope** does, which is the population-class analogue of
#: the stochastic class's "a Fano factor needs ten times the ensemble its mean does".
_SUBJECTS = 1500
_PROTOCOL = f"{_SUBJECTS} subjects, seed 20260907, log-normal variability on V (CV 0.3)"


def _subjects(cv: float, n: int = _SUBJECTS) -> tuple[float, ...]:
    """A population's metric values with a known coefficient of variation, drawn deterministically."""
    from statistics import NormalDist

    omega = math.sqrt(math.log(1.0 + cv * cv))
    normal = NormalDist()
    # The same median-preserving log-normal the simulator draws, sampled by inverse CDF at evenly
    # spaced quantiles: a fixed sample with the right spread and no RNG in the test.
    return tuple(
        10.0 * math.exp(omega * normal.inv_cdf((index + 0.5) / n)) for index in range(n)
    )


def _certificate(**kw):
    base = dict(
        claim_id="cv-of-auc", quantity="between-subject CV of AUC",
        statistic=SpreadStatistic.COEFFICIENT_OF_VARIATION,
        reported=0.3, values=_subjects(0.3), source_location="Table 4", protocol=_PROTOCOL,
    )
    base.update(kw)
    return certify_population(
        paper=PaperIdentity(title="a population paper"), engine_pin=solver_pin(),
        variability=[VariabilityClaim(**base)],
    )


# --- the statistic, judged by relative error ------------------------------------------------------


def test_a_reported_cv_reproduces_against_the_population_s_own() -> None:
    certificate = _certificate()
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.REPRODUCED
    assert assessment.method == "scalar-relative-error"
    # Qualified, never clean: the spread is a property of the variability model Reprolith
    # reconstructed as much as of the model, exactly as the envelope is.
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assumption = certificate.assumptions[0]
    assert assumption.load_bearing and assumption.author_can_close is False


def test_a_wrong_cv_does_not_reproduce() -> None:
    certificate = _certificate(reported=0.9)
    assert certificate.assessments[0].verdict is Verdict.FAILED
    assert certificate.assessments[0].root_cause


def test_a_standard_deviation_is_judged_in_the_quantity_s_own_units() -> None:
    values = _subjects(0.3)
    expected = spread_statistic(values, SpreadStatistic.STANDARD_DEVIATION)
    certificate = _certificate(
        statistic=SpreadStatistic.STANDARD_DEVIATION, reported=expected, values=values,
        quantity="between-subject SD of AUC",
    )
    assert certificate.assessments[0].verdict is Verdict.REPRODUCED


def test_the_protocol_carries_the_sampling_and_what_it_cost() -> None:
    protocol = _certificate().assessments[0].protocol
    assert _PROTOCOL in protocol
    assert "jackknife standard error" in protocol


# --- the abstentions ------------------------------------------------------------------------------


def test_a_population_too_noisy_to_decide_the_claim_abstains() -> None:
    # Five hundred subjects is the size this class simulates an *envelope* at, and it is not enough
    # for a spread: the CV's own standard error is 3.6% of it against a 5% pass threshold, which is
    # the regime where a correct model misses routinely and a wrong one passes. The honest verdict
    # is that this population cannot decide the claim, not that the model is wrong.
    certificate = _certificate(values=_subjects(0.3, n=500))
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "cannot resolve the claim" in assessment.root_cause
    # An abstention concluded nothing, so nothing is qualified on its behalf.
    assert certificate.assumptions == ()


def test_a_population_whose_metric_is_zero_everywhere_abstains() -> None:
    certificate = _certificate(values=tuple(0.0 for _ in range(500)))
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "no centre to normalize the spread by" in assessment.root_cause


# --- what the claim refuses ------------------------------------------------------------------------


def test_a_population_below_the_spread_bar_is_refused() -> None:
    with pytest.raises(ValueError, match="the spread is the sampling rather than the population"):
        VariabilityClaim(
            claim_id="c", quantity="q", statistic=SpreadStatistic.COEFFICIENT_OF_VARIATION,
            reported=0.3, values=_subjects(0.3, n=20), source_location="Table 4",
            protocol=_PROTOCOL,
        )


def test_a_claim_with_no_protocol_is_refused() -> None:
    with pytest.raises(ValueError, match="states no protocol"):
        VariabilityClaim(
            claim_id="c", quantity="q", statistic=SpreadStatistic.COEFFICIENT_OF_VARIATION,
            reported=0.3, values=_subjects(0.3), source_location="Table 4", protocol="  ",
        )


def test_a_reported_zero_spread_is_refused() -> None:
    with pytest.raises(ValueError, match="statement about the sampling"):
        VariabilityClaim(
            claim_id="c", quantity="q", statistic=SpreadStatistic.COEFFICIENT_OF_VARIATION,
            reported=0.0, values=_subjects(0.3), source_location="Table 4", protocol=_PROTOCOL,
        )


# --- the error bar is one implementation, used by two classes ---------------------------------------


def test_the_two_classes_share_one_definition_of_a_coefficient_of_variation() -> None:
    """The stochastic class's noise statistics and this one are the same shape of quantity, and
    were written a day apart. Two implementations would have disagreed about a zero mean, about the
    population-vs-sample variance, or about the jackknife's scaling — all three of which decide a
    verdict."""
    from reprolith.stochastic import NoiseStatistic, noise_standard_error

    values = _subjects(0.3, n=100)
    assert NoiseStatistic is SpreadStatistic
    assert noise_standard_error(values, SpreadStatistic.COEFFICIENT_OF_VARIATION) == (
        spread_standard_error(values, SpreadStatistic.COEFFICIENT_OF_VARIATION)
    )


def test_the_error_bar_shrinks_with_the_square_root_of_the_population() -> None:
    """What the jackknife is claiming, checked against the law it has to obey."""
    small = spread_standard_error(_subjects(0.3, n=100), SpreadStatistic.COEFFICIENT_OF_VARIATION)
    large = spread_standard_error(_subjects(0.3, n=400), SpreadStatistic.COEFFICIENT_OF_VARIATION)
    assert small is not None and large is not None
    assert small / large == pytest.approx(2.0, rel=0.15)


def test_an_envelope_beside_a_variability_claim_keeps_its_own_assumption() -> None:
    """The pairing defect this was written after finding in my own diff.

    The assumptions were built by slicing the last N assessments back off the list to pair them
    with the variability claims. `assessments[-0:]` is the *whole* list, so a certificate carrying
    an envelope and no variability claim paired the envelope's assessment with nothing — harmless
    there, and one claim away from pairing the wrong claim with the wrong verdict. Both kinds are
    certified together here, and each assumption names its own claim.
    """
    from reprolith import PercentileBand, PopulationClaim

    bands = tuple(
        PercentileBand(percentile=p, curve=tuple(10.0 * f for f in (1.0, 0.8, 0.6)))
        for p in (5.0, 50.0, 95.0)
    )
    certificate = certify_population(
        paper=PaperIdentity(title="a population paper"), engine_pin=solver_pin(),
        claims=[PopulationClaim(
            claim_id="envelope", quantity="envelope", reported=bands, predicted=bands,
            source_location="Fig 2", protocol=_PROTOCOL,
        )],
        variability=[VariabilityClaim(
            claim_id="cv-of-auc", quantity="between-subject CV of AUC",
            statistic=SpreadStatistic.COEFFICIENT_OF_VARIATION,
            reported=0.3, values=_subjects(0.3), source_location="Table 4", protocol=_PROTOCOL,
        )],
    )
    assert [a.claim_id for a in certificate.assessments] == ["envelope", "cv-of-auc"]
    assert sorted(a.id for a in certificate.assumptions) == [
        "population-sampling-cv-of-auc", "population-sampling-envelope",
    ]


def test_a_certificate_of_no_claims_is_refused() -> None:
    """Certifying a paper this path judged nothing of would publish a verdict about no evidence —
    the same refusal every other front end carries."""
    with pytest.raises(ValueError, match="needs at least one claim"):
        certify_population(paper=PaperIdentity(title="nothing"), engine_pin=solver_pin())
