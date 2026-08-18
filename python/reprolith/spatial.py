"""The spatial reaction-diffusion model class simulator (spec: ``spatial-class``).

Reprolith's sixth model class: PDE models over space and time — morphogen gradients, growth fronts,
tissue-scale distribution. The reproducible result is a concentration profile over space, so this
class reuses the curve oracle (:func:`reprolith.judge_curve`) unchanged and specializes only the
simulator: an explicit finite-difference solver for 1-D diffusion with optional first-order reaction
(decay/production) terms.

Like the logical and stochastic classes, the solver is exact-scheme and dependency-free — pure
Python — so this class carries no deferred engine. It is deterministic under its pinned
discretization, and rejects a time step that violates the explicit scheme's stability limit rather
than producing a diverging profile (spec: "Discretization is part of the protocol").
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Gap, GapKind, Parameter
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    ReferenceKind,
    Tolerance,
    judge_curve,
    not_evaluable,
    undetermined_shortfall,
)
from .pins import algorithm_revision


def _diffusion_number(
    *,
    diffusivity: float,
    dx: float,
    dt: float,
    steps: int,
    limit: float,
    decay: float = 0.0,
    must_advance: bool = True,
) -> float:
    """Validate a discretization and return its diffusion number ``D·dt/dx²``.

    Each input is checked on its own before the combined number is formed, because two wrong
    signs cancel: a negative diffusivity with a negative time step yields a positive,
    innocent-looking diffusion number while the caller asked for anti-diffusion running
    backwards in time.

    The last check is the important one. A discretization whose per-step update is too small to
    change a value at unit scale — because ``dt``, ``D``, or ``1/dx²`` is zero or subnormal — runs
    to completion and returns the initial profile unchanged. Judged against a reported profile
    near that initial condition, a simulation that never happened reads as a perfect
    reproduction. So a run that cannot advance is refused rather than reported (the spatial
    counterpart of the stochastic class refusing a rate or duration the SSA cannot advance
    through). ``must_advance`` is off for solvers whose update carries a reaction or source term
    that moves the profile on its own.
    """
    if steps < 0:
        raise ValueError(f"steps must not be negative, got {steps}")
    for name, value in (("diffusivity", diffusivity), ("dx", dx), ("dt", dt), ("decay", decay)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number, got {value!r}")
    if diffusivity < 0.0:
        raise ValueError(f"diffusivity must not be negative, got {diffusivity}")
    if dx <= 0.0:
        raise ValueError(f"dx must be a positive grid spacing, got {dx}")
    if dt < 0.0:
        raise ValueError(f"dt must not be negative, got {dt}")
    if decay < 0.0:
        raise ValueError(f"decay must not be negative (a negative decay is unbounded growth), got {decay}")
    if decay * dt > 1.0:
        raise ValueError(
            f"unstable decay step: decay·dt = {decay * dt:.3g} must not exceed 1; "
            "above it the first-order term overshoots zero and oscillates"
        )
    alpha = diffusivity * dt / (dx * dx)
    if alpha > limit + 1e-12:
        raise UnstableDiscretization(
            f"unstable discretization: D·dt/dx² = {alpha:.3g} must lie in [0, {limit}]; "
            "reduce dt or increase dx"
        )
    # Diffusion and decay share one stability budget, and checking them separately spends it
    # twice. The explicit update's amplification at the highest grid mode is 1 − (α/limit)·2 −
    # decay·dt, so a grid with α = 0.4 (inside 0.5) and decay·dt = 0.6 (inside 1) has an
    # amplification of −1.2 and oscillates to divergence — while staying *finite*, so nothing
    # downstream sees a non-finite value and the profile is judged as an honest miss.
    combined = 2.0 * alpha / limit + decay * dt
    if combined > 2.0 + 1e-12:
        raise UnstableDiscretization(
            f"unstable discretization: diffusion and decay together give an amplification factor "
            f"of {1.0 - combined:.3g} at the shortest wavelength, outside [-1, 1] "
            f"(D·dt/dx² = {alpha:.3g}, decay·dt = {decay * dt:.3g}); reduce dt"
        )
    if must_advance and steps > 0 and 1.0 + alpha == 1.0 and 1.0 + decay * dt == 1.0:
        raise ValueError(
            f"this discretization cannot advance the profile: D·dt/dx² = {alpha:.3g} and "
            f"decay·dt = {decay * dt:.3g} are both too small to change a value, so the run "
            "would return its initial condition unchanged (check the units of D, dx and dt)"
        )
    return alpha


class UnstableDiscretization(ValueError):
    """A discretization the explicit scheme cannot run stably.

    A distinct type so a front-end can tell "this protocol cannot decide this claim" — an honest
    abstention — from a caller's malformed input (a negative diffusivity, a one-point profile),
    which is a bug and must still raise. Catching bare ``ValueError`` published the second as the
    first, so a sign error certified as "not evaluable" instead of surfacing.
    """


def _reaction_stability(
    values: Sequence[float],
    reaction: Callable[[float], float],
    *,
    alpha: float,
    dt: float,
    samples: int = 33,
    checked: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Refuse a step whose diffusion *and reaction* together leave the stable amplification band.

    The explicit update's amplification at the shortest wavelength is ``1 − 4α − dt·f′``, so the
    reaction has to be budgeted against the same [−1, 1] band the diffusion number is checked in —
    the way :func:`_diffusion_number` already budgets a linear decay. ``f′`` is not known
    symbolically here, so it is estimated by differencing ``f`` across the values the profile
    actually holds.

    Sampled *inside* the profile's own closed range, never outside it. Widening the probe to
    anticipate growth meant evaluating the caller's reaction at values the run never visits, and
    three things followed: a reaction with an ordinary non-negativity check raised, and the probe
    swallowed the exception and skipped the whole guard; ``u**0.5`` went complex and crashed the
    solver; and a uniform profile at large magnitude produced a widening below one ulp, so the
    sample step was zero. Growth is handled by re-checking as the profile grows (see
    :func:`_react_step`), which is what the run actually does, rather than by guessing how far.

    An estimate is enough because the failure is not marginal: outside the band the even and odd
    grid points decouple and the profile becomes a comb, which is finite, in range, and wrong by
    any amount — a Fisher-KPP front speed of −0.0000 against an analytic 2.19.
    """
    finite = [v for v in values if math.isfinite(v)]
    if not finite or dt == 0.0:
        return checked if checked is not None else (0.0, 0.0)
    lo, hi = min(finite), max(finite)
    if checked is not None:  # a re-check covers the union, so a shrinking profile stays covered
        lo, hi = min(lo, checked[0]), max(hi, checked[1])
    if hi == lo:
        # A uniform profile still has a slope through it; difference over a step scaled to the
        # value's own magnitude, since a fixed epsilon vanishes at 1e9 and swamps the value at 1e-9.
        step = max(abs(lo), 1.0) * 1e-6
        probes = [lo, lo + step]
    else:
        step = (hi - lo) / (samples - 1)
        probes = [lo + i * step for i in range(samples)]
    slope = 0.0
    for left, right in zip(probes, probes[1:]):
        # No exception handling here on purpose: every probe is a value the profile holds, so a
        # reaction that cannot be evaluated at one of them cannot be run either, and the error
        # belongs to the caller rather than being turned into a silently skipped check.
        rise = reaction(right) - reaction(left)
        if math.isfinite(rise):
            slope = max(slope, abs(rise) / (right - left))
    combined = 4.0 * alpha + dt * slope
    if combined > 2.0 + 1e-12:
        raise UnstableDiscretization(
            f"unstable discretization: diffusion and reaction together give an amplification of "
            f"{1.0 - combined:.3g} at the shortest wavelength, outside [-1, 1] "
            f"(D·dt/dx² = {alpha:.3g}, dt·|f'| = {dt * slope:.3g}); reduce dt or dx"
        )
    return lo, hi


