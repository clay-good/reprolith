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
from dataclasses import dataclass, field

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Gap, GapKind, Parameter
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import Attribution, Tolerance, judge_curve


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
    limit — so an unstable discretization is refused, not run to a diverging profile.
    """
    alpha = diffusivity * dt / (dx * dx)
    if alpha > 0.5 + 1e-12:
        raise ValueError(
            f"unstable discretization: D·dt/dx² = {alpha:.3g} exceeds the explicit limit 0.5; "
            "reduce dt or increase dx"
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
    and subject to the same diffusion stability limit (the reaction term's own stability is the
    caller's to keep, e.g. by a small ``dt``).
    """
    alpha = diffusivity * dt / (dx * dx)
    if alpha > 0.5 + 1e-12:
        raise ValueError(
            f"unstable discretization: D·dt/dx² = {alpha:.3g} exceeds the explicit limit 0.5"
        )
    current = list(profile)
    n = len(current)
    if n < 2:
        raise ValueError("need at least two grid points")
    for _ in range(steps):
        nxt = current[:]
        for i in range(n):
            left = current[i - 1] if i > 0 else current[i]
            right = current[i + 1] if i < n - 1 else current[i]
            nxt[i] = current[i] + alpha * (left - 2.0 * current[i] + right) + dt * reaction(current[i])
        current = nxt
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
    alpha = diffusivity * dt / (dx * dx)
    if alpha > 0.5 + 1e-12:
        raise ValueError(
            f"unstable discretization: D·dt/dx² = {alpha:.3g} exceeds the explicit limit 0.5"
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
    are the local rates ``f`` and ``g``. Deterministic; both species must satisfy the diffusion
    stability limit.
    """
    au, av = du * dt / (dx * dx), dv * dt / (dx * dx)
    if au > 0.5 + 1e-12 or av > 0.5 + 1e-12:
        raise ValueError(
            f"unstable discretization: D·dt/dx² = {max(au, av):.3g} exceeds the explicit limit 0.5"
        )
    cu, cv = list(u), list(v)
    n = len(cu)
    if n < 2 or len(cv) != n:
        raise ValueError("u and v must have the same length, at least two grid points")
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
    """
    for i in range(len(profile) - 1):
        if profile[i] >= level >= profile[i + 1]:
            span = profile[i] - profile[i + 1]
            frac = (profile[i] - level) / span if span != 0.0 else 0.0
            return (i + frac) * dx
    return None


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
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)


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
    """
    assessments = []
    for claim in claims:
        predicted = diffuse_1d(
            claim.initial, diffusivity=claim.diffusivity, dx=claim.dx, dt=claim.dt,
            steps=claim.steps, decay=claim.decay,
        )
        assessments.append(
            judge_curve(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reference=claim.reference,
                predicted=predicted,
                tolerance=claim.tolerance,
                attribution=claim.shortfall,
                assumption_qualified=claim.assumption_qualified,
            )
        )
    return build_certificate(
        paper=paper, engine_pin=engine_pin,
        assessments=assessments, assumptions=tuple(assumptions),
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
    "front_position",
    "gaussian_profile",
    "gradient_decay_length",
    "morphogen_gradient",
    "react_diffuse_1d",
    "react_diffuse_2species",
    "spatial_dossier",
    "validate_spatial",
]
