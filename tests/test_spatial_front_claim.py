"""Certifying an invasion front speed: the other spatial scalar a paper prints.

Fisher-KPP — `u_t = D u_xx + r·u(1−u)` — is the canonical invasion and growth-front model, and its
asymptotic speed `c = 2√(rD)` is the number ecology and epidemic-wave papers report. Like a decay
length and unlike a whole profile, it is a scalar in the text, so it is reachable without a curator
digitizing a figure.

The subtlety this claim has and the gradient does not: **a measured KPP speed sits a few percent
below** `2√(rD)`, so the class-default 5% would fail a correct reproduction. It is not a tolerance
to widen quietly — the claim measures the speed over two consecutive windows and reports how much
it is still changing, and a wider tolerance has to be a stated override.

Which cause dominates was measured after the fact and it is not the front's logarithmic approach,
which is what this file first said: halving `dt` halves the deficit (1.9154 at a diffusion number
of 0.2, 1.9617 at 0.1, 1.9856 at 0.05), so most of it is the explicit stepper's own O(dt) error.
The second engine measures 2.0100 over the same window, and the milestone publishes that 4.7%
disagreement rather than widening it away.
"""

from __future__ import annotations

import math

import pytest
from reprolith import (
    FrontSpeedClaim,
    OverallVerdict,
    PaperIdentity,
    Tolerance,
    ToleranceSource,
    Verdict,
    certify_spatial,
)
from reprolith.spatial import solver_pin

_D, _R = 1.0, 1.0
_DX = 0.5
_DT = 0.2 * _DX * _DX / _D
_POINTS = 1201  # [0, 600]: long enough that the front never reaches the wall
_WINDOW = round(100.0 / _DT)

#: The finite-time bias is known and stated, so the override is principled rather than a magic
#: number — the same tolerance `tests/test_spatial.py` has used for this system since it landed.
_TOL = Tolerance(
    0.10, 0.20, ToleranceSource.REVIEWER_OVERRIDE,
    rationale="the measured speed sits below 2*sqrt(rD) by the explicit stepper's O(dt) time error (4.2% at a diffusion number of 0.2, 1.9% at 0.1, 0.7% at 0.05) plus the KPP front's logarithmic finite-time approach; 10% covers both",
)


def _initial(points: int = _POINTS, dx: float = _DX) -> tuple[float, ...]:
    return tuple(1.0 if i * dx < 20.0 else 0.0 for i in range(points))


def _claim(**extra) -> FrontSpeedClaim:
    base = dict(
        claim_id="front", quantity="Fisher-KPP asymptotic front speed",
        reported=2.0 * math.sqrt(_R * _D), source_location="Table 2",
        initial=_initial(), diffusivity=_D, growth=_R, dx=_DX, dt=_DT,
        settle_steps=_WINDOW, measure_steps=_WINDOW, tolerance=_TOL,
    )
    base.update(extra)
    return FrontSpeedClaim(**base)


def _certify(*fronts: FrontSpeedClaim):
    return certify_spatial(
        paper=PaperIdentity(title="invasion paper", doi=""),
        engine_pin=solver_pin(),
        fronts=list(fronts),
    )


# --- the claim reproduces the closed form -------------------------------------------------------


def test_a_reported_front_speed_reproduces_against_the_analytical_one() -> None:
    """Non-circular: the reported value is `2√(rD)` and the predicted one is measured from the
    positions of a simulated front. Nothing in the run is told the answer."""
    cert = _certify(_claim())
    assert cert.assessments[0].verdict is Verdict.REPRODUCED
    assert cert.overall is OverallVerdict.REPRODUCED
    assert cert.assumptions == (), "a front is judged away from the walls, so it assumes no wall"


def test_a_wrong_reported_speed_fails_with_a_stated_cause() -> None:
    assessment = _certify(_claim(reported=5.0)).assessments[0]
    assert assessment.verdict is Verdict.FAILED
    assert assessment.root_cause