def diffuse_1d(
    profile: Sequence[float],
    *,
    diffusivity: float,
    dx: float,
    dt: float,
    steps: int,
    decay: float = 0.0,
) -> list[float]:
    """Evolve a 1-D concentration profile under diffusion (and optional first-order decay).

    Solves ``∂C/∂t = D ∂²C/∂x² − k·C`` with the explicit forward-time centered-space scheme under
    zero-flux (Neumann) boundaries, which conserves mass when ``decay`` is zero. ``profile`` is the
    initial concentration at uniformly spaced points ``dx`` apart; the result is the profile after
    ``steps`` steps of size ``dt``. Deterministic in its inputs.

    Raises if the diffusion number ``D·dt/dx²`` exceeds ``0.5`` — the explicit scheme's stability
    limit — so an unstable discretization is refused, not run to a diverging profile, and equally
    refuses a discretization too small to advance the profile at all (see
    :func:`_diffusion_number`), which would otherwise return the initial condition as a result.
    """
    alpha = _diffusion_number(
        diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, limit=0.5, decay=decay,
    )
    current = list(profile)
    n = len(current)
    if n < 2:
        raise ValueError("need at least two grid points")
    for _ in range(steps):
        nxt = current[:]
        for i in range(n):
            left = current[i - 1] if i > 0 else current[i]  # zero-flux: mirror the boundary
            right = current[i + 1] if i < n - 1 else current[i]
            laplacian = left - 2.0 * current[i] + right
            nxt[i] = current[i] + alpha * laplacian - decay * dt * current[i]
        current = nxt
    return current


