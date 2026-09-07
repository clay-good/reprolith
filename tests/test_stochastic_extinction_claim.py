"""Certifying a reported **mean time to extinction**: this class's first-passage target.

`time_to_extinction` has been in this package with its censoring semantics worked out — a run that
reaches the cap returns infinity rather than the cap, because returning `t` made a censored run
indistinguishable from a first passage — and no claim type could certify one. It is the quantity
population-dynamics and resistance papers report (how long a small population, or a drug-resistant
clone, persists), and like a decay length and unlike a distribution it is a number a paper prints.

The ground truth here is closed-form and needs no external tool: a pure death process `X -> 0` at
rate `k` per molecule leaves the mean extinction time from `n0` molecules at `H(n0)/k`, the
harmonic number over the rate, because the wait in state `i` is exponential with rate `k·i`.
"""

from __future__ import annotations

import pytest
from reprolith import (
    ExtinctionTimeClaim,
    PaperIdentity,
    Reaction,
    Tolerance,
    ToleranceSource,
    certify_stochastic,
)
from reprolith.enums import OverallVerdict, Verdict
from reprolith.stochastic import solver_pin

_K, _N0 = 1.0, 5
_DEATH = [Reaction(reactants=((0, 1),), products=(), rate=_K)]
#: H(n0)/k — the exact mean first passage to zero.
_EXACT = sum(1.0 / (_K * i) for i in range(1, _N0 + 1))


def _claim(**kw) -> ExtinctionTimeClaim:
    base = dict(
        claim_id="tex",
        quantity="mean time to extinction",
        species=0,
        reported_mean=_EXACT,
        source_location="Table 1",
        trajectories=2000,
        seed=20260907,
        max_time=1e6,
    )
    base.update(kw)
    return ExtinctionTimeClaim(**base)


def _certify(claim: ExtinctionTimeClaim):
    return certify_stochastic(
        paper=PaperIdentity(title="a pure death process"),
        engine_pin=solver_pin(),
        n_species=1,
        reactions=_DEATH,
        initial=[_N0],
        extinctions=[claim],
    )


def test_a_reported_extinction_time_reproduces_against_the_closed_form() -> None:
    """Non-circular: the reported value is `H(n0)/k` and the predicted one is the mean of 2000
    seeded first passages. Nothing in the run is told what the answer is."""
    certificate = _certify(_claim())
    (assessment,) = certificate.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    # And the ensemble's own noise, on the certificate rather than in a reader's head.
    assert "the mean's standard error is 1.17% of the reported value" in assessment.protocol
    assert "2000 trajectories, seed 20260907" in assessment.protocol
    assert "capped at t=1000000.0" in assessment.protocol


def test_the_verdict_rests_on_an_ensemble_this_engine_chose_and_says_so() -> None:
    certificate = _certify(_claim())
    (assumption,) = certificate.assumptions
    assert assumption.id == "ssa-sampling-tex"
    assert assumption.load_bearing
    # No wording in a paper clears it: the ensemble is Reprolith's draw, not the paper's run.
    assert assumption.author_can_close is False
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED
    # One question for a class, not one per claim — the queue keys items by their wording.
    from reprolith.stochastic import _SAMPLING_BASIS

    assert assumption.basis == _SAMPLING_BASIS


def test_a_run_that_observed_no_extinction_abstains_rather_than_averaging_the_rest() -> None:
    """The reason `time_to_extinction` returns infinity rather than the cap, carried through to a
    verdict: a mean over the trajectories that finished is the mean of a *conditioned* sample,
    short by an amount the sample itself cannot bound. Averaging past it is how a cap silently
    becomes the answer."""
    assessment = _certify(_claim(max_time=0.5, trajectories=200)).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "reached the 0.5 cap without the species going extinct" in assessment.root_cause
    assert "conditioned sample" in assessment.root_cause


def test_an_ensemble_too_small_to_decide_the_claim_abstains() -> None:
    """The same rule the mean count is held to: where the standard error is more than half the pass
    threshold, a correct model routinely misses and a wrong one routinely passes."""
    assessment = _certify(_claim(trajectories=8)).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "cannot resolve" in assessment.root_cause


def test_a_stated_tolerance_travels_with_its_reason() -> None:
    wide = Tolerance(
        0.10, 0.20, ToleranceSource.REVIEWER_OVERRIDE,
        rationale="a first-passage mean is heavy-tailed; this ensemble resolves 1.2%",
    )
    assessment = _certify(_claim(tolerance=wide)).assessments[0]
    assert assessment.verdict is Verdict.REPRODUCED
    assert "against a 10% pass threshold" in assessment.protocol


@pytest.mark.parametrize(
    "kw,message",
    [
        ({"trajectories": 1}, "needs an ensemble"),
        ({"max_time": 0.0}, "observes no extinction"),
    ],
)
def test_a_claim_that_could_not_be_a_measurement_is_refused(kw, message) -> None:
    with pytest.raises(ValueError, match=message):
        _claim(**kw)


def test_a_certificate_of_nothing_is_refused() -> None:
    """Both claim lists empty is a paper this class judged nothing of, and publishing a verdict
    about no evidence is what every other class front-end refuses too."""
    with pytest.raises(ValueError, match="needs at least one claim"):
        certify_stochastic(
            paper=PaperIdentity(title="nothing"), engine_pin=solver_pin(),
            n_species=1, reactions=_DEATH, initial=[_N0],
        )
