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
from typing import Any

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Gap, GapKind, Parameter
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    ComparisonMethod,
    ReferenceKind,
    Tolerance,
    default_tolerance,
    judge_curve,
    normalized_curve_distance,
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
        # UnstableDiscretization, not ValueError: this is a statement about the grid, exactly like
        # the two checks below it, and certify_spatial catches only UnstableDiscretization in order
        # to abstain on one claim. Raised as a ValueError it escaped that handler and took down the
        # whole certificate, discarding every sibling claim's honest verdict over a step size.
        raise UnstableDiscretization(
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
    checked: tuple[float, float, float] | None = None,
) -> tuple[float, float, float]:
    """Refuse a step whose diffusion *and reaction* together leave the stable amplification band.

    The explicit update's amplification at the shortest wavelength is ``1 − 4α − dt·f′``, so the
    reaction has to be budgeted against the same [−1, 1] band the diffusion number is checked in —
    the way :func:`_diffusion_number` already budgets a linear decay. ``f′`` is not known
    symbolically here, so it is estimated by differencing ``f`` across the values the profile
    actually holds.

    Sampled *inside* the profile's own closed range, never outside it. Widening the probe to
    anticipate growth meant evaluating the caller's reaction where the run never goes: a reaction
    with an ordinary non-negativity check raised, ``u**0.5`` went complex, and a uniform profile at
    large magnitude widened by less than one ulp. Growth is handled by re-checking as the profile
    grows, which is what the run actually does.

    A *uniform* profile is therefore not probed at all, and reports no slope. That is not a gap: the
    instability guarded against is neighbouring grid points decoupling, and under the zero-flux
    update a uniform profile stays bitwise uniform, so there is no such mode. The step that moves it
    off uniform is re-checked on the range it reaches.

    ``checked`` carries what a previous call already covered — the range and the largest slope found
    in it — so a re-check probes only the sliver the profile has newly entered and keeps the slope
    already measured. That is what makes re-checking on *any* departure affordable: an earlier
    version skipped re-checks until the profile left the accumulated band by 1%, and because that
    band only ever grows, a profile drifting step by step into a region with ``dt·|f′| = 25`` was
    never re-probed at all — the run returned 4.92 against a true 5.00, finite and plausible and
    wrong, which is the exact failure this guard exists to prevent.
    """
    finite = [v for v in values if math.isfinite(v)]
    if not finite or dt == 0.0:
        return checked if checked is not None else (0.0, 0.0, 0.0)
    lo, hi = min(finite), max(finite)
    slope = 0.0
    if checked is None:
        intervals = [(lo, hi)] if hi > lo else []
    else:
        seen_lo, seen_hi, slope = checked
        # Only the newly entered slivers; the interior is already accounted for by `slope`.
        intervals = [
            (a, b) for a, b in ((lo, seen_lo), (seen_hi, hi)) if b > a
        ]
        lo, hi = min(lo, seen_lo), max(hi, seen_hi)
    for left, right in intervals:
        # A sliver needs fewer samples than a first look at the whole range, and its slope is
        # folded into the running maximum rather than replacing it.
        count = samples if checked is None else 5
        step = (right - left) / (count - 1)
        if step == 0.0:
            # A sliver narrower than float resolution at this magnitude: the probes would all be
            # the same value and the difference quotient would divide by zero. A smooth reaction's
            # slope across it is the slope already measured on the range beside it.
            continue
        probes = [left + i * step for i in range(count)]
        for a, b in zip(probes, probes[1:]):
            if b == a:
                continue
            # No exception handling: every probe is a value the profile holds, so a reaction that
            # cannot be evaluated at one of them cannot be run either, and that error belongs to
            # the caller rather than being turned into a silently skipped check.
            rise = reaction(b) - reaction(a)
            if math.isfinite(rise):
                slope = max(slope, abs(rise) / (b - a))
    combined = 4.0 * alpha + dt * slope
    if combined > 2.0 + 1e-12:
        raise UnstableDiscretization(
            f"unstable discretization: diffusion and reaction together give an amplification of "
            f"{1.0 - combined:.3g} at the shortest wavelength, outside [-1, 1] "
            f"(D·dt/dx² = {alpha:.3g}, dt·|f'| = {dt * slope:.3g}); reduce dt or dx"
        )
    return lo, hi, slope


