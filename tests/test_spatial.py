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


def test_negative_diffusivity_is_rejected() -> None:
    # A negative diffusivity is the backward heat equation — unconditionally unstable. Each input
    # is checked on its own, because two wrong signs cancel: D<0 with dt<0 gives an innocent-looking
    # positive diffusion number while the caller asked for anti-diffusion running backwards.
    initial = gaussian_profile(_CENTERS, mass=1.0, variance=1.0)
    with pytest.raises(ValueError, match="diffusivity must not be negative"):
        diffuse_1d(initial, diffusivity=-1.0, dx=_DX, dt=0.1 * _DX * _DX, steps=10)
    with pytest.raises(ValueError, match="diffusivity must not be negative"):
        diffuse_1d(initial, diffusivity=-1.0, dx=_DX, dt=-0.1 * _DX * _DX, steps=10)
    with pytest.raises(ValueError, match="dx must be a positive"):
        diffuse_1d(initial, diffusivity=1.0, dx=-_DX, dt=0.1 * _DX * _DX, steps=10)


def test_a_discretization_that_cannot_advance_the_profile_is_refused() -> None:
    # The frozen-run false reproduction: a run that cannot advance returns its initial condition,
    # which then "reproduces" any reported profile near that condition. Every route into it — a zero
    # or subnormal time step, zero diffusivity, a grid spacing so large the diffusion number
    # underflows — must be refused, not reported. (The stochastic class refuses the same way.)
    initial = gaussian_profile(_CENTERS, mass=1.0, variance=1.0)
    for kwargs in (
        {"diffusivity": 1.0, "dx": _DX, "dt": 0.0},
        {"diffusivity": 0.0, "dx": _DX, "dt": 0.1 * _DX * _DX},
        {"diffusivity": 1.0, "dx": 1e200, "dt": 0.1},
        {"diffusivity": 1.0, "dx": _DX, "dt": 1e-320},
    ):
        with pytest.raises(ValueError, match="cannot advance"):
            diffuse_1d(initial, steps=10, **kwargs)  # type: ignore[arg-type]

    # A decay term is enough on its own to advance the profile, so diffusion-free decay is legal.
    decayed = diffuse_1d(initial, diffusivity=0.0, dx=_DX, dt=0.1, steps=10, decay=0.5)
    assert decayed[len(decayed) // 2] < initial[len(initial) // 2]


def test_a_spatial_claim_must_evolve_the_profile_to_be_evidence() -> None:
    # A zero-step run returns the initial profile, which is an input to the reconstruction rather
    # than evidence about it — certifying it would publish a simulation that never ran.
    from reprolith import EnginePin, PaperIdentity, SpatialClaim, certify_spatial

    profile = tuple(gaussian_profile(_CENTERS, mass=1.0, variance=1.0))
    claim = SpatialClaim(
        claim_id="s1", quantity="profile", initial=profile, reference=profile,
        source_location="Fig 1", diffusivity=1.0, dx=_DX, dt=0.1 * _DX * _DX, steps=0,
    )
    with pytest.raises(ValueError, match="at least one step"):
        certify_spatial(
            paper=PaperIdentity(title="P", doi="10.1/x"),
            engine_pin=EnginePin(engine="reprolith-fd", version="0.0.1"),
            claims=[claim],
        )


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


def test_bistable_nagumo_reproduces_the_exact_pushed_front_speed() -> None:
    # The bistable (Nagumo) equation u_t = D u_xx + u(1-u)(u-a), 0<a<1/2, has a *pushed* front
    # connecting the two stable states u=1 and u=0 with an EXACT closed-form speed c = sqrt(D/2)(1-2a).
    # Unlike the Fisher-KPP pulled front (which reaches its speed only logarithmically, needing a ~10%
    # override), a pushed front has a sharply selected speed the solver reproduces within the default
    # tolerance — a qualitatively different, and stronger, reproduction.
    from reprolith import front_position, judge_scalar, react_diffuse_1d

    D, a = 1.0, 0.25
    analytic_speed = math.sqrt(D / 2.0) * (1.0 - 2.0 * a)  # = 0.35355...
    dx = 0.25
    n = 481  # domain [0, 120]: the front settles and travels without reaching the boundary
    dt = 0.2 * dx * dx / D
    xs = [i * dx for i in range(n)]
    # A smooth step: u=1 (invaded) on the left, u=0 ahead, centered at x=25.
    u = [0.5 * (1.0 - math.tanh((x - 25.0) / 4.0)) for x in xs]

    def reaction(c: float) -> float:
        return c * (1.0 - c) * (c - a)

    def advance(state: list[float], elapsed: float) -> list[float]:
        return react_diffuse_1d(state, diffusivity=D, dx=dx, dt=dt, steps=round(elapsed / dt),
                                reaction=reaction)

    at_30 = advance(u, 30.0)  # let the transient settle onto the traveling profile
    at_60 = advance(at_30, 30.0)
    speed = (front_position(at_60, dx=dx) - front_position(at_30, dx=dx)) / 30.0

    verdict = judge_scalar(  # default tolerance: the pushed front's speed is exact, not asymptotic
        claim_id="nagumo-front", quantity="bistable (Nagumo) pushed-front speed",
        source_location="analytical c=sqrt(D/2)(1-2a)", reported=analytic_speed, predicted=speed,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    assert abs(speed - analytic_speed) / analytic_speed < 0.01  # reproduced to ~0.1%, no override


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


def test_two_species_reaction_diffusion_reproduces_the_dispersion_relation() -> None:
    # A linear activator-inhibitor system's spatial mode cos(k x) grows at the dominant eigenvalue
    # of J - k^2·diag(Du,Dv) — the dispersion relation underlying Turing pattern formation, and a
    # closed-form ground truth. The coupled solver must reproduce that growth rate.
    from reprolith import judge_scalar, react_diffuse_2species

    a, b, c, d = 2.0, -1.0, 1.0, -1.0  # reaction Jacobian at the (0,0) steady state
    Du, Dv = 0.5, 2.0
    n = 201
    dx = 0.1
    length = (n - 1) * dx
    dt = 0.002  # keeps Dv·dt/dx² = 0.4 within the stability limit
    k0 = math.pi / length
    k2 = k0 * k0

    m00, m01, m10, m11 = a - Du * k2, b, c, d - Dv * k2
    trace = m00 + m11
    determinant = m00 * m11 - m01 * m10
    eigenvalue = (trace + math.sqrt(trace * trace - 4 * determinant)) / 2  # dominant
    ex, ey = m01, eigenvalue - m00  # its eigenvector
    norm = math.hypot(ex, ey)
    ex, ey = ex / norm, ey / norm

    eps = 1e-4
    xs = [i * dx for i in range(n)]
    u = [eps * ex * math.cos(k0 * x) for x in xs]
    v = [eps * ey * math.cos(k0 * x) for x in xs]

    def fu(uu, vv):
        return a * uu + b * vv

    def fv(uu, vv):
        return c * uu + d * vv

    u1, v1 = react_diffuse_2species(u, v, du=Du, dv=Dv, dx=dx, dt=dt, steps=500,
                                    reaction_u=fu, reaction_v=fv)
    u2, v2 = react_diffuse_2species(u1, v1, du=Du, dv=Dv, dx=dx, dt=dt, steps=500,
                                    reaction_u=fu, reaction_v=fv)
    growth_rate = math.log(u2[0] / u1[0]) / (500 * dt)

    verdict = judge_scalar(
        claim_id="dispersion", quantity="linear growth rate of a spatial mode",
        source_location="dispersion relation of J - k^2 D", reported=eigenvalue, predicted=growth_rate,
    )
    assert verdict.verdict is Verdict.REPRODUCED  # matches to the O(dx^2) discretization error


def test_schnakenberg_reproduces_the_turing_wavelength_selection() -> None:
    # THE landmark morphogenesis result (Turing 1952): a reaction-diffusion system that is stable
    # to uniform perturbations becomes unstable to a *band* of spatial modes once diffusion is added,
    # and the pattern that emerges is dominated by the single fastest-growing mode. Here the
    # dispersion relation predicts the winning mode m* = argmax_m lambda(k_m); the nonlinear
    # Schnakenberg solver, seeded from a broadband perturbation, must select exactly that mode.
    # Non-circular: the emergent wavenumber comes from simulation, the prediction from linear
    # stability analysis. Stronger than the dispersion-relation test — it validates *which* pattern
    # forms, not just one mode's growth rate.
    from reprolith import react_diffuse_2species

    # Schnakenberg: u_t = Du u_xx + a - u + u^2 v ,  v_t = Dv v_xx + b - u^2 v.
    a, b = 0.1, 0.9
    Du, Dv = 1.0, 40.0
    u_star, v_star = a + b, b / (a + b) ** 2  # homogeneous steady state

    # Reaction Jacobian at (u*, v*).
    fu = -1.0 + 2.0 * u_star * v_star
    fv = u_star * u_star
    gu = -2.0 * u_star * v_star
    gv = -u_star * u_star

    # Turing preconditions: stable without diffusion (trace<0, det>0), so any instability is
    # diffusion-driven — the defining signature of a Turing pattern.
    assert fu + gv < 0.0
    assert fu * gv - fv * gu > 0.0

    length, n = 40.0, 201
    dx = length / (n - 1)
    xs = [i * dx for i in range(n)]

    def dispersion(k2: float) -> float:  # dominant real eigenvalue of J - k^2 diag(Du, Dv)
        m00, m11 = fu - Du * k2, gv - Dv * k2
        trace, det = m00 + m11, m00 * m11 - fv * gu
        disc = trace * trace - 4.0 * det
        return trace / 2.0 if disc < 0.0 else (trace + math.sqrt(disc)) / 2.0

    modes = range(1, 40)  # admissible zero-flux modes cos(m pi x / L)
    growth = {m: dispersion((m * math.pi / length) ** 2) for m in modes}
    m_star = max(modes, key=lambda m: growth[m])  # predicted fastest-growing mode
    assert growth[m_star] > 0.0  # a genuine Turing instability exists

    dt = 0.24 * dx * dx / Dv  # Dv dt/dx^2 = 0.24 within the explicit limit
    # Broadband deterministic seed: equal weight on every mode, so selection is the solver's doing.
    u = [u_star + 0.001 * sum(math.cos(m * math.pi * x / length) for m in modes) for x in xs]
    v = [v_star for _ in xs]

    def reaction_u(uu: float, vv: float) -> float:
        return a - uu + uu * uu * vv

    def reaction_v(uu: float, vv: float) -> float:
        return b - uu * uu * vv

    u, v = react_diffuse_2species(u, v, du=Du, dv=Dv, dx=dx, dt=dt, steps=16000,
                                  reaction_u=reaction_u, reaction_v=reaction_v)

    def mode_amplitude(field: list[float], m: int) -> float:  # |projection onto cos(m pi x / L)|
        total = 0.0
        for i, x in enumerate(xs):
            weight = 0.5 if i in (0, n - 1) else 1.0  # trapezoid
            total += weight * (field[i] - u_star) * math.cos(m * math.pi * x / length)
        return abs(total)

    dominant = max(modes, key=lambda m: mode_amplitude(u, m))
    assert max(u) - min(u) > 0.01  # the instability actually grew a pattern
    assert dominant == m_star  # wavelength selection reproduced: the fastest-growing mode won


def test_2d_diffusion_reproduces_the_analytical_gaussian_field() -> None:
    # 2-D diffusion of a Gaussian is a Gaussian whose (isotropic) variance grows by 2·D·t — the
    # exact tissue-scale-spread ground truth.
    from reprolith import diffuse_2d, gaussian_field_2d, judge_curve

    D, var0, mass = 1.0, 1.0, 10.0
    dx = 0.4
    m = 61
    axis = [-12.0 + i * dx for i in range(m)]
    dt = 0.2 * dx * dx / D  # 2-D number D·dt/dx² = 0.2 < 0.25
    steps = 200
    elapsed = steps * dt
    initial = gaussian_field_2d(axis, axis, mass=mass, variance=var0)
    simulated = diffuse_2d(initial, diffusivity=D, dx=dx, dt=dt, steps=steps)
    analytic = gaussian_field_2d(axis, axis, mass=mass, variance=var0 + 2 * D * elapsed)

    # Flatten both fields and judge with the shared curve oracle.
    flat_sim = [c for row in simulated for c in row]
    flat_ref = [c for row in analytic for c in row]
    verdict = judge_curve(
        claim_id="Cxy", quantity="2-D diffused concentration field",
        source_location="analytical 2-D Gaussian diffusion", reference=flat_ref, predicted=flat_sim,
    )
    assert verdict.verdict is Verdict.REPRODUCED


def test_2d_diffusion_conserves_mass_and_rejects_instability() -> None:
    from reprolith import diffuse_2d, gaussian_field_2d

    dx = 0.4
    axis = [-12.0 + i * dx for i in range(61)]
    field = gaussian_field_2d(axis, axis, mass=5.0, variance=1.0)
    final = diffuse_2d(field, diffusivity=1.0, dx=dx, dt=0.2 * dx * dx / 1.0, steps=100)
    total = sum(c for row in final for c in row) * dx * dx
    assert total == pytest.approx(5.0, abs=1e-4)  # zero-flux conserves 2-D mass
    with pytest.raises(ValueError, match="0.25"):
        diffuse_2d(field, diffusivity=1.0, dx=dx, dt=0.3 * dx * dx, steps=1)  # number 0.3 > 0.25


def test_spatial_sir_reproduces_the_epidemic_wave_speed() -> None:
    # A spatially spreading epidemic (S non-diffusing, I diffusing) forms a traveling infection
    # front. Ahead of the front the I equation linearizes to a Fisher-KPP form with growth rate
    # r = beta*S0 - gamma, so the wave speed is c = 2*sqrt(D*(beta*S0 - gamma)) — the canonical
    # spatial-epidemiology result for how fast an epidemic spreads geographically.
    from reprolith import (
        Tolerance,
        ToleranceSource,
        front_position,
        judge_scalar,
        react_diffuse_2species,
    )

    D, beta, gamma, s0 = 1.0, 1.0, 0.5, 1.0
    r = beta * s0 - gamma
    c_analytic = 2.0 * math.sqrt(D * r)
    dx = 0.5
    n = 1601
    dt = 0.2 * dx * dx / D
    xs = [i * dx for i in range(n)]
    sus = [s0] * n
    inf = [0.5 if x < 20.0 else 0.0 for x in xs]

    def susceptible_rate(s, i):
        return -beta * s * i

    def infected_rate(s, i):
        return beta * s * i - gamma * i

    def advance(state_s, state_i, to_steps):
        return react_diffuse_2species(state_s, state_i, du=0.0, dv=D, dx=dx, dt=dt,
                                      steps=to_steps, reaction_u=susceptible_rate,
                                      reaction_v=infected_rate)

    per = round(100.0 / dt)
    sus, inf = advance(sus, inf, per)          # t = 100
    front_100 = front_position(inf, dx=dx, level=0.1)
    sus, inf = advance(sus, inf, per)          # t = 200
    front_200 = front_position(inf, dx=dx, level=0.1)
    speed = (front_200 - front_100) / 100.0

    tol = Tolerance(
        0.10, 0.20, ToleranceSource.REVIEWER_OVERRIDE,
        rationale="KPP-type front speed converges logarithmically; finite-time + discretized "
                  "measurement expected within ~10%",
    )
    verdict = judge_scalar(
        claim_id="sir-wave", quantity="spatial SIR epidemic wave speed",
        source_location="analytical c=2*sqrt(D(beta*S0-gamma))", reported=c_analytic,
        predicted=speed, tolerance=tol,
    )
    assert verdict.verdict is Verdict.REPRODUCED


def test_diffusion_and_decay_share_one_stability_budget() -> None:
    """Checked separately, the budget is spent twice and the profile diverges while staying finite.

    The explicit update's amplification at the shortest wavelength is 1 − 4α − decay·dt, so a grid
    at α = 0.4 (inside the 0.5 diffusion limit) with decay·dt = 0.6 (inside the 1.0 decay limit)
    amplifies by −1.2 per step. Nothing downstream can catch it: the values oscillate to huge
    magnitudes but remain finite, so the oracle's non-finite abstention never fires and the class
    publishes an honest-looking `not-reproduced` against a discretization it should have refused.
    """
    profile = [0.0] * 10 + [1.0] + [0.0] * 10
    with pytest.raises(ValueError, match="amplification"):
        diffuse_1d(profile, diffusivity=0.4, dx=1.0, dt=1.0, steps=30, decay=0.6)
    # A grid inside the joint bound still runs, and stays bounded by its initial magnitude.
    stable = diffuse_1d(profile, diffusivity=0.25, dx=1.0, dt=1.0, steps=30, decay=1.0)
    assert max(abs(v) for v in stable) <= 1.0


def test_a_reaction_term_is_budgeted_against_the_stability_band_not_assumed_away() -> None:
    """A limit on the diffusion number alone cannot make a reaction-bearing step stable.

    `dt = α·dx²/D`, so the reaction's share of the amplification grows with `dx²` at fixed α.
    Measured on Fisher-KPP (D=1, r=1.2) at α = 0.40 exactly — which any bare α limit accepts —
    dx = 1.1 gives a front speed of −0.0000 against an analytic 2.19, with every value finite and
    in range, so nothing downstream can see it and the judge blames the paper.
    """
    from reprolith.spatial import UnstableDiscretization, front_position, react_diffuse_1d

    D, r, alpha = 1.0, 1.2, 0.40
    analytic = 2 * math.sqrt(D * r)

    def run(dx: float) -> float:
        dt, n = alpha * dx * dx / D, int(400 / dx)
        profile = [1.0 if i * dx < 20 else 0.0 for i in range(n)]
        first = react_diffuse_1d(profile, diffusivity=D, dx=dx, dt=dt, steps=int(50 / dt),
                                 reaction=lambda u: r * u * (1 - u))
        second = react_diffuse_1d(first, diffusivity=D, dx=dx, dt=dt, steps=int(50 / dt),
                                  reaction=lambda u: r * u * (1 - u))
        return (front_position(second, dx=dx) - front_position(first, dx=dx)) / 50

    # A grid the combined rule admits reproduces the analytic front speed.
    assert abs(run(0.5) - analytic) / analytic < 0.15
    # The same α on a coarser grid is refused, rather than returning finite garbage.
    with pytest.raises(UnstableDiscretization, match="diffusion and reaction together"):
        run(1.1)


def test_a_spatial_claim_the_judge_abstains_on_does_not_mint_an_assumption() -> None:
    """An assumption on an abstention describes a judgment nobody made — and downgrades for it.

    The boundary qualification was read off the *claim*, but `judge_curve` abstains internally on a
    non-finite reference without raising, so a `not-evaluable` claim still minted a load-bearing
    assumption and pushed the whole certificate to `partially-reproduced`.
    """
    from reprolith import OverallVerdict, PaperIdentity, Verdict
    from reprolith.spatial import SpatialClaim, certify_spatial, solver_pin

    def claim(claim_id: str, reference: tuple[float, ...]) -> SpatialClaim:
        return SpatialClaim(claim_id=claim_id, quantity="profile", initial=(1.0, 0.0, 0.0, 0.0),
                            reference=reference, source_location="s", diffusivity=1.0,
                            dx=1.0, dt=0.2, steps=2)

    good = claim("good", (0.6, 0.28, 0.09, 0.03))
    unjudgeable = claim("nanref", (float("nan"), 0.0, 0.0, 0.0))
    cert = certify_spatial(paper=PaperIdentity(title="t", doi=""), engine_pin=solver_pin(),
                           claims=[good, unjudgeable])
    verdicts = {a.claim_id: a.verdict for a in cert.assessments}
    assert verdicts["nanref"] is Verdict.NOT_EVALUABLE
    assert [a.id for a in cert.assumptions] == ["spatial-boundary-good"]
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED  # from the judged claim alone


def test_a_caller_error_still_raises_where_an_unstable_grid_abstains() -> None:
    """`except ValueError` was broad enough to publish a sign error as an honest abstention."""
    from reprolith import OverallVerdict, PaperIdentity, Verdict
    from reprolith.spatial import SpatialClaim, certify_spatial, solver_pin

    def certify(**kw):
        return certify_spatial(
            paper=PaperIdentity(title="t", doi=""), engine_pin=solver_pin(),
            claims=[SpatialClaim(claim_id="c", quantity="profile", initial=(1.0, 0.0, 0.0, 0.0),
                                 reference=(1.0, 0.0, 0.0, 0.0), source_location="s",
                                 dx=1.0, dt=0.2, steps=2, **kw)],
        )

    # An unstable discretization is a published abstention — and the abstention is what is
    # asserted, not merely that nothing raised. Asserting only "no exception" let the whole
    # abstention branch be deleted with the suite staying green: the certificate then read the
    # initial profile back as the answer and published `reproduced` for a grid at alpha = 20
    # against an explicit scheme's limit of 0.5, which is the "a simulation that never happened
    # reads as a perfect reproduction" failure this module names as its own.
    unstable = certify(diffusivity=100.0)
    assert unstable.overall is OverallVerdict.BLOCKED
    assert unstable.assessments[0].verdict is Verdict.NOT_EVALUABLE
    assert "unstable" in (unstable.assessments[0].root_cause or "") or "unstable" in (
        unstable.assessments[0].discrepancy or ""
    )
    # …a negative diffusivity is a bug in the caller, and still raises.
    with pytest.raises(ValueError, match="must not be negative"):
        certify(diffusivity=-1.0)


def test_both_solvers_apply_the_same_reaction_stability_rule() -> None:
    """The re-check landed in the one-species solver and not its two-species neighbour.

    Same model, same grid: one refused the step and the other ran it and returned 5.65 against a
    true steady state of 10.0. The union with the range already checked has to be carried too — a
    profile that stays uniform at every step is degenerate on every individual check, so without it
    the guard never probes anything at all while the values walk somewhere far stiffer.
    """
    from reprolith.spatial import UnstableDiscretization, react_diffuse_1d, react_diffuse_2species

    def reaction(u: float) -> float:
        return 1000.0 - u**3          # slope 3 at u=1, 300 at u=10

    def one_species(dt: float) -> list[float]:
        return react_diffuse_1d([1.0] * 8, diffusivity=0.1, dx=1.0, dt=dt, steps=4000,
                                reaction=reaction)

    def two_species(dt: float) -> list[float]:
        return react_diffuse_2species([1.0] * 8, [0.0] * 8, du=0.1, dv=0.1, dx=1.0, dt=dt,
                                      steps=4000, reaction_u=lambda u, v: reaction(u),
                                      reaction_v=lambda u, v: 0.0)[0]

    # dt·|f′| = 1.8 at the steady state: inside the band, so both run and both find u = 10.
    assert one_species(0.006)[0] == pytest.approx(10.0, abs=1e-4)
    assert two_species(0.006)[0] == pytest.approx(10.0, abs=1e-4)
    # dt·|f′| = 2.4: outside it, so both refuse rather than returning something finite and wrong.
    with pytest.raises(UnstableDiscretization):
        one_species(0.008)
    with pytest.raises(UnstableDiscretization):
        two_species(0.008)


def test_a_uniform_profile_is_not_probed_outside_itself() -> None:
    """A reaction defined only up to its carrying capacity must not be evaluated past it.

    The rule is that every probe is a value the profile holds; a uniform profile has exactly one,
    so it is not probed at all — which is sound, because the instability being guarded against is
    neighbouring grid points decoupling, and a profile with no spatial variation has no such mode.
    Probing `lo + ε` instead crashed with a bare `math domain error`.
    """
    from reprolith.spatial import react_diffuse_1d

    at_capacity = react_diffuse_1d([1.0] * 6, diffusivity=1.0, dx=1.0, dt=0.05, steps=3,
                                   reaction=lambda u: 0.5 * math.sqrt(1.0 - u))
    assert at_capacity == [1.0] * 6
    # …and a constant profile at any magnitude runs, rather than being refused by a fixed floor.
    for magnitude in (1e-300, 1e-12, 0.0):
        assert react_diffuse_1d([magnitude] * 6, diffusivity=1.0, dx=1.0, dt=0.05, steps=2,
                                reaction=lambda u: 0.0) == [magnitude] * 6


def test_an_unstable_decay_step_abstains_instead_of_taking_down_the_certificate() -> None:
    """The decay check raised a bare `ValueError` while both its siblings raise UnstableDiscretization.

    `certify_spatial` catches only `UnstableDiscretization`, in order to abstain on the one claim
    that cannot be judged. Raised as a `ValueError`, an ordinary discretization — a 5/min
    degradation rate at dt = 0.5 min — escaped that handler and took down the whole certificate,
    discarding every sibling claim's honest verdict. The threshold itself is right; the type was not.
    """
    from reprolith.spatial import UnstableDiscretization, diffuse_1d

    with pytest.raises(UnstableDiscretization, match="unstable decay step"):
        diffuse_1d((1.0, 1.0, 1.0), diffusivity=0.0, dx=1.0, dt=0.5, steps=1, decay=3.0)
    # A genuine caller bug stays a caller bug.
    with pytest.raises(ValueError, match="must not be negative"):
        diffuse_1d((1.0, 1.0, 1.0), diffusivity=0.0, dx=1.0, dt=0.5, steps=1, decay=-1.0)


def test_the_boundary_assumption_does_not_assert_what_the_paper_said() -> None:
    """This front-end takes claims, not a dossier, so it never learns what boundary was stated.

    Its own docstring says it "cannot see" the dossier's boundary gap — and the published
    assumption asserted "not one the paper stated" regardless, a fact about the author's paper that
    nothing checked, and vacuously wrong for the three committed entries, which have no paper.
    """
    from reprolith import PaperIdentity
    from reprolith.spatial import SpatialClaim, certify_spatial, solver_pin

    cert = certify_spatial(
        paper=PaperIdentity(title="1-D diffusion", doi=""), engine_pin=solver_pin(),
        claims=[SpatialClaim(claim_id="c", quantity="profile", initial=(0.0, 1.0, 0.0),
                             reference=(0.1, 0.8, 0.1), source_location="Fig 1",
                             diffusivity=0.1, dx=1.0, dt=0.1, steps=1)],
    )
    description = cert.assumptions[0].description
    assert "the paper stated" not in description, description
    assert "did not check" in description
    # And the author is told it is not theirs to fix.
    assert cert.assumptions[0].author_can_close is False


def test_a_claim_with_no_reported_profile_abstains_like_its_sibling_front_end() -> None:
    """Two front-ends over one oracle used to answer the same input differently.

    `certify_curves` abstains on a claim with no reference; this one raised out of the whole
    certificate, discarding every sibling claim's verdict along with it.
    """
    from reprolith import OverallVerdict, PaperIdentity, Verdict
    from reprolith.spatial import SpatialClaim, certify_spatial, solver_pin

    certificate = certify_spatial(
        paper=PaperIdentity(title="t", doi=""), engine_pin=solver_pin(),
        claims=[
            SpatialClaim(claim_id="figure-only", quantity="profile", initial=(1.0, 0.0, 0.0, 0.0),
                         reference=(), source_location="Fig 3", diffusivity=0.1,
                         dx=1.0, dt=0.2, steps=2),
            SpatialClaim(claim_id="checked", quantity="profile", initial=(1.0, 0.0, 0.0, 0.0),
                         reference=(0.98, 0.02, 0.0, 0.0), source_location="Fig 4",
                         diffusivity=0.1, dx=1.0, dt=0.2, steps=2),
        ],
    )

    abstained, judged = certificate.assessments
    assert abstained.verdict is Verdict.NOT_EVALUABLE
    assert "nothing to compare" in (abstained.root_cause or "")
    # The sibling claim is still judged: the abstention costs one claim, not the certificate.
    assert judged.verdict is not Verdict.NOT_EVALUABLE
    assert certificate.overall is not OverallVerdict.BLOCKED


def test_a_zero_step_claim_still_raises_even_with_no_reference() -> None:
    """Two malformed things at once: the caller's bug wins, it is not published as an abstention."""
    import pytest as _pytest
    from reprolith import PaperIdentity
    from reprolith.spatial import SpatialClaim, certify_spatial, solver_pin

    with _pytest.raises(ValueError, match="at least one step"):
        certify_spatial(
            paper=PaperIdentity(title="t", doi=""), engine_pin=solver_pin(),
            claims=[SpatialClaim(claim_id="c", quantity="profile", initial=(1.0, 0.0, 0.0, 0.0),
                                 reference=(), source_location="Fig 3", diffusivity=0.1,
                                 dx=1.0, dt=0.2, steps=0)],
        )
