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