def test_the_finite_time_bias_is_measured_and_is_why_the_override_exists() -> None:
    """Measured rather than asserted, because the first version of this test asserted it and was
    wrong. The bias shrinks with run length: over 10-unit windows the measured speed is 9.5% below
    `2√(rD)`, over 25 it is 5.8%, and over 100 it is 4.2%. So the class-default 5% fails a
    *correct* reproduction at the shorter runs and passes at the longer ones — which is exactly
    why the override has to state its reason rather than being a widened number.
    """
    short = round(10.0 / _DT)
    at_default = _certify(
        _claim(settle_steps=short, measure_steps=short, tolerance=None)
    ).assessments[0]
    assert at_default.verdict is not Verdict.REPRODUCED, "a correct model, missed at the default"
    with_override = _certify(_claim(settle_steps=short, measure_steps=short)).assessments[0]
    assert with_override.verdict is Verdict.REPRODUCED
    # And the long run is inside the default, so the override is not load-bearing everywhere.
    assert _certify(_claim(tolerance=None)).assessments[0].verdict is Verdict.REPRODUCED


# --- what the certificate records ---------------------------------------------------------------


def test_the_protocol_reports_how_far_the_front_is_from_having_settled() -> None:
    """The number that separates "still converging" from "converged and biased" — without it a
    reader cannot tell whether a few percent low is the known logarithmic approach or a defect."""
    protocol = _certify(_claim()).assessments[0].protocol
    assert "still changes by" in protocol
    assert "how far the front is from having settled" in protocol
    # And every input the speed turns on.
    for expected in ("D=1.0", "r=1.0", "dx=0.5", "settling steps", "u=0.5", "continuum equation is 2"):
        assert expected in protocol, expected


# --- what it refuses and abstains on -------------------------------------------------------------


def test_a_front_with_no_growth_is_refused() -> None:
    with pytest.raises(ValueError, match="no advancing front"):
        _claim(growth=0.0)


def test_a_window_that_does_not_advance_the_model_is_refused() -> None:
    with pytest.raises(ValueError, match="must advance the model"):
        _claim(measure_steps=0)


def test_a_front_that_has_reached_the_wall_abstains_rather_than_reporting_the_wall() -> None:
    """Past the domain's end the wall holds the front, and the distance it "travelled" is the
    distance to the wall. That speed is confidently wrong, which is worse than absent — the
    front-speed analogue of the gradient's badly chosen fitting window."""
    short = 121  # [0, 60]: the front runs out of domain well inside the measuring window
    assessment = _certify(_claim(initial=_initial(short))).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "reached the end of the domain" in assessment.root_cause
    assert "saturated" in assessment.root_cause, (
        "a front that ran out of domain must not be reported as a front that never existed"
    )


def test_a_profile_with_no_front_abstains() -> None:
    """Nothing crosses the level, so there is no edge to follow."""
    empty = tuple(0.0 for _ in range(_POINTS))
    assessment = _certify(_claim(initial=empty)).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "no front at the" in assessment.root_cause
    assert "saturated" not in assessment.root_cause, "nothing ran out of domain here"


def test_an_unstable_discretization_abstains_rather_than_raising() -> None:
    assessment = _certify(_claim(dt=_DT * 100)).assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "unstable" in assessment.root_cause or "diffusion number" in assessment.root_cause


def test_the_certificate_says_what_its_time_step_costs_the_speed() -> None:
    """The rationale, turned into a per-claim measurement.

    A reader with only the settling drift cannot tell a converged-but-under-resolved measurement
    from a still-converging one, and this class published exactly that confusion for a day: the
    drift over the next window is 0.21% while halving the time step moves the speed by 2.4%, and
    the total deficit is 4.2%. Both numbers are on the certificate now, so which term dominates is
    read rather than believed.
    """
    from reprolith.spatial import front_step_sensitivity

    assessment = _certify(_claim()).assessments[0]
    assert "Halving the time step moves this speed by" in assessment.protocol
    assert "which is how far the front is from having settled" in assessment.protocol
    moved = front_step_sensitivity(_claim())
    assert 0.02 < moved < 0.03, moved


def test_a_step_sensitivity_that_cannot_be_read_is_absent_rather_than_zero() -> None:
    """The halved run fails on the same domain the judged one does — a front that runs into the
    wall has no readable speed at either step — and a sensitivity of 0.0 there would say the
    stepper costs nothing, which is the opposite of what is known."""
    from reprolith.spatial import front_step_sensitivity

    short = _claim(initial=_initial(points=60), settle_steps=_WINDOW, measure_steps=_WINDOW)
    assert front_step_sensitivity(short) is None
