"""A Turing pattern's selected wavelength, and the three things that make it certifiable.

This class's third scalar, and the one its own source said could not be written: a two-species
reaction has no canonical parameterization, so a claim carrying a callable could not be re-derived
from its certificate. Naming the family resolves that — `TURING_KINETICS` holds three with their
rate laws, steady states and Jacobians, and a claim states one plus its two parameters.

Two facts measured while writing it decide the rest of the design:

* **The selected mode moves while the pattern grows.** On the Schnakenberg configuration below it
  is 22 at t=3, 21 at t=6 and 20 from t=9 on. A wavelength read at an arbitrary step count is the
  pattern still forming, so a claim states a confirming window and abstains when the mode changes
  across it.
* **The nonlinear selection is not the linear prediction.** Linear stability picks m=21 here and the
  saturated pattern selects m=20 — 5% apart, which is the whole class-default tolerance. So the
  certificate judges the *measured* wavelength and reports the linear one beside it; certifying the
  closed form would publish 15.24 for a model that produces 16.0.
"""

from __future__ import annotations

import math

import pytest
from reprolith import (
    TURING_KINETICS,
    PaperIdentity,
    PatternClaim,
    certify_spatial,
    pattern_wavelength,
)
from reprolith.enums import OverallVerdict, Verdict
from reprolith.spatial import _judge_pattern, solver_pin

# The self-validation configuration: Schnakenberg at its textbook parameters, on a domain long
# enough to hold ~20 wavelengths — which is what it takes to resolve a wavelength to 5%, since the
# measurable values are 2L/m and neighbouring ones are 1/(m+1) apart.
LENGTH, DX = 160.0, 0.5
POINTS = int(round(LENGTH / DX)) + 1
DT = 0.24 * DX * DX / 40.0


def _claim(**kw) -> PatternClaim:
    base = dict(
        claim_id="stripe-spacing",
        quantity="Turing pattern wavelength",
        reported=16.0,
        source_location="Fig 1",
        kinetics="schnakenberg",
        a=0.1,
        b=0.9,
        du=1.0,
        dv=40.0,
        length=LENGTH,
        points=POINTS,
        dt=DT,
        steps=6000,
        confirm_steps=2000,
    )
    base.update(kw)
    return PatternClaim(**base)


# --- the kinetics families ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TURING_KINETICS))
@pytest.mark.parametrize("a,b", [(0.1, 0.9), (1.0, 3.0), (0.5, 2.0)])
def test_each_family_states_a_true_steady_state_and_its_own_jacobian(name, a, b) -> None:
    """The steady state and the Jacobian are written out per family rather than differenced, and a
    wrong entry would move every prediction on the certificate without failing anything else: the
    dispersion relation is built from these four numbers."""
    kinetics = TURING_KINETICS[name]
    u, v = kinetics.steady_state(a, b)
    assert abs(kinetics.reaction_u(u, v, a, b)) < 1e-12
    assert abs(kinetics.reaction_v(u, v, a, b)) < 1e-12
    h = 1e-6
    numerical = (
        (kinetics.reaction_u(u + h, v, a, b) - kinetics.reaction_u(u - h, v, a, b)) / (2 * h),
        (kinetics.reaction_u(u, v + h, a, b) - kinetics.reaction_u(u, v - h, a, b)) / (2 * h),
        (kinetics.reaction_v(u + h, v, a, b) - kinetics.reaction_v(u - h, v, a, b)) / (2 * h),
        (kinetics.reaction_v(u, v + h, a, b) - kinetics.reaction_v(u, v - h, a, b)) / (2 * h),
    )
    for stated, differenced in zip(kinetics.jacobian(a, b), numerical):
        assert stated == pytest.approx(differenced, rel=1e-5, abs=1e-6)


def test_a_family_this_class_does_not_implement_is_refused_by_name() -> None:
    """Approximating one reaction with a neighbouring one would certify the wrong model: the
    wavelength a paper reports is a property of its own kinetics."""
    with pytest.raises(ValueError, match="gray-scott"):
        _claim(kinetics="gray-scott")


def test_the_projection_finds_the_mode_a_field_is_made_of() -> None:
    xs = [i * DX for i in range(POINTS)]
    field = [3.0 + 0.25 * math.cos(7 * math.pi * x / LENGTH) for x in xs]
    mode, wavelength = pattern_wavelength(field, length=LENGTH, modes=range(1, POINTS), baseline=3.0)
    assert mode == 7
    assert wavelength == pytest.approx(2 * LENGTH / 7)


# --- what the run produces ----------------------------------------------------------------------