def _hold(
    f: Callable[[float, float], float], partner: float, *, first: bool
) -> Callable[[float], float]:
    """``f`` as a function of one species, with the other held at ``partner``."""
    return (lambda x: f(x, partner)) if first else (lambda x: f(partner, x))


def _partner_probes(values: Sequence[float], samples: int = 9) -> list[float]:
    """The partner-species values to hold ``f`` at — drawn from the grid itself.

    The values the run visits, evenly subsampled, rather than a uniform grid over their range: the
    same rule :func:`_reaction_stability` follows for the species it is differencing. A uniform grid
    over the range steps over a narrow feature the profile sits on — measured, an activation window
    at ``v = 51`` that a grid point lands exactly on reported ``dt·|∂f/∂u| = 1.1e-06`` against a true
    10, and the run returned 1.5e38 against a reference of 1.2e-174.
    """
    finite = sorted({v for v in values if math.isfinite(v)})
    if not finite:
        return [0.0]
    if len(finite) <= samples:
        return finite
    step = (len(finite) - 1) / (samples - 1)
    return [finite[round(i * step)] for i in range(samples)]


def _left_checked(values: Sequence[float], checked: tuple[float, float, float]) -> bool:
    """Whether a profile has moved outside the range already probed.

    Any departure at all. A tolerance here is measured against a band that only ever grows, so it
    lets a profile drift step by step into a region far stiffer than anything checked; the cost of
    checking every departure is paid instead by probing only the newly entered sliver.
    """
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return False
    lo, hi, _ = checked
    return min(finite) < lo or max(finite) > hi


#: The boundary conditions this solver implements, and what each does at the edge of the domain.
#:
#: ``no-flux`` mirrors the edge point, so nothing leaves the domain and mass is conserved. It was
#: the only one for as long as this class has existed, which made it an unconditional assumption on
#: every spatial certificate: the queue reported it as a limit of this engine that no expert
#: decision closes, and it was true. ``dirichlet`` holds the edge at a fixed value (absorbing at
#: the default 0), and ``periodic`` wraps, so what leaves one end enters the other.
#:
#: Having more than one is what makes the assumption *measurable*: with a single boundary, "the
#: distance moves with a choice the paper did not make" can only ever be asserted.
BOUNDARIES = ("no-flux", "dirichlet", "periodic")

#: How each wall is named on a certificate, where "no-flux" alone would not tell a reader which
#: mathematical condition was imposed.
_WALL_NAMES = {
    "no-flux": "zero-flux (Neumann) boundaries",
    "dirichlet": "Dirichlet (fixed-value) boundaries",
    "periodic": "periodic boundaries",
}


def _neighbours(
    current: list[float], i: int, n: int, boundary: str, value: float
) -> tuple[float, float]:
    """The two neighbours of grid point ``i`` under ``boundary``."""
    if boundary == "periodic":
        return current[i - 1], current[(i + 1) % n]
    if boundary == "dirichlet":
        return (current[i - 1] if i > 0 else value), (current[i + 1] if i < n - 1 else value)
    # no-flux: mirror the edge point, so the gradient across the boundary is zero
    return (current[i - 1] if i > 0 else current[i]), (current[i + 1] if i < n - 1 else current[i])