def react_diffuse_1d(
    profile: Sequence[float],
    *,
    diffusivity: float,
    dx: float,
    dt: float,
    steps: int,
    reaction: Callable[[float], float],
) -> list[float]:
    """Evolve a 1-D profile under diffusion plus a general local reaction term.

    Solves ``∂u/∂t = D ∂²u/∂x² + f(u)`` with the same explicit forward-time centered-space scheme as
    :func:`diffuse_1d`, where ``reaction`` is the local rate ``f(u)`` — e.g. logistic growth
    ``r·u·(1−u)`` for the Fisher-KPP invasion/growth-front model. Zero-flux boundaries, deterministic,
    and subject to a *tighter* diffusion stability limit than pure diffusion: 0.4, not 0.5. At α
    near 0.5 the explicit update's amplification at the shortest wavelength approaches −1, so it
    stops smoothing and the even and odd grid points decouple. Pure diffusion still converges
    there; a reaction term feeds the resulting comb, and the profile becomes garbage that stays
    entirely *finite* — so no non-finite abstention downstream can see it, and the judge publishes
    a confident `failed` blamed on the paper for a time step the engine accepted.

    So the reaction is budgeted rather than assumed away: the amplification at the shortest
    wavelength is ``1 − 4α − dt·|f′|``, and this refuses a discretization whose reaction pushes it
    outside [−1, 1] (see :func:`_reaction_stability`). A limit on α alone cannot do this, because
    ``dt = α·dx²/D`` makes the reaction's share grow with ``dx²`` at fixed α — measured on
    Fisher-KPP (D=1, r=1.2) at α = 0.40 exactly, which a bare α limit accepts: dx = 0.5 gives a
    front speed of 1.95 against an analytic 2.19, and dx = 1.1 gives −0.0000, every value finite
    and in range. The combined rule refuses the second and admits the first, and it reproduces the
    measured cliff (α ≈ 0.465 at dx = 0.5) rather than guessing at a constant.

    The reaction moves the profile on its own, so a zero diffusion number is a legitimate
    reaction-only run here.
    """
    alpha = _diffusion_number(
        diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, limit=0.5, must_advance=False,
    )
    current = list(profile)
    n = len(current)
    if n < 2:
        raise ValueError("need at least two grid points")
    # Re-checked whenever the profile leaves the range already checked, because a profile that
    # grows into a stiffer region of the reaction was admitted on the strength of where it started:
    # a run entering a region with dt·|f′| = 3.6 produced a spurious comb oscillating between 10.26
    # and 10.70 where the true steady state is flat at 10.25 — a pattern manufactured by the step.
    checked_lo, checked_hi = _reaction_stability(current, reaction, alpha=alpha, dt=dt)
    for _ in range(steps):
        nxt = current[:]
        for i in range(n):
            left = current[i - 1] if i > 0 else current[i]
            right = current[i + 1] if i < n - 1 else current[i]
            nxt[i] = current[i] + alpha * (left - 2.0 * current[i] + right) + dt * reaction(current[i])
        current = nxt
        finite = [v for v in current if math.isfinite(v)]
        if finite and (min(finite) < checked_lo or max(finite) > checked_hi):
            checked_lo, checked_hi = _reaction_stability(
                current, reaction, alpha=alpha, dt=dt, checked=(checked_lo, checked_hi)
            )
    return current


