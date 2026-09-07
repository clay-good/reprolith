"""A reported noise statistic can be certified, and it says what a bigger ensemble it costs.

`fano_factor` and `coefficient_of_variation` have been in this package since the class was written,
checked against the Poisson laws (Fano = 1, CV = 1/√mean) — and no claim could carry one. So the
quantity a stochastic model is *for* — how noisy it is, which is what single-cell and
gene-expression papers report as their headline — was implemented and unreachable, the fifth thing
found in that state here.

The part worth reading twice is the error bar. A mean's is `sqrt(variance/n)`; a Fano factor's is
not, and the closed forms that exist assume a distribution — which is the thing the claim is about.
So it is resampled, by leave-one-out rather than by bootstrap, because this class's contract is that
a verdict is a deterministic function of a pinned seed and a bootstrap would put a second, unpinned
sampler inside the number that decides whether to abstain.
"""

from __future__ import annotations

import math

import pytest
from reprolith import (
    NoiseClaim,
    NoiseStatistic,
    PaperIdentity,
    Reaction,
    certify_stochastic,
    ensemble_final_counts,
    noise_standard_error,
)
from reprolith.enums import OverallVerdict, Verdict
from reprolith.stochastic import solver_pin

# Immigration-death: birth at a constant rate, death proportional to copy number. Its stationary
# distribution is Poisson with mean k/γ, so its Fano factor is exactly 1 and its CV exactly
# 1/√mean — closed-form ground truth needing no external tool.
_IMMIGRATION_DEATH = [Reaction(10.0, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())]
_POISSON_MEAN = 10.0


def _claim(**kw) -> NoiseClaim:
    base = dict(
        claim_id="fano", quantity="Fano factor of the stationary distribution", species=0,
        statistic=NoiseStatistic.FANO_FACTOR, reported_value=1.0, source_location="closed-form",
        duration=40.0, trajectories=4000, seed=20260907,
    )
    base.update(kw)
    return NoiseClaim(**base)


def _certificate(*claims: NoiseClaim):
    return certify_stochastic(
        paper=PaperIdentity(title="immigration-death"),
        engine_pin=solver_pin(),
        n_species=1, reactions=_IMMIGRATION_DEATH, initial=[0],
        noises=list(claims),
    )


# --- the two statistics reproduce their closed forms ---------------------------------------------


def test_a_poisson_fano_factor_of_one_reproduces() -> None:
    certificate = _certificate(_claim())
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.REPRODUCED
    # Qualified, never clean: the ensemble is Reprolith's choice, like every verdict in this class.
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert certificate.assumptions[0].load_bearing
    assert certificate.assumptions[0].author_can_close is False


def test_a_poisson_coefficient_of_variation_reproduces() -> None:
    certificate = _certificate(_claim(
        claim_id="cv", statistic=NoiseStatistic.COEFFICIENT_OF_VARIATION,
        reported_value=1.0 / math.sqrt(_POISSON_MEAN), trajectories=2000,
    ))
    assert certificate.assessments[0].verdict is Verdict.REPRODUCED


def test_a_wrong_noise_level_does_not_reproduce() -> None:
    # A model whose expression is claimed to be twice as bursty as it is. The ensemble's own error
    # bar is 2.3% here, so nothing about this miss is sampling.
    certificate = _certificate(_claim(reported_value=2.0))
    assert certificate.assessments[0].verdict is Verdict.FAILED


# --- what the statistic costs, on the certificate ------------------------------------------------


def test_the_protocol_names_the_statistic_and_its_measured_error_bar() -> None:
    certificate = _certificate(_claim())
    protocol = certificate.assessments[0].protocol
    # The same ensemble answers both statistics, so a protocol naming only the species would be
    # byte-identical for two claims that disagree about the number.
    assert "read=fano-factor of species[0]" in protocol
    assert "jackknife standard error" in protocol
    assert "against a 5% pass threshold" in protocol


def test_a_fano_factor_needs_a_bigger_ensemble_than_a_mean_and_the_run_says_so() -> None:
    # The measurement behind that sentence, and the reason this claim type carries its own error
    # bar: at 400 trajectories — the size this class certifies *means* at — a Fano factor's
    # standard error is over 7% of the value, far past the 2.5% at which a correct model starts
    # missing routinely. The ensemble cannot decide the claim, and the honest verdict says so.
    small = _certificate(_claim(trajectories=400))
    assert small.assessments[0].verdict is Verdict.NOT_EVALUABLE
    assert "cannot resolve the claim" in small.assessments[0].root_cause
    assert "of the reported value" in small.assessments[0].root_cause
    # An abstention concluded nothing, so nothing is qualified on its behalf.
    assert small.assumptions == ()