def diffuse_1d(
    profile: Sequence[float],
    *,
    diffusivity: float,
    dx: float,
    dt: float,
    steps: int,
    decay: float = 0.0,
    boundary: str = "no-flux",
    boundary_value: float = 0.0,
) -> list[float]:
    """Evolve a 1-D concentration profile under diffusion (and optional first-order decay).

    Solves ``∂C/∂t = D ∂²C/∂x² − k·C`` with the explicit forward-time centered-space scheme.
    ``profile`` is the initial concentration at uniformly spaced points ``dx`` apart; the result is
    the profile after ``steps`` steps of size ``dt``. Deterministic in its inputs.

    ``boundary`` is one of :data:`BOUNDARIES`. The default, ``no-flux``, is what this solver did
    unconditionally before the others existed, so every published spatial certificate was computed
    under it and still is — the default is the compatibility guarantee, not a preference.
    ``dirichlet`` holds both ends at ``boundary_value`` (absorbing at the default 0); ``periodic``
    wraps. Only ``no-flux`` conserves mass: the other two are ways for material to leave or
    re-enter, which is the point of having them.

    Raises if the diffusion number ``D·dt/dx²`` exceeds ``0.5`` — the explicit scheme's stability
    limit — so an unstable discretization is refused, not run to a diverging profile, and equally
    refuses a discretization too small to advance the profile at all (see
    :func:`_diffusion_number`), which would otherwise return the initial condition as a result.
    """
    if boundary not in BOUNDARIES:
        raise ValueError(
            f"unknown boundary {boundary!r}; this solver implements {', '.join(BOUNDARIES)}"
        )
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
            left, right = _neighbours(current, i, n, boundary, boundary_value)
            laplacian = left - 2.0 * current[i] + right
            nxt[i] = current[i] + alpha * laplacian - decay * dt * current[i]
        if boundary == "dirichlet":
            # The edge points are held, not evolved: a Dirichlet condition fixes the value there
            # rather than merely supplying a neighbour for it.
            nxt[0] = nxt[-1] = boundary_value
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
    probed = _reaction_stability(current, reaction, alpha=alpha, dt=dt)
    for _ in range(steps):
        nxt = current[:]
        for i in range(n):
            left = current[i - 1] if i > 0 else current[i]
            right = current[i + 1] if i < n - 1 else current[i]
            nxt[i] = current[i] + alpha * (left - 2.0 * current[i] + right) + dt * reaction(current[i])
        current = nxt
        if _left_checked(current, probed):
            probed = _reaction_stability(current, reaction, alpha=alpha, dt=dt, checked=probed)
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
    # Probed across the partner species' own range, not at 0.0 and not only at its endpoints. A
    # value the run never visits can report a slope of zero where the true one is large — `g(0, v)`
    # is identically zero for a Brusselator, and any mass-action `-k·u·v` vanishes there — and a
    # slope maximized at an interior partner value (substrate inhibition peaks at v = √(K·Ki)) is
    # invisible to the two endpoints alone: measured, 133 at the bulk value against 0.0 and 3.96 at
    # the ends, which admitted a run returning 165 against a reference of 1.5e-12.
    def _check_pair(
        cu: list[float],
        cv: list[float],
        seen_u: tuple[float, float, float] | None = None,
        seen_v: tuple[float, float, float] | None = None,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        # Every partner value gets the *same* already-probed range, and the results are combined
        # afterwards. Threading one partner's result into the next made the range look covered
        # after the first partner, so the other eight never probed anything at all: an activation
        # window that only fires at one partner value reported a slope of zero and the run
        # returned 6.4e33. The ranges already seen are carried in the same way the one-species
        # loop carries them — without that union a profile uniform at every step is degenerate on
        # every individual check and is never probed.
        def _combine(
            spans: list[tuple[float, float, float]], seen: tuple[float, float, float] | None
        ) -> tuple[float, float, float]:
            if not spans:
                return seen if seen is not None else (0.0, 0.0, 0.0)
            return (
                min(span[0] for span in spans),
                max(span[1] for span in spans),
                max(span[2] for span in spans),
            )

        span_u = _combine(
            [
                _reaction_stability(
                    cu, _hold(reaction_u, partner, first=True), alpha=au, dt=dt, checked=seen_u
                )
                for partner in _partner_probes(cv)
            ],
            seen_u,
        )
        span_v = _combine(
            [
                _reaction_stability(
                    cv, _hold(reaction_v, partner, first=False), alpha=av, dt=dt, checked=seen_v
                )
                for partner in _partner_probes(cu)
            ],
            seen_v,
        )
        return span_u, span_v

    # The same re-check the one-species solver does, for the same reason and on the same rule: it
    # landed there and not here, so an identical model refused at dt=0.008 in one solver and
    # returned 5.65 against a true 10.0 in the other.
    checked_u, checked_v = _check_pair(cu, cv)
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
        if _left_checked(cu, checked_u) or _left_checked(cv, checked_v):
            checked_u, checked_v = _check_pair(cu, cv, checked_u, checked_v)
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
    #: The wall this claim's source states, when it states one. ``None`` means it does not, which
    #: is the case every published certificate here was produced under: the run then uses
    #: ``no-flux`` and carries the load-bearing assumption saying so. A claim that *names* its
    #: boundary is a different situation — the wall is then the model's, not Reprolith's — and
    #: :func:`certify_spatial` neither assumes nor qualifies it. This field is what
    #: ``ingest_spatial_sbml`` needed before it could stop refusing a file that states a Dirichlet
    #: wall: the refusal was never that the solver could not run one, but that nothing carried the
    #: statement through to the run.
    boundary: str | None = None
    #: The value a Dirichlet wall is held at; ignored for the others. Absorbing at the default.
    boundary_value: float = 0.0
    # Defaults to True, as `StochasticClaim` does, and for the same reason: a claim that states no
    # boundary is run under one Reprolith chose, so its verdict rests on a value Reprolith
    # supplied. Off by default it was never set by any caller, and the shipped milestone published
    # `reproduced` with no assumption block for a run whose walls are Reprolith's own. A claim that
    # states its boundary sets this False for itself — nothing was assumed.
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)

    def __post_init__(self) -> None:
        if self.boundary is not None and self.boundary not in BOUNDARIES:
            raise ValueError(
                f"claim {self.claim_id!r} names boundary {self.boundary!r}; this solver runs "
                f"{', '.join(BOUNDARIES)}"
            )

    @property
    def wall(self) -> str:
        """The boundary this claim is actually run under — its own, or this engine's default."""
        return self.boundary or "no-flux"

    @property
    def wall_is_reprolith_s(self) -> bool:
        """Whether the wall was Reprolith's choice rather than something the source stated."""
        return self.boundary is None