def morphogen_gradient(
    *,
    source: float,
    diffusivity: float,
    decay: float,
    dx: float,
    points: int,
    dt: float,
    steps: int,
) -> list[float]:
    """The steady-state morphogen gradient from a fixed source: diffusion with linear decay.

    Solves ``∂C/∂t = D ∂²C/∂x² − k·C`` to steady state with a Dirichlet source (``C = source`` pinned
    at x=0) and a zero-flux far boundary, over ``points`` grid points. This is the developmental-
    biology gradient: a morphogen released at a boundary and degraded as it spreads, forming the
    exponential profile ``C(x) = source·e^{−x/λ}`` with decay length ``λ = √(D/k)``. ``steps`` must be
    large enough to reach steady state; the result is deterministic in the discretization.
    """
    alpha = _diffusion_number(
        diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, limit=0.5, decay=decay,
    )
    if points < 2:
        raise ValueError("need at least two grid points")
    current = [0.0] * points
    current[0] = source
    for _ in range(steps):
        nxt = current[:]
        for i in range(1, points):
            left = current[i - 1]
            right = current[i + 1] if i < points - 1 else current[i]
            nxt[i] = current[i] + alpha * (left - 2.0 * current[i] + right) - dt * decay * current[i]
        nxt[0] = source  # Dirichlet source
        current = nxt
    return current


def gradient_decay_length(profile: Sequence[float], *, dx: float, start: int, end: int) -> float:
    """The decay length λ of an exponential gradient, from the slope of ``ln C`` over ``[start, end)``.

    Fits ``ln C(x) = ln C₀ − x/λ`` by least squares over the grid-index window ``[start, end)`` and
    returns ``λ``. The window must lie in the positive, exponential part of the profile.
    """
    xs = [i * dx for i in range(start, end)]
    values = [profile[i] for i in range(start, end)]
    if any(v <= 0.0 for v in values):
        raise ValueError("the fit window must be in the positive part of the gradient")
    ys = [math.log(v) for v in values]
    n = len(xs)
    if n < 2:
        raise ValueError("need at least two points to fit a decay length")
    sx, sy = math.fsum(xs), math.fsum(ys)
    sxx = math.fsum(x * x for x in xs)
    sxy = math.fsum(x * y for x, y in zip(xs, ys))
    denominator = n * sxx - sx * sx
    if denominator == 0.0:
        raise ValueError("degenerate fit window")
    slope = (n * sxy - sx * sy) / denominator
    if slope >= 0.0:
        raise ValueError("the profile does not decay over the fit window")
    return -1.0 / slope


