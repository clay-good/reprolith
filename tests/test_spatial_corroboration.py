"""A second engine for the spatial class: scipy's LSODA against this package's explicit stepper.

The last of the six classes to get one, and the one where being exact about what "a second engine"
buys matters most. Reprolith advances the diffusion equation with a fixed-step explicit
forward-Euler stepper; this re-solves the same semi-discrete system by method of lines under
LSODA — adaptive order, adaptive step, implicit where the problem is stiff, and Fortran code this
package shares nothing with.

So the comparison isolates the **time integration**: a profile the two agree on is the differential
equation's rather than an artifact of stepping it explicitly at this dt. It does not isolate the
spatial discretization, which both sides take as second-order central differences with the boundary
cell mirrored — that is the scheme the class certifies under, and two implementations of one scheme
agree about the scheme's error. The tests below assert both halves, because the limit is as much
the result as the agreement is.

Needs scipy (the ``fba`` or ``corroborate`` extra).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("scipy", reason="scipy (the 'fba' or 'corroborate' extra) is not installed")

from reprolith import corroborate_profile, gaussian_profile  # noqa: E402
from reprolith.oracle import normalized_curve_distance  # noqa: E402
from reprolith.spatial import diffuse_1d  # noqa: E402

_MILESTONE = Path(__file__).parent.parent / "datasets" / "spatial" / "milestone"

_L, _N = 20.0, 201
_DX = 2 * _L / (_N - 1)
_CENTERS = [-_L + i * _DX for i in range(_N)]
_DIFFUSION_NUMBER = 0.2

#: The three systems the spatial milestone certifies, at the discretization each was certified on.
_SYSTEMS = {
    "diffusion_D1": (1.0, 1.0, 10.0, 1000),
    "diffusion_D2": (2.0, 1.5, 7.0, 800),
    "diffusion_Dhalf": (0.5, 2.0, 5.0, 1200),
}


def _committed() -> dict:
    return json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))


def _run(key: str):
    diffusivity, variance, mass, steps = _SYSTEMS[key]
    return corroborate_profile(
        gaussian_profile(_CENTERS, mass=mass, variance=variance),
        diffusivity=diffusivity,
        dx=_DX,
        dt=_DIFFUSION_NUMBER * _DX * _DX / diffusivity,
        steps=steps,
    )


@pytest.mark.parametrize("key", sorted(_SYSTEMS))
def test_each_certified_profile_agrees_with_scipys_stiff_integrator(key: str) -> None:
    """The committed record is reproduced rather than merely present.

    Every field but the engine builds: a record has to keep naming the build it was measured on
    rather than borrowing the one installed today, so that is the one field a reproduction check
    cannot demand.
    """
    result = _run(key)
    assert result.stable, result.summary()
    measured = {k: v for k, v in result.record().items() if k != "engine_versions"}
    committed = {k: v for k, v in _committed()[key].items() if k != "engine_versions"}
    assert measured == committed


def test_the_gap_is_the_explicit_stepper_s_own_error_and_not_a_disagreement() -> None:
    """1.2e-04, which is what forward-Euler at this dt costs — and it shrinks when dt does.

    A published agreement that did not move with the step size would be measuring something else.
    Halving dt (and doubling the steps, so the physical time is unchanged) should roughly halve
    the distance, because forward-Euler's error is first order in dt. That is the check that the
    number is the *time* discretization rather than a fixed offset between two implementations.
    """
    diffusivity, variance, mass, steps = _SYSTEMS["diffusion_D1"]
    profile = gaussian_profile(_CENTERS, mass=mass, variance=variance)
    coarse_dt = _DIFFUSION_NUMBER * _DX * _DX / diffusivity
    coarse = corroborate_profile(
        profile, diffusivity=diffusivity, dx=_DX, dt=coarse_dt, steps=steps
    ).distance
    fine = corroborate_profile(
        profile, diffusivity=diffusivity, dx=_DX, dt=coarse_dt / 2, steps=steps * 2
    ).distance
    assert coarse == pytest.approx(1.2e-4, rel=0.2)
    # First order: halving dt halves the error. Bracketed loosely — the point is the trend, not a
    # convergence-rate measurement.
    assert 1.7 < coarse / fine < 2.3, (coarse, fine)


def test_the_gap_is_not_a_distance_from_the_truth_and_the_numbers_say_which_way() -> None:
    """The reading this comparison invites, and why it is wrong.

    "The two engines differ by 1.2e-04" reads as Reprolith being 1.2e-04 wrong. It is not. LSODA
    integrates the *semi-discrete* system essentially exactly, so the gap is what forward-Euler's
    time stepping costs against that system — and against the continuum solution the explicit
    scheme does **better** than that, not worse: 2.0e-05 from the closed-form Gaussian, six times
    closer than the engines are to each other.

    The reason is a known property of this scheme rather than luck. Central differencing in space
    and forward Euler in time have truncation errors of opposite sign, and at a diffusion number
    of 1/6 they cancel exactly; the milestone runs at 0.2, near enough for most of the cancellation.
    So the corroboration's number is a statement about two discretizations differing, and the
    certificate's own discrepancy is the one that says how close the profile is to the truth. Both
    are asserted here so neither can be quoted as the other.
    """
    diffusivity, variance, mass, steps = _SYSTEMS["diffusion_D1"]
    dt = _DIFFUSION_NUMBER * _DX * _DX / diffusivity
    profile = gaussian_profile(_CENTERS, mass=mass, variance=variance)
    mine = diffuse_1d(profile, diffusivity=diffusivity, dx=_DX, dt=dt, steps=steps)
    closed_form = gaussian_profile(
        _CENTERS, mass=mass, variance=variance + 2 * diffusivity * dt * steps
    )
    from_truth = normalized_curve_distance(mine, closed_form)
    from_the_other_engine = corroborate_profile(
        profile, diffusivity=diffusivity, dx=_DX, dt=dt, steps=steps
    ).distance
    assert from_truth == pytest.approx(2.0e-5, rel=0.2)
    assert from_truth < from_the_other_engine / 3


def test_a_configuration_this_class_refuses_is_never_compared() -> None:
    """An unstable discretization is refused before anything is integrated.

    Reprolith will not run a diffusion number above 0.5, so publishing an agreement at one would
    describe a configuration no certificate can be issued under. The refusal comes from the class's
    own solver, which is why it is run first.
    """
    profile = gaussian_profile(_CENTERS, mass=10.0, variance=1.0)
    with pytest.raises(ValueError):
        corroborate_profile(
            profile, diffusivity=1.0, dx=_DX, dt=0.9 * _DX * _DX, steps=10
        )


def test_decay_is_carried_to_the_second_engine() -> None:
    """The class solves diffusion *and* first-order decay; a reference that dropped the sink would
    disagree by the whole decayed fraction and read as engine sensitivity."""
    profile = gaussian_profile(_CENTERS, mass=10.0, variance=1.0)
    dt = _DIFFUSION_NUMBER * _DX * _DX / 1.0
    with_decay = corroborate_profile(
        profile, diffusivity=1.0, dx=_DX, dt=dt, steps=400, decay=0.5
    )
    assert with_decay.stable, with_decay.summary()
    # And the decayed run really is a different profile from the undecayed one, so the agreement
    # above is not being reached by both sides ignoring `decay`.
    plain = diffuse_1d(profile, diffusivity=1.0, dx=_DX, dt=dt, steps=400)
    decayed = diffuse_1d(profile, diffusivity=1.0, dx=_DX, dt=dt, steps=400, decay=0.5)
    assert normalized_curve_distance(plain, decayed) > 0.1


# --- the two scalars, which `corroborate_profile` cannot reach ----------------------------------


def test_a_decay_length_is_corroborated_on_the_quantity_the_certificate_publishes() -> None:
    """`corroborate_profile` re-solves a profile; a decay length is read *off* a run rather than
    being one, so the class's two scalar certificates stood with no second engine at all. What is
    compared is the fitted length — the number the certificate publishes — not the profile."""
    from reprolith.corroboration import corroborate_gradient_length

    dx = 0.1
    result = corroborate_gradient_length(
        source=100.0, diffusivity=1.0, decay=0.25, dx=dx, points=300,
        dt=_DIFFUSION_NUMBER * dx * dx, steps=40000, fit_from=20, fit_to=120,
    )
    assert result.quantity == "morphogen decay length"
    assert result.engines == ("reprolith-fd", "scipy-lsoda")
    # A steady state is the same fixed point for both integrators, so this one is not a statement
    # about the time stepping at all — which is why the front below is the interesting half.
    assert result.stable
    assert result.distance < 1e-6


def test_the_two_engines_disagree_about_the_front_speed_and_it_is_published() -> None:
    """The finding this comparison exists for. The front claim's tolerance was attributed to the
    KPP front's logarithmic approach to its asymptote; the second engine, integrating the same
    semi-discrete system essentially exactly in time over the same window, measures 2.0100 where
    this package's explicit stepper measures 1.9154. That is the stepper's own O(dt) error, and it
    is reported as a disagreement rather than widened away."""
    from reprolith.corroboration import corroborate_front_speed

    dx = 0.5
    dt = _DIFFUSION_NUMBER * dx * dx
    window = round(100.0 / dt)
    result = corroborate_front_speed(
        initial=tuple(1.0 if i * dx < 20.0 else 0.0 for i in range(1201)),
        diffusivity=1.0, growth=1.0, dx=dx, dt=dt,
        settle_steps=window, measure_steps=window,
    )
    assert result.quantity == "Fisher-KPP asymptotic front speed"
    assert not result.stable, "the two engines agree here, which they did not when this was written"
    assert 0.04 < result.distance < 0.06


def test_halving_the_time_step_halves_the_front_speed_deficit() -> None:
    """Why the disagreement above is the *stepper* and not the front: at a fixed window, refining
    dt walks the measured speed toward the second engine's 2.0100, first-order. Attributing it to
    the logarithmic approach — as this class's own docstrings did — would have been a rationale
    nobody had measured."""
    import math

    from reprolith import front_position, react_diffuse_1d

    dx, points = 0.5, 1201
    initial = [1.0 if i * dx < 20.0 else 0.0 for i in range(points)]
    speeds = []
    for number in (0.2, 0.1, 0.05):
        dt = number * dx * dx
        window = round(100.0 / dt)

        def run(state, steps=window, dt=dt):
            return react_diffuse_1d(
                state, diffusivity=1.0, dx=dx, dt=dt, steps=steps,
                reaction=lambda u: u * (1.0 - u),
            )

        settled = run(initial)
        measured = run(settled)
        start = front_position(settled, dx=dx, level=0.5)
        end = front_position(measured, dx=dx, level=0.5)
        speeds.append((end - start) / (window * dt))
    deficits = [(2.0 * math.sqrt(1.0) - speed) / 2.0 for speed in speeds]
    assert deficits[0] == pytest.approx(0.042, abs=0.003)
    assert deficits[1] == pytest.approx(0.019, abs=0.003)
    assert deficits[2] == pytest.approx(0.007, abs=0.003)
    # Halving dt roughly halves the deficit: first order in time, which is what forward Euler is.
    assert 1.8 < deficits[0] / deficits[1] < 2.6
    assert 1.8 < deficits[1] / deficits[2] < 3.0


def test_every_milestone_entry_carries_a_corroboration_record() -> None:
    """The absence the scalars published when they landed is closed, and this is what keeps it
    closed: a sixth entry added without a second engine fails here rather than being counted as
    corroborated by a summary that can only see records."""
    records = json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))
    certificates = {path.stem for path in (_MILESTONE / "certificates").glob("*.json")}
    assert set(records) == certificates
    assert records["front_speed"]["engine_independent"] is False, (
        "the committed record says the two engines agree about the front speed; re-run "
        "scripts/run_spatial_milestone.py, and if they now do, say so here"
    )


def test_the_selected_wavelength_survives_a_different_integrator() -> None:
    """The contrast that makes this worth running, beside the front's 4.7% disagreement.

    A front speed is a *rate* read from a moving feature, so the time discretization moves it. A
    wavelength is a **selected mode** — which perturbation grows fastest, and how the nonlinearity
    saturates it — so it either survives a different integrator or it does not, with nothing in
    between. Both engines select mode 20 here, and the comparison is published as an exact match
    rather than as a distance of zero, which would read as six orders better than the curve
    classes when it is a different kind of statement.
    """
    from reprolith import PatternClaim
    from reprolith.corroboration import corroborate_pattern_wavelength

    length, dx = 160.0, 0.5
    claim = PatternClaim(
        claim_id="stripes", quantity="Turing pattern wavelength", reported=16.0,
        source_location="closed-form", kinetics="schnakenberg", a=0.1, b=0.9,
        du=1.0, dv=40.0, length=length, points=int(round(length / dx)) + 1,
        dt=0.0015, steps=6000, confirm_steps=2000,
    )
    result = corroborate_pattern_wavelength(claim)
    assert result.comparison == "exact-match"
    assert result.stable
    assert result.distance == 0.0
    assert result.engines == ("reprolith-fd", "scipy-lsoda")


def test_a_claim_this_class_declines_to_measure_has_nothing_to_corroborate() -> None:
    """A comparison against a claim Reprolith itself abstains on would be a number about nothing,
    so it refuses by name rather than integrating anything."""
    from reprolith import PatternClaim
    from reprolith.corroboration import EngineUnavailable, corroborate_pattern_wavelength

    unresolvable = PatternClaim(
        claim_id="short", quantity="Turing pattern wavelength", reported=16.0,
        source_location="closed-form", kinetics="schnakenberg", a=0.1, b=0.9,
        du=1.0, dv=40.0, length=40.0, points=201, dt=0.0002, steps=100, confirm_steps=100,
    )
    with pytest.raises(EngineUnavailable, match="measures no wavelength"):
        corroborate_pattern_wavelength(unresolvable)