def boundary_sensitivity(claim: SpatialClaim) -> dict[str, Any] | None:
    """What the wall costs this claim, in the statistic the verdict is actually drawn from.

    The measurement the boundary assumption could not carry while this solver had exactly one wall.
    Re-runs the claim's own protocol under each alternative in :data:`BOUNDARIES` and reports the
    **judged distance** — the same normalized curve distance against the claim's own reference that
    decides the verdict — under the wall that was used and under the worst alternative. ``None``
    when the discretization does not run: it is the claim's own, so if it is unstable for one wall
    it is unstable for all, and nothing is reported rather than a number from a run that did not
    happen.

    Reporting the distance rather than the raw profile deviation is the whole point of the units.
    The tolerance a spatial claim is judged against is a normalized curve distance; a maximum
    absolute concentration difference is a different quantity, and putting the two beside each
    other — which the first version of this did — compares a length to a ratio and reads as though
    it means something.

    This turns "on a domain narrow enough for the walls to matter the distance moves with a choice
    the paper did not make" from a statement into a bound. It stays a *conditional* claim — it
    always was — and the condition is now checked for the run in hand rather than left to the
    reader. An unbounded domain is not among the alternatives because this solver cannot run one;
    it stays listed on the assumption, unmeasured and said to be so.
    """
    def distance(boundary: str) -> float | None:
        try:
            profile = diffuse_1d(
                claim.initial, diffusivity=claim.diffusivity, dx=claim.dx, dt=claim.dt,
                steps=claim.steps, decay=claim.decay, boundary=boundary,
                boundary_value=claim.boundary_value,
            )
        except UnstableDiscretization:
            return None
        return normalized_curve_distance(claim.reference, profile)

    judged = distance(claim.wall)
    if judged is None or not claim.reference:
        return None
    alternatives: dict[str, float] = {}
    for name in BOUNDARIES:
        if name == claim.wall:
            continue
        moved = distance(name)
        if moved is not None:  # pragma: no branch - the discretization is the same for all walls
            alternatives[name] = moved
    if not alternatives:  # pragma: no cover - unreachable while every wall shares one grid
        return None
    worst = max(alternatives, key=lambda name: abs(alternatives[name] - judged))
    tolerance = claim.tolerance or default_tolerance(
        ComparisonMethod.CURVE_NORMALIZED_DISTANCE, ReferenceKind.NUMERIC
    )
    return {
        "judged_distance": judged,
        "worst_alternative": worst,
        "worst_distance": alternatives[worst],
        "moved_by": abs(alternatives[worst] - judged),
        "pass_within": tolerance.reproduced_within,
    }


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
        if not claim.reference:
            # No reported profile to compare against — abstain rather than run and judge against
            # nothing. `certify_curves` answers the same input the same way; before this, the two
            # front-ends over the same oracle disagreed about a reference-less claim, one abstaining
            # and one raising out of the whole certificate. NUMERIC because this class states no
            # reference kind anywhere and its sibling abstention already says NUMERIC.
            # Ordered *after* the step check on purpose: a claim that asks for zero steps is a
            # caller's bug and must still raise, and checking the reference first turned a
            # malformed claim into a published abstention — the same "a bug published as an honest
            # abstention" shape `UnstableDiscretization` exists to prevent.
            assessments.append(not_evaluable(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reason=(
                    "no reported profile for this claim: there is nothing to compare the "
                    "simulated profile against"
                ),
                reference_kind=ReferenceKind.NUMERIC,
            ))
            continue
        try:
            predicted = diffuse_1d(
                claim.initial, diffusivity=claim.diffusivity, dx=claim.dx, dt=claim.dt,
                steps=claim.steps, decay=claim.decay,
                boundary=claim.wall, boundary_value=claim.boundary_value,
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
                    # One expression governs the flag and the assumption below, because they are
                    # one fact. This flag defaults True in this class *because* the wall is
                    # Reprolith's, so a claim that states its own wall must not carry it: it left
                    # a certificate with no assumptions reading `partially-reproduced` for a
                    # qualification nothing on it named.
                    assumption_qualified=_rests_on_our_wall(claim),
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
                    + f", {_WALL_NAMES[claim.wall]}"
                    + ("" if claim.wall_is_reprolith_s else " stated by the source")
                    # What that wall costs *this* claim. It belongs here rather than in the
                    # assumption's basis: the assumption is one fact about this engine, and
                    # putting a per-claim number in its wording gave three claims three different
                    # questions, so one solver limitation stopped merging into one queue item and
                    # its impact fell from three dependents to one.
                    + _boundary_cost(claim)
                ),
            )
        )
        # Only the claims a verdict was actually drawn from, as the stochastic class does: an
        # assumption attached to an abstention would describe a judgment nobody made, and being
        # load-bearing it would downgrade the certificate on that claim's behalf. Read off the
        # *assessment*, not the claim — the judge abstains internally on a non-finite profile
        # without raising, so gating on the claim's own flag minted an assumption for a claim that
        # came back `not-evaluable` and pushed the certificate to `partially-reproduced` anyway.
        # A claim that names its own boundary rests on nothing Reprolith supplied for it, so it
        # gets no boundary assumption — and, having stated it, can reach a clean pass.
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
                # Not "not one the paper stated" — this front-end takes claims rather than a
                # dossier and never sees whether a boundary was stated, as the docstring above
                # concedes. Asserting it published a fact about the author's paper that nothing
                # checked, and vacuously so for the three committed entries, which have no paper
                # at all. What is true is what this engine does, and that it did not look.
                "the profile judged here was evolved under zero-flux (Neumann) boundaries; "
                "Reprolith did not check what boundary the source specifies"
            ),
            chosen="zero-flux (Neumann) boundaries",
            basis=_BOUNDARY_BASIS,
            load_bearing=True,
            alternatives=(
                "Dirichlet (fixed value)",
                "absorbing (Dirichlet at zero)",
                "periodic",
                "an unbounded domain (not implemented, so not measured)",
            ),
            # A claim carries no field naming a boundary, so no wording in a paper reaches this
            # front-end: it stays this engine's limit rather than the paper's omission, even now
            # that the alternatives can be *run*. What changed is that the cost of the choice is
            # measured instead of asserted.
            author_can_close=False,
        )
        for claim in qualified
    )
    return build_certificate(
        paper=paper, engine_pin=engine_pin,
        assessments=assessments, assumptions=(*assumptions, *boundary),
    )