def react_diffuse_2species(
    u: Sequence[float],
    v: Sequence[float],
    *,
    du: float,
    dv: float,
    dx: float,
    dt: float,
    steps: int,
    reaction_u: Callable[[float, float], float],
    reaction_v: Callable[[float, float], float],
) -> tuple[list[float], list[float]]:
    """Evolve two coupled fields under reaction-diffusion — the basis of pattern formation.

    Solves the activator-inhibitor system ``u_t = Du u_xx + f(u,v)``, ``v_t = Dv v_xx + g(u,v)`` with
    the shared explicit scheme and zero-flux boundaries. This is the machinery behind Turing patterns
    (morphogenesis, pigmentation) and other multi-species spatial models. ``reaction_u``/``reaction_v``
    are the local rates ``f`` and ``g``. Deterministic; both species must satisfy the same combined
    diffusion-plus-reaction stability rule :func:`react_diffuse_1d` explains — a reaction term feeds
    the node-to-node oscillation an α near 0.5 stops damping, and the result is finite, plausible,
    and wrong.
    """
    au = _diffusion_number(diffusivity=du, dx=dx, dt=dt, steps=steps, limit=0.5, must_advance=False)
    av = _diffusion_number(diffusivity=dv, dx=dx, dt=dt, steps=steps, limit=0.5, must_advance=False)
    cu, cv = list(u), list(v)
    n = len(cu)
    if n < 2 or len(cv) != n:
        raise ValueError("u and v must have the same length, at least two grid points")
    # Probed at the partner species' own extremes, not at 0.0: a value the run never visits can
    # report a slope of zero where the true one is large — `g(0, v)` is identically zero for a
    # Brusselator, and any mass-action `-k·u·v` vanishes there. Measured, holding the partner at
    # 0.0 admitted dt·|∂f/∂u| = 3.0 and the run returned 1.1e15 against a converged 2.3e-66.
    def _held(f: Callable[[float, float], float], partner: float, *, first: bool) -> Callable[[float], float]:
        return (lambda x: f(x, partner)) if first else (lambda x: f(partner, x))

    for partner_v in (min(cv), max(cv)):
        _reaction_stability(cu, _held(reaction_u, partner_v, first=True), alpha=au, dt=dt)
    for partner_u in (min(cu), max(cu)):
        _reaction_stability(cv, _held(reaction_v, partner_u, first=False), alpha=av, dt=dt)
    for _ in range(steps):
        nu, nv = cu[:], cv[:]
        for i in range(n):
            ul = cu[i - 1] if i > 0 else cu[i]
            ur = cu[i + 1] if i < n - 1 else cu[i]
            vl = cv[i - 1] if i > 0 else cv[i]
            vr = cv[i + 1] if i < n - 1 else cv[i]
            nu[i] = cu[i] + au * (ul - 2.0 * cu[i] + ur) + dt * reaction_u(cu[i], cv[i])
            nv[i] = cv[i] + av * (vl - 2.0 * cv[i] + vr) + dt * reaction_v(cu[i], cv[i])
        cu, cv = nu, nv
    return cu, cv


def front_position(profile: Sequence[float], *, dx: float, level: float = 0.5) -> float | None:
    """The spatial position where ``profile`` first descends through ``level`` (linearly interpolated).

    The front location of a traveling wave — used to measure a front's speed between two times.
    Returns ``None`` when the profile never crosses the level.

    A non-finite value is refused rather than scanned past. Every comparison against NaN is false,
    so a diverged profile with NaN nodes silently reported the first crossing among its surviving
    ones — reducing a run that blew up to a plausible finite scalar, before any non-finite
    abstention downstream could see it.
    """
    if any(not math.isfinite(value) for value in profile):
        raise ValueError(
            "the profile carries a non-finite value: a diverged run has no front position, and "
            "scanning past it would report one from the nodes that happened to survive"
        )
    for i in range(len(profile) - 1):
        if profile[i] >= level >= profile[i + 1]:
            span = profile[i] - profile[i + 1]
            frac = (profile[i] - level) / span if span != 0.0 else 0.0
            return (i + frac) * dx
    return None


