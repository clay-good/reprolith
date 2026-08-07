"""The spatial reaction-diffusion model class (spec: spatial-class).

Self-validated non-circularly against the exact analytical diffusion solution — no external tool,
no fabricated data. The finite-difference solver is pure Python and deterministic, so this runs in
the core CI job.
"""

from __future__ import annotations

import math

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


def test_fisher_kpp_reproduces_the_analytical_front_speed() -> None:
    # The Fisher-KPP equation u_t = D u_xx + r u(1-u) — the canonical invasion/growth-front model —
    # develops a traveling wave whose asymptotic speed is c = 2*sqrt(rD), a closed-form ground truth.
    from reprolith import Tolerance, ToleranceSource, front_position, judge_scalar, react_diffuse_1d

    D, r = 1.0, 1.0
    analytic_speed = 2.0 * math.sqrt(r * D)
    dx = 0.5
    n = 1201  # domain [0, 600], long enough for the front not to reach the boundary
    dt = 0.2 * dx * dx / D
    u = [1.0 if i * dx < 20.0 else 0.0 for i in range(n)]

    def to_time(state, target_t):
        steps = round(target_t / dt)
        return react_diffuse_1d(state, diffusivity=D, dx=dx, dt=dt, steps=steps,
                                reaction=lambda c: r * c * (1.0 - c))

    at_100 = to_time(u, 100.0)
    at_200 = react_diffuse_1d(at_100, diffusivity=D, dx=dx, dt=dt, steps=round(100.0 / dt),
                              reaction=lambda c: r * c * (1.0 - c))
    speed = (front_position(at_200, dx=dx) - front_position(at_100, dx=dx)) / 100.0

    # KPP fronts approach 2*sqrt(rD) only logarithmically in time, and the explicit discretization
    # adds its own bias, so a finite-time measurement sits a few percent below — a known, stated
    # effect, so the tolerance is a principled override, not a magic number.
    tol = Tolerance(
        0.10, 0.20, ToleranceSource.REVIEWER_OVERRIDE,
        rationale="KPP front speed converges to 2*sqrt(rD) logarithmically; finite-time + "
                  "discretized measurement expected within ~10%",
    )
    verdict = judge_scalar(
        claim_id="front-speed", quantity="Fisher-KPP asymptotic front speed",
        source_location="analytical c=2*sqrt(rD)", reported=analytic_speed, predicted=speed,
        tolerance=tol,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    assert 1.8 < speed < 2.0  # approaching the asymptotic speed from below


def test_react_diffuse_matches_pure_diffusion_when_the_reaction_is_zero() -> None:
    # With a zero reaction term, react_diffuse_1d must agree with diffuse_1d.
    initial = gaussian_profile(_CENTERS, mass=5.0, variance=1.0)
    a = diffuse_1d(initial, diffusivity=1.0, dx=_DX, dt=0.2 * _DX * _DX, steps=50)
    from reprolith import react_diffuse_1d
    b = react_diffuse_1d(initial, diffusivity=1.0, dx=_DX, dt=0.2 * _DX * _DX, steps=50,
                         reaction=lambda u: 0.0)
    assert a == b


def test_morphogen_gradient_reproduces_the_analytical_decay_length() -> None:
    # A morphogen released at a boundary and degraded (diffusion + linear decay) forms the
    # exponential gradient C(x) = C0 exp(-x/lambda) with decay length lambda = sqrt(D/k) — the
    # central length scale in developmental biology, and a closed-form ground truth.
    from reprolith import (
        gradient_decay_length,
        judge_scalar,
        morphogen_gradient,
    )

    D, k, C0 = 1.0, 0.25, 100.0
    analytic_lambda = math.sqrt(D / k)  # = 2.0
    dx = 0.1
    dt = 0.2 * dx * dx / D
    profile = morphogen_gradient(
        source=C0, diffusivity=D, decay=k, dx=dx, points=300, dt=dt, steps=40000
    )
    # Fit the decay length over the mid-gradient (away from the source and the far boundary).
    measured = gradient_decay_length(profile, dx=dx, start=20, end=120)
    verdict = judge_scalar(
        claim_id="gradient-length", quantity="morphogen decay length",
        source_location="analytical lambda=sqrt(D/k)", reported=analytic_lambda, predicted=measured,
    )
    assert verdict.verdict is Verdict.REPRODUCED  # exact to well within the 5% default


def test_gradient_decay_length_rejects_a_non_decaying_window() -> None:
    from reprolith import gradient_decay_length

    with pytest.raises(ValueError, match="does not decay"):
        gradient_decay_length([1.0, 2.0, 3.0, 4.0], dx=1.0, start=0, end=4)
