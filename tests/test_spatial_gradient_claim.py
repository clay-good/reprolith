"""Certifying a decay length: the spatial result a paper actually prints as a number.

This class could certify one thing — a whole reported concentration profile — which a paper almost
never prints as numbers. Reaching one needs a curator's figure digitization, the route this corpus
is blocked on. A **decay length** is a scalar in the text: `C(x) = C₀·e^{−x/λ}` with `λ = √(D/k)`
is the reportable quantity of developmental-biology gradient papers, and it is reachable by the
same table and prose extraction that already works.

The machinery was all here and none of it was certifiable: `morphogen_gradient` runs the model,
`gradient_decay_length` fits the length, and `tests/test_spatial.py` has validated both against the
closed form since the class landed. What was missing was a claim type joining them to the judge.
"""

from __future__ import annotations

import math

import pytest
from reprolith import (
    GradientClaim,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    certify_spatial,
)
from reprolith.spatial import solver_pin

_D, _K, _C0 = 1.0, 0.25, 100.0
_DX = 0.1
_DT = 0.2 * _DX * _DX / _D


def _claim(reported: float, **extra) -> GradientClaim:
    base = dict(
        claim_id="lambda", quantity="morphogen decay length", reported=reported,
        source_location="Fig 3 caption", source=_C0, diffusivity=_D, decay=_K,
        dx=_DX, points=300, dt=_DT, steps=40000, fit_from=20, fit_to=120,
    )
    base.update(extra)
    return GradientClaim(**base)


def _certify(*claims: GradientClaim):
    return certify_spatial(
        paper=PaperIdentity(title="gradient paper", doi=""),
        engine_pin=solver_pin(),
        gradients=list(claims),
    )


# --- the claim reproduces what the closed form says ---------------------------------------------


def test_a_reported_decay_length_reproduces_against_the_analytical_one() -> None:
    """Non-circular: the reported value is `√(D/k)`, and the predicted one is fitted from a run
    of the discretized model. Nothing in the run is told what the answer is."""
    cert = _certify(_claim(math.sqrt(_D / _K)))
    assert cert.assessments[0].verdict is Verdict.REPRODUCED
    assert cert.overall is OverallVerdict.REPRODUCED


def test_a_wrong_reported_length_fails_with_a_stated_cause() -> None:
    """The class has to be able to get this *wrong* loudly, or its passes mean nothing."""
    assessment = _certify(_claim(3.5)).assessments[0]
    assert assessment.verdict is Verdict.FAILED
    assert assessment.root_cause, "a published miss has to say what missed"


def test_a_gradient_carries_no_boundary_assumption() -> None:
    """Its walls *are* the model — a fixed source at one end, a zero-flux far field — not a choice
    this engine made in the absence of one. Qualifying it would overstate the uncertainty, which
    is the same defect as understating it.
    """
    cert = _certify(_claim(math.sqrt(_D / _K)))
    assert cert.assumptions == ()
    assert cert.assessments[0].assumption_qualified is False


# --- what the certificate records so the number can be re-derived -------------------------------


def test_the_protocol_records_every_input_that_moves_the_number() -> None:
    protocol = _certify(_claim(2.0)).assessments[0].protocol
    for expected in ("source=100.0", "D=1.0", "k=0.25", "dx=0.1", "40000 steps", "300 points"):
        assert expected in protocol, expected
    # The fitting window is a judgement the claim makes, so it is recorded rather than implied.
    assert "[20, 120)" in protocol
    # And the continuum length, which answers a different question from the judged one: what the
    # equation says, beside what the discretized run produced.
    assert "continuum length is 2" in protocol


# --- what it refuses, and what it abstains on ---------------------------------------------------


def test_a_gradient_without_degradation_has_no_length_scale_and_is_refused() -> None:
    with pytest.raises(ValueError, match="no length scale"):
        _claim(2.0, decay=0.0)


def test_a_fitting_window_outside_the_grid_is_refused() -> None:
    with pytest.raises(ValueError, match="not a window inside the grid"):
        _claim(2.0, fit_from=250, fit_to=400)
    with pytest.raises(ValueError, match="not a window inside the grid"):
        _claim(2.0, fit_from=120, fit_to=20)


def test_an_unstable_discretization_abstains_rather_than_raising() -> None:
    """As every other path in this class does: one unusable claim must not discard the honest
    verdicts of its siblings, and "this protocol cannot decide this claim" is an abstention."""
    assessment = _certify(_claim(2.0, dt=_DT * 100)).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "unstable discretization" in assessment.root_cause


def test_a_window_that_does_not_decay_abstains_rather_than_publishing_a_slope() -> None:
    """A least-squares slope through a flat or *rising* stretch returns a number, and publishing
    it as a length would be a verdict about a fit nobody could make. Note what this is not: the
    far tail of a real gradient still decays, only slowly, so a window there produces an honest
    miss rather than an abstention — the window is the claim's own and the protocol records it.
    """
    rising = _claim(2.0, source=0.0, fit_from=1, fit_to=40)
    assessment = _certify(rising).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "decay length" in assessment.root_cause


def test_a_badly_chosen_window_is_a_miss_and_the_protocol_says_which_window() -> None:
    """The far tail decays too slowly to give the gradient's length. That is the curator's window,
    not the engine's, so it produces a stated miss rather than an abstention — and the number can
    be traced to the choice that produced it."""
    assessment = _certify(_claim(2.0, fit_from=295, fit_to=300)).assessments[0]
    assert assessment.verdict is Verdict.FAILED
    assert "[295, 300)" in assessment.protocol


# --- the front-end's contract -------------------------------------------------------------------


def test_a_certificate_of_no_claims_is_refused() -> None:
    """Certifying a paper this class judged nothing of would publish a verdict about no evidence."""
    with pytest.raises(ValueError, match="at least one claim"):
        certify_spatial(
            paper=PaperIdentity(title="nothing", doi=""), engine_pin=solver_pin()
        )


def test_profile_and_gradient_claims_travel_on_one_certificate() -> None:
    """One paper reports both kinds, so one certificate has to carry both — and the boundary
    assumption attaches to the profile claim alone."""
    from reprolith.spatial import SpatialClaim, gaussian_profile

    length, points = 20.0, 201
    dx = 2 * length / (points - 1)
    centers = [-length + i * dx for i in range(points)]
    dt = 0.2 * dx * dx / 1.0
    initial = tuple(gaussian_profile(centers, mass=10.0, variance=1.0))
    reference = tuple(gaussian_profile(centers, mass=10.0, variance=1.0 + 2 * 400 * dt))
    cert = certify_spatial(
        paper=PaperIdentity(title="both", doi=""),
        engine_pin=solver_pin(),
        claims=[SpatialClaim(
            claim_id="profile", quantity="profile", initial=initial, reference=reference,
            source_location="Fig 2", diffusivity=1.0, dx=dx, dt=dt, steps=400,
        )],
        gradients=[_claim(math.sqrt(_D / _K))],
    )
    assert [a.claim_id for a in cert.assessments] == ["profile", "lambda"]
    assert [a.id for a in cert.assumptions] == ["spatial-boundary-profile"]