#: The boundary assumption's basis. Identical for every claim on purpose: it states one fact about
#: this engine, and an item in the verification queue is keyed by its question — so a per-claim
#: number here gives three claims three different questions, and one solver limitation stops
#: merging into one item with three dependents. Its impact then reads as 1 instead of 3, which
#: understates precisely what the queue exists to rank. The measurement lives on each claim's
#: protocol line, where the rest of that run's facts already are.
_BOUNDARY_BASIS = (
    "a claim carries no field naming a boundary, so this run's wall is this engine's choice rather "
    "than anything a paper could state. What the choice costs is no longer a caveat: each claim's "
    "protocol line reports how far re-running the same discretization under the alternatives this "
    "solver implements moves the judged distance, against the threshold it is judged at. An "
    "unbounded domain is not among those alternatives and is not measured"
)


def _rests_on_our_wall(claim: SpatialClaim) -> bool:
    """Whether this claim's verdict rests on a boundary Reprolith chose for it.

    ``SpatialClaim.assumption_qualified`` defaults True in this class for exactly one reason — the
    wall was this engine's — so a claim that states its own wall has nothing left for the flag to
    mean. Read here rather than in two places, because the flag and the assumption below are one
    fact: setting them apart left a certificate carrying no assumptions and still reporting
    `partially-reproduced`, a qualification nothing on it named.
    """
    return claim.assumption_qualified and claim.wall_is_reprolith_s