def test_the_settled_wavelength_is_certified_and_the_linear_prediction_travels_with_it() -> None:
    # Non-circular: the wavelength comes from the nonlinear run, the prediction from the Jacobian.
    # They differ by one mode here, which is the point — the certificate judges what the model
    # produced and states what the linearization expected.
    claim = _claim()
    assert claim.fastest_growing_mode == 21
    assert claim.analytical_wavelength == pytest.approx(2 * LENGTH / 21)

    certificate = certify_spatial(
        paper=PaperIdentity(title="Schnakenberg stripes"),
        engine_pin=solver_pin(),
        patterns=[claim],
    )
    (assessment,) = certificate.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    assert "Mode 20 won" in assessment.protocol
    assert "unchanged over a further 2000 steps" in assessment.protocol
    assert "linear stability predicts m=21" in assessment.protocol
    # The domain's own resolution, on the certificate rather than in a reader's head.
    assert "4.76%" in assessment.protocol

    # The wall decides which wavelengths are measurable at all, and this solver has one — so the
    # verdict rests on a choice Reprolith made and cannot read as a clean pass.
    (assumption,) = certificate.assumptions
    assert assumption.id == "spatial-pattern-boundary-stripe-spacing"
    assert assumption.load_bearing
    assert assumption.author_can_close is False
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED


def test_a_pattern_still_forming_abstains_rather_than_publishing_the_mode_it_is_passing_through() -> None:
    assessment = _judge_pattern(_claim(steps=4000, confirm_steps=2000))
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "has not settled" in assessment.root_cause
    assert "mode 21" in assessment.root_cause and "mode 20" in assessment.root_cause


def test_a_domain_too_coarse_to_tell_two_wavelengths_apart_abstains() -> None:
    """The measurable wavelengths are 2L/m, so their spacing near mode m is 1/(m+1) — a domain
    holding few wavelengths cannot tell a pass from a fail however precisely it agrees.

    On L=40 this pattern's own mode is 5, whose neighbours are 16.67% away against a 5% pass width,
    so the answer is available for the cost of a division and the run is never started. Resolving
    to 5% takes a mode above 19, which is why the self-validation domain is four times longer than
    the pattern it measures needs."""
    short = _claim(length=40.0, points=201, dt=0.24 * (40.0 / 200) ** 2 / 40.0, steps=100,
                   confirm_steps=100)
    assert short.fastest_growing_mode == 5
    assessment = _judge_pattern(short)
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "cannot resolve the claim" in assessment.root_cause
    assert "16.67% away while a pass is 5.00%" in assessment.root_cause


def test_the_resolution_rule_is_one_over_the_mode_plus_one() -> None:
    """The rule both checks share, so it is tested where it is written rather than twice through a
    simulation: measurable wavelengths are 2L/m, so the nearest neighbour of m is 1/(m+1) away."""
    from reprolith.spatial import _mode_resolution

    claim = _claim()
    for mode in (2, 5, 20, 43):
        assert _mode_resolution(claim, mode) == pytest.approx(1.0 / (mode + 1))


def test_a_run_that_settles_on_a_coarse_mode_is_caught_after_the_run_too(monkeypatch) -> None:
    """The pre-run check clears the domain at the mode linear stability predicts. A run that
    settles far below that is measured on a scale the cleared one says nothing about, so the same
    rule is asked again of the mode that actually won — forced here, since a configuration that
    does it takes minutes to grow."""
    import reprolith.spatial as spatial

    def peaked(field_values, *, length, modes, baseline):
        return {mode: 100.0 / (abs(mode - 3) + 1) for mode in modes}

    monkeypatch.setattr(spatial, "mode_amplitudes", peaked)
    assessment = _judge_pattern(_claim(steps=200, confirm_steps=200))
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "cannot resolve the claim" in assessment.root_cause
    assert "(mode 3)" in assessment.root_cause


def test_a_reaction_that_is_unstable_on_its_own_is_not_a_turing_pattern() -> None:
    # Brusselator with b > 1 + a^2 is oscillatory without diffusion: whatever grows is not
    # diffusion-driven, so its spacing is not a Turing wavelength.
    assessment = _judge_pattern(_claim(kinetics="brusselator", a=1.0, b=3.0, steps=10,
                                       confirm_steps=10))
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "not stable without diffusion" in assessment.root_cause


def test_a_run_stopped_before_anything_grew_abstains_rather_than_reporting_the_seed() -> None:
    """The broadband seed puts every mode at the same amplitude, so the "dominant" one before
    growth is whichever way the arithmetic fell. Measured on this configuration: every mode starts
    at 0.16 and the winner reaches 10.4 by the time the pattern has settled."""
    assessment = _judge_pattern(_claim(steps=200, confirm_steps=200))
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "no pattern formed" in assessment.root_cause
    assert "nothing has been selected" in assessment.root_cause


def test_a_stable_parameter_set_admits_no_growing_mode_and_abstains() -> None:
    # Equal diffusivities: no Turing instability is possible, so every admissible mode decays.
    assessment = _judge_pattern(_claim(du=1.0, dv=1.0, steps=10, confirm_steps=10))
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "no mode this domain admits grows" in assessment.root_cause


@pytest.mark.parametrize(
    "kw,message",
    [
        ({"steps": 0}, "must evolve the fields"),
        ({"confirm_steps": 0}, "second reading"),
        ({"seed_amplitude": 0.0}, "no perturbation"),
        ({"points": 2}, "at least one interior mode"),
        ({"length": 0.0}, "domain length"),
    ],
)
def test_a_claim_that_could_not_be_a_measurement_is_refused(kw, message) -> None:
    with pytest.raises(ValueError, match=message):
        _claim(**kw)