def diffuse_2d(
    grid: Sequence[Sequence[float]],
    *,
    diffusivity: float,
    dx: float,
    dt: float,
    steps: int,
) -> list[list[float]]:
    """Evolve a 2-D concentration field under isotropic diffusion (tissue-scale spread).

    Solves ``∂C/∂t = D (C_xx + C_yy)`` with the explicit five-point stencil under zero-flux
    boundaries on a uniform ``dx``-spaced grid (rows × columns). Deterministic. Raises if the 2-D
    diffusion number ``D·dt/dx²`` exceeds ``0.25`` — the explicit scheme's stability limit in two
    dimensions (stricter than 1-D's 0.5).
    """
    alpha = _diffusion_number(diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, limit=0.25)
    ny = len(grid)
    nx = len(grid[0]) if ny else 0
    if any(len(row) != nx for row in grid):
        raise ValueError("the grid must be rectangular: every row needs the same number of columns")
    if ny < 2 or nx < 2:
        raise ValueError("need at least a 2x2 grid")
    current = [list(row) for row in grid]
    for _ in range(steps):
        nxt = [row[:] for row in current]
        for i in range(ny):
            for j in range(nx):
                up = current[i - 1][j] if i > 0 else current[i][j]
                down = current[i + 1][j] if i < ny - 1 else current[i][j]
                left = current[i][j - 1] if j > 0 else current[i][j]
                right = current[i][j + 1] if j < nx - 1 else current[i][j]
                laplacian = up + down + left + right - 4.0 * current[i][j]
                nxt[i][j] = current[i][j] + alpha * laplacian
        current = nxt
    return current


def gaussian_field_2d(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    mass: float,
    variance: float,
    center: tuple[float, float] = (0.0, 0.0),
) -> list[list[float]]:
    """A 2-D Gaussian concentration field sampled on the ``ys`` × ``xs`` grid.

    The analytical shape a 2-D point source diffuses into: ``mass`` is the integral ∫∫C dx dy and
    ``variance`` the (isotropic) spread. Used to seed a 2-D simulation and, at a later variance, as
    the exact diffusion solution to check against.
    """
    if variance <= 0.0:
        raise ValueError("variance must be positive")
    cx, cy = center
    norm = mass / (2.0 * math.pi * variance)
    return [
        [norm * math.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * variance))) for x in xs]
        for y in ys
    ]


def gaussian_profile(centers: Sequence[float], *, mass: float, variance: float, center: float = 0.0) -> list[float]:
    """A Gaussian concentration profile sampled at ``centers`` with the given total ``mass``.

    The analytical shape a point source diffuses into: ``mass`` is the integral ∫C dx, ``variance``
    the spread. Used both to seed a simulation and, at a later variance, as the exact diffusion
    solution to check against (spec: "Analytical agreement").
    """
    if variance <= 0.0:
        raise ValueError("variance must be positive")
    norm = mass / math.sqrt(2.0 * math.pi * variance)
    return [norm * math.exp(-((x - center) ** 2) / (2.0 * variance)) for x in centers]


@dataclass(frozen=True)
class SpatialClaim:
    """A published spatial-profile claim: a reported concentration profile over space to reproduce.

    ``initial`` is the starting profile at grid spacing ``dx``; the model is evolved ``steps`` steps
    of ``dt`` under ``diffusivity`` (and optional first-order ``decay``), and the resulting profile
    is compared to ``reference`` — the paper's reported profile at that time — with the curve oracle.
    ``shortfall`` supplies the root cause a non-pass verdict requires.
    """

    claim_id: str
    quantity: str
    initial: tuple[float, ...]
    reference: tuple[float, ...]
    source_location: str
    diffusivity: float
    dx: float
    dt: float
    steps: int
    decay: float = 0.0
    tolerance: Tolerance | None = None
    # Defaults to True, as `StochasticClaim` does, and for the same reason: this class imposes a
    # boundary condition the paper did not choose, so every verdict rests on a value Reprolith
    # supplied. Off by default it was never set by any caller, and the shipped milestone published
    # `reproduced` with no assumption block for a run whose walls are Reprolith's own.
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)


def solver_pin() -> EnginePin:
    """The :class:`~reprolith.model.EnginePin` for this module's solver, at its current revision.

    The finite-difference solver is this package, so the pin's version is the package's — and that
    version has never moved, which left the freshness check comparing two identical pins and every
    certificate a solver fix invalidates looking current. The algorithm field therefore names the
    revision of the code that computed the profile (see
    :func:`reprolith.pins.algorithm_revision`); it moves whenever this module or the curve oracle it
    judges through does. The scheme is named too, because an explicit scheme's stability limit is
    part of what a reader needs to repeat the run.
    """
    from . import __version__  # local: the package imports this module while initializing

    revision = algorithm_revision("spatial", "oracle", "certificate")
    return EnginePin(
        engine="reprolith-fd",
        version=__version__,
        algorithm=f"explicit-forward-euler-finite-difference (rev {revision})",
    )