def _boundary_cost(claim: SpatialClaim) -> str:
    """The protocol line's measured boundary cost for one claim, or a clause saying there is none.

    This used to be the assumption's basis and ended "so on a domain narrow enough for the walls to
    matter the distance moves with a choice the paper did not make" — true, conditional, and
    leaving the reader to guess whether the condition holds for the run in front of them. It holds
    or it does not, and the solver can now be asked.
    """
    measured = boundary_sensitivity(claim)
    if measured is None:  # pragma: no cover - a judged claim ran, so its alternatives run too
        return " (the boundary's cost was not measurable for this run)"
    return (
        f" (that wall costs this claim {measured['moved_by']:.3e}: the judged distance moves from "
        f"{measured['judged_distance']:.3e} to {measured['worst_distance']:.3e} under "
        f"{measured['worst_alternative']}, against a pass threshold of "
        f"{measured['pass_within']:.3e})"
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


@dataclass(frozen=True)
class SpatialModel:
    """A reaction-diffusion model read from a file: what diffuses, how fast, and over what.

    The runtime shape of :func:`reprolith.ingest_spatial_sbml`, holding only what this class's
    solver actually consumes. ``extent`` is the domain's physical size along each Cartesian axis
    in the file's own units, in axis order, so a caller choosing a grid gets ``dx`` from a length
    the file states rather than from a number nobody wrote down.
    """

    species: tuple[str, ...]
    diffusivities: tuple[tuple[str, float], ...]
    initial: tuple[tuple[str, float], ...]
    extent: tuple[float, ...]
    #: First-order decay constants read from the file's reactions, per species. This is the one
    #: reaction term the class's solver takes as a number (:func:`diffuse_1d`'s ``decay``), and it
    #: is the morphogen-gradient case: diffusion against linear decay. A species the file gives no
    #: decay reaction has none, which is what ``decay_of`` returns.
    decay: tuple[tuple[str, float], ...] = ()
    #: The boundary the file states, in this solver's vocabulary, or ``None`` where it states
    #: none. Reading it is what let ``ingest_spatial_sbml`` stop refusing a Dirichlet file: the
    #: refusal was never that the solver could not run one, but that nothing carried the file's
    #: statement through to the run. A claim built from this model passes it on
    #: (:attr:`SpatialClaim.boundary`), so the wall the model asks for is the wall it gets.
    boundary: str | None = None
    #: The value a stated Dirichlet wall is held at.
    boundary_value: float = 0.0

    def diffusivity_of(self, species: str) -> float:
        return dict(self.diffusivities)[species]

    def decay_of(self, species: str) -> float:
        """The species' first-order decay constant, or zero where the file states none."""
        return dict(self.decay).get(species, 0.0)

    def dossier(self, entry: str, *, source_location: str) -> Dossier:
        """This model as a spatial dossier — with the domain recorded as stated, because it is.

        The class records an unstated domain or boundary as a load-bearing gap, which is what a
        *paper* usually leaves out. A file carrying a geometry states it, and recording a gap here
        would report the artifact as missing something it ships.
        """
        return spatial_dossier(
            entry,
            species=self.species,
            diffusivities=dict(self.diffusivities),
            source_location=source_location,
            boundary_stated=True,
        )


__all__ = [
    "SpatialClaim",
    "SpatialModel",
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