# --- the error bar itself ------------------------------------------------------------------------


def test_the_jackknife_error_bar_matches_the_spread_across_independent_ensembles() -> None:
    """The measurement this abstention rule rests on, checked against what it predicts.

    A jackknife estimates how far the statistic would move on another draw. So draw again: twelve
    independent ensembles under twelve seeds, and compare their actual spread to the error bar one
    of them reports. Agreement to within a third is the claim being made — an error bar is an
    order-of-magnitude instrument, and one that was wrong by a factor of three would move the
    abstention boundary by a factor of three.
    """
    def fano_of(seed: int) -> float:
        ensemble = ensemble_final_counts(
            1, _IMMIGRATION_DEATH, [0], duration=40.0, trajectories=500, seed=seed
        )
        values = [run[0] for run in ensemble]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return variance / mean

    draws = [fano_of(seed) for seed in range(100, 112)]
    centre = sum(draws) / len(draws)
    empirical = math.sqrt(sum((d - centre) ** 2 for d in draws) / (len(draws) - 1))

    one = ensemble_final_counts(1, _IMMIGRATION_DEATH, [0], duration=40.0, trajectories=500, seed=100)
    estimated = noise_standard_error([run[0] for run in one], NoiseStatistic.FANO_FACTOR)
    assert estimated is not None
    assert 0.67 < estimated / empirical < 1.5
    # And it lands where the Poisson theory says it should: sqrt(2/n) for a Fano factor of 1.
    assert abs(estimated - math.sqrt(2 / 500)) < 0.02


def test_the_error_bar_is_deterministic() -> None:
    # It draws no random numbers of its own; a bootstrap would, and this class's verdicts are a
    # function of one pinned seed.
    one = ensemble_final_counts(1, _IMMIGRATION_DEATH, [0], duration=40.0, trajectories=200, seed=7)
    values = [run[0] for run in one]
    first = noise_standard_error(values, NoiseStatistic.FANO_FACTOR)
    assert first == noise_standard_error(values, NoiseStatistic.FANO_FACTOR)


def test_one_trajectory_supports_no_error_bar() -> None:
    assert noise_standard_error([5], NoiseStatistic.FANO_FACTOR) is None


# --- the ways it abstains ------------------------------------------------------------------------


def test_an_ensemble_that_never_left_zero_abstains_rather_than_reporting_no_noise() -> None:
    # A pure death process from one molecule, run long: every trajectory ends at zero, so both
    # statistics divide by a zero mean. Judging it would publish "the spread is 0" as a measurement
    # of the model, when it is a statement about where the ensemble ended up.
    certificate = certify_stochastic(
        paper=PaperIdentity(title="pure death"), engine_pin=solver_pin(),
        n_species=1, reactions=[Reaction(1.0, ((0, 1),), ())], initial=[1],
        noises=[_claim(duration=50.0, trajectories=50)],
    )
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "no mean to normalize the spread by" in assessment.root_cause


def test_a_zero_spread_ensemble_below_the_bar_abstains() -> None:
    # Every trajectory lands on the same count, so the Fano factor is exactly 0 — and at this size
    # that is as likely an accident as a measurement. It is the same bar a mean is held to, and it
    # matters more here: a spread of zero *is* this claim's quantity, so publishing it would be a
    # confident `failed` against a model that may be exactly right.
    frozen = [Reaction(1.0, ((0, 1),), ((1, 1),))]  # A -> B, and B never moves
    certificate = certify_stochastic(
        paper=PaperIdentity(title="frozen"), engine_pin=solver_pin(),
        n_species=2, reactions=frozen, initial=[3, 0],
        noises=[_claim(species=1, duration=50.0, trajectories=5)],
    )
    assert certificate.assessments[0].verdict is Verdict.NOT_EVALUABLE
    assert "no spread at all" in certificate.assessments[0].root_cause


# --- what the claim refuses ----------------------------------------------------------------------


def test_a_single_trajectory_claim_is_refused() -> None:
    with pytest.raises(ValueError, match="one draw has none"):
        _claim(trajectories=1)


def test_a_claim_that_never_advances_is_refused() -> None:
    with pytest.raises(ValueError, match="never advances"):
        _claim(duration=0.0)


def test_a_reported_zero_is_refused_as_a_statement_about_the_sampling() -> None:
    with pytest.raises(ValueError, match="no spread at all"):
        _claim(reported_value=0.0)