def certify_spatial(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[SpatialClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Run each spatial claim's diffusion to its stated time, judge the profile, build the certificate.

    The spatial class front-end (the counterpart of ``certify_curves`` / ``certify_stochastic``):
    each claim's reconstructed profile is simulated with :func:`diffuse_1d` and judged against the
    reported profile by the shared curve oracle, then assembled through the same rule and scope flag
    as every other class. Deterministic — no engine extra, no sampling qualification.

    A claim must describe a run of at least one step. A zero-step run returns the initial profile,
    which is an input to the reconstruction rather than evidence about it, so judging it against a
    reported profile would certify a simulation that never ran.

    **The boundary condition is an unconditional assumption of this class.** Every solver here
    imposes zero-flux (Neumann) boundaries; there is no Dirichlet, absorbing, or periodic option, and
    a claim carries no boundary field to state one. So a paper whose model has a different boundary
    is being run under a condition it did not specify. ``spatial_dossier`` records an unstated
    boundary as a load-bearing gap, but this front-end takes claims rather than a dossier and cannot
    see it — so the qualification is on by default and each qualified claim gets a load-bearing
    ``spatial-boundary-*`` assumption, exactly as the stochastic class does for its ensemble. Left to
    the caller it was never set, and the class published clean passes for runs whose walls are
    Reprolith's own. A caller certifying a genuinely unbounded claim can clear it per claim.
    """
    assessments = []
    qualified = []
    for claim in claims:
        if claim.steps < 1:
            raise ValueError(
                f"claim {claim.claim_id!r} asks for {claim.steps} steps: a spatial claim must "
                "evolve the profile by at least one step to be evidence about the model"
            )
        try:
            predicted = diffuse_1d(
                claim.initial, diffusivity=claim.diffusivity, dx=claim.dx, dt=claim.dt,
                steps=claim.steps, decay=claim.decay,
            )
        except UnstableDiscretization as unstable:
            # An unstable discretization genuinely cannot be run — but raising discarded the whole
            # certificate, including the honest verdicts of every sibling claim, and made the class
            # systematically silent at the top of the error range (a diffusivity wrong enough to
            # break the grid was un-certifiable rather than not-reproduced). "This protocol cannot
            # decide this claim" is an abstention, which is what the stochastic class already does
            # when its sampling cannot resolve a mean.
            assessments.append(not_evaluable(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reason=str(unstable),
                reference_kind=ReferenceKind.NUMERIC,
            ))
            continue
        assessments.append(
            replace(
                judge_curve(
                    claim_id=claim.claim_id,
                    quantity=claim.quantity,
                    source_location=claim.source_location,
                    reference=claim.reference,
                    predicted=predicted,
                    tolerance=claim.tolerance,
                    # A profile that genuinely misses used to raise here rather than certify:
                    # the judge requires a root cause for a non-pass and this front-end supplied
                    # none, so the only outcomes it could publish were a pass and a traceback —
                    # and the class's agreement rate was guaranteed rather than measured.
                    attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
                    assumption_qualified=claim.assumption_qualified,
                ),
                # The discretization is the run (spec: spatial-class — "the spatial step, time
                # step, and diffusivity are recorded as part of the claim's protocol"). Every
                # plausible alternative grid gives a different distance, so without this the
                # number on the certificate cannot be re-derived from it. The boundary is stated
                # too because this class has exactly one and a reader cannot see that anywhere else.
                # Printed in full precision, not :g — a reader who re-runs with the printed
                # number has to get the number that was run, and a stability-derived dt is rarely
                # six significant figures (0.0026666666666666674 printed as 0.00266667).
                protocol=(
                    f"1-D finite difference: D={claim.diffusivity!r}, dx={claim.dx!r}, "
                    f"dt={claim.dt!r}, {claim.steps} steps"
                    + (f", decay={claim.decay!r}" if claim.decay else "")
                    + ", zero-flux (Neumann) boundaries"
                ),
            )
        )
        # Only the claims a verdict was actually drawn from, as the stochastic class does: an
        # assumption attached to an abstention would describe a judgment nobody made, and being
        # load-bearing it would downgrade the certificate on that claim's behalf. Read off the
        # *assessment*, not the claim — the judge abstains internally on a non-finite profile
        # without raising, so gating on the claim's own flag minted an assumption for a claim that
        # came back `not-evaluable` and pushed the certificate to `partially-reproduced` anyway.
        if assessments[-1].assumption_qualified:
            qualified.append(claim)
    # The counterpart of the stochastic class's `ssa-sampling-*` block. The boundary is named in
    # each assessment's protocol, but a protocol line does not downgrade a verdict and does not
    # reach the "what was missing" report — so a wall Reprolith chose could push a claim to
    # `failed` and the certificate would attribute the miss to the paper.
    boundary = tuple(
        Assumption(
            id=f"spatial-boundary-{claim.claim_id}",
            description=(
                "the profile judged here was evolved under a boundary condition Reprolith "
                "imposes, not one the paper stated"
            ),
            chosen="zero-flux (Neumann) boundaries",
            basis=(
                "this solver has exactly one boundary condition and a claim carries no field to "
                "state another, so on a domain narrow enough for the walls to matter the distance "
                "moves with a choice the paper did not make"
            ),
            load_bearing=True,
            alternatives=("Dirichlet (fixed value)", "absorbing", "periodic", "an unbounded domain"),
        )
        for claim in qualified
    )
    return build_certificate(
        paper=paper, engine_pin=engine_pin,
        assessments=assessments, assumptions=(*assumptions, *boundary),
    )


def validate_spatial(dossier: Dossier) -> list[str]:
    """Structural problems that make a spatial dossier ill-formed; empty when well-formed.

    On top of the shared checks: an unstated spatial domain or boundary condition must be a
    load-bearing gap, because it changes the profile (spec: spatial-class — "Structural elements").
    """
    problems = dossier.validate()
    for gap in dossier.gaps:
        if gap.kind is GapKind.BOUNDARY and not gap.load_bearing:
            problems.append("an unstated domain/boundary condition must be recorded as a load-bearing gap")
    return problems


def spatial_dossier(
    entry: str,
    *,
    species: Sequence[str],
    diffusivities: Mapping[str, float],
    source_location: str,
    boundary_stated: bool,
    claims: Sequence[DossierClaim] = (),
) -> Dossier:
    """Assemble a well-formed spatial dossier, or raise if it is ill-formed.

    Records the ``species`` as state variables, their ``diffusivities`` as parameters, and the
    reported profile ``claims``. When ``boundary_stated`` is false the spatial domain / boundary
    condition is recorded as a load-bearing :class:`~reprolith.dossier.Gap`. Validated by
    :func:`validate_spatial`.
    """
    parameters = tuple(
        Parameter(name=f"D_{name}", value=diffusivities[name], unit="length^2/time",
                  source_location=source_location)
        for name in sorted(diffusivities)
    )
    gaps: tuple[Gap, ...] = ()
    if not boundary_stated:
        gaps = (Gap(
            element="domain/boundary condition",
            kind=GapKind.BOUNDARY,
            detail="the paper does not state the spatial domain or its boundary conditions",
            load_bearing=True,
        ),)
    dossier = Dossier(
        entry=entry,
        state_variables=tuple(sorted(species)),
        parameters=parameters,
        claims=tuple(claims),
        gaps=gaps,
    )
    problems = validate_spatial(dossier)
    if problems:
        raise ValueError("ill-formed spatial dossier: " + "; ".join(problems))
    return dossier


__all__ = [
    "SpatialClaim",
    "certify_spatial",
    "diffuse_1d",
    "diffuse_2d",
    "front_position",
    "gaussian_field_2d",
    "gaussian_profile",
    "gradient_decay_length",
    "morphogen_gradient",
    "react_diffuse_1d",
    "react_diffuse_2species",
    "spatial_dossier",
    "validate_spatial",
]
