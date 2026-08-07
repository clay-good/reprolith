"""The spatial reaction-diffusion model class (spec: spatial-class).

Self-validated non-circularly against the exact analytical diffusion solution — no external tool,
no fabricated data. The finite-difference solver is pure Python and deterministic, so this runs in
the core CI job.
"""

from __future__ import annotations

import pytest
from reprolith import Verdict, diffuse_1d, gaussian_profile, judge_curve

_L, _N = 20.0, 201
_DX = 2 * _L / (_N - 1)
_CENTERS = [-_L + i * _DX for i in range(_N)]


def test_pure_diffusion_reproduces_the_analytical_gaussian() -> None:
    # Diffusion of a Gaussian is a Gaussian whose variance grows by 2·D·t — an exact, closed-form
    # ground truth. The finite-difference profile must reproduce it.
    D, var0, mass = 1.0, 1.0, 10.0
    dt = 0.4 * _DX * _DX / D  # below the explicit stability limit of 0.5
    steps = 500
    elapsed = steps * dt
    initial = gaussian_profile(_CENTERS, mass=mass, variance=var0)
    simulated = diffuse_1d(initial, diffusivity=D, dx=_DX, dt=dt, steps=steps)
    analytic = gaussian_profile(_CENTERS, mass=mass, variance=var0 + 2 * D * elapsed)

    verdict = judge_curve(
        claim_id="Cx", quantity="diffused concentration profile",
        source_location="analytical Gaussian diffusion", reference=analytic, predicted=simulated,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    assert verdict.method == "curve-normalized-distance"


def test_diffusion_conserves_mass_under_zero_flux_boundaries() -> None:
    initial = gaussian_profile(_CENTERS, mass=7.0, variance=1.5)
    final = diffuse_1d(initial, diffusivity=2.0, dx=_DX, dt=0.3 * _DX * _DX / 2.0, steps=300)
    # Zero-flux boundaries conserve the integral ∫C dx (Riemann sum with spacing dx).
    assert sum(final) * _DX == pytest.approx(7.0, abs=1e-6)


def test_unstable_discretization_is_rejected() -> None:
    initial = gaussian_profile(_CENTERS, mass=1.0, variance=1.0)
    # D·dt/dx² = 1.0 > 0.5: the explicit scheme would diverge, so it must raise.
    with pytest.raises(ValueError, match="unstable"):
        diffuse_1d(initial, diffusivity=1.0, dx=_DX, dt=_DX * _DX, steps=10)


def test_first_order_decay_matches_the_exponential_analytical_solution() -> None:
    # A spatially uniform field with decay k obeys C(t) = C0·e^{-k t} everywhere, independent of
    # diffusion (a flat profile has zero Laplacian) — another exact check of the reaction term.
    k = 0.5
    dt = 0.4 * _DX * _DX / 1.0
    steps = 200
    flat = [3.0] * _N
    final = diffuse_1d(flat, diffusivity=1.0, dx=_DX, dt=dt, steps=steps, decay=k)
    expected = 3.0 * (1.0 - k * dt) ** steps  # the scheme's forward-Euler decay factor
    assert final[_N // 2] == pytest.approx(expected, rel=1e-9)
    assert all(abs(v - final[_N // 2]) < 1e-9 for v in final)  # stays spatially uniform


def test_solver_is_deterministic() -> None:
    initial = gaussian_profile(_CENTERS, mass=5.0, variance=2.0)
    a = diffuse_1d(initial, diffusivity=1.0, dx=_DX, dt=0.2 * _DX * _DX, steps=100)
    b = diffuse_1d(initial, diffusivity=1.0, dx=_DX, dt=0.2 * _DX * _DX, steps=100)
    assert a == b


def test_spatial_dossier_records_diffusivities_and_boundary_gap() -> None:
    from reprolith import DossierClaim, GapKind, spatial_dossier

    dossier = spatial_dossier(
        "morphogen", species=["M"], diffusivities={"M": 1.0}, source_location="Eq 3",
        boundary_stated=False,
        claims=[DossierClaim(id="grad", quantity="gradient profile", conditions="", source_location="Fig 2")],
    )
    assert dossier.state_variables == ("M",)
    assert dossier.parameters[0].name == "D_M"
    # An unstated domain/boundary condition is a load-bearing gap.
    assert len(dossier.load_bearing_gaps()) == 1
    assert dossier.load_bearing_gaps()[0].kind is GapKind.BOUNDARY


def test_lint_diffusion_inline_verdict_and_mcp_registration() -> None:
    from reprolith import lint_diffusion
    from reprolith.mcp_server import TOOL_DEFINITIONS

    assert "lint_diffusion" in {t["name"] for t in TOOL_DEFINITIONS}
    D = 1.0
    dt = 0.4 * _DX * _DX / D
    steps = 500
    initial = gaussian_profile(_CENTERS, mass=10.0, variance=1.0)
    reference = gaussian_profile(_CENTERS, mass=10.0, variance=1.0 + 2 * D * steps * dt)
    result = lint_diffusion(initial, reference, diffusivity=D, dx=_DX, dt=dt, steps=steps)
    assert result.verdict is Verdict.REPRODUCED
    assert result.method == "curve-normalized-distance"
    assert result.scope.machine == "reproducible-not-correct-not-clinical"
