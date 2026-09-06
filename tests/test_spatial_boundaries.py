"""The second and third boundary conditions, and what having them makes measurable.

Until now this solver imposed zero-flux (Neumann) walls and had no alternative, which made the
boundary an *unconditional* assumption on every spatial certificate: the verification queue
reported it as a limit of this engine that no expert decision closes, and that was exactly right.
The cost of having one is that "on a domain narrow enough for the walls to matter the distance
moves with a choice the paper did not make" can only ever be asserted — there is nothing to move it
to.

Each boundary is validated against an exact solution of the diffusion equation rather than against
another run of this solver: an eigenfunction of the Laplacian satisfying that boundary decays as
``exp(-D k² t)`` without changing shape, so the closed form is known for all time. Mass behaviour
is checked too, because it needs no grid convention at all and separates the three unambiguously:
zero-flux reflects, periodic wraps, Dirichlet absorbs.
"""

from __future__ import annotations

import math

import pytest
from reprolith.spatial import BOUNDARIES, diffuse_1d

_D = 0.3
_ALPHA = 0.2  # diffusion number, well inside the explicit scheme's 0.5 limit


def _grid(points: int, length: float = 1.0, *, endpoint: bool = True):
    dx = length / (points - 1) if endpoint else length / points
    return dx, [i * dx for i in range(points)]


def _run(u0, dx, *, boundary, steps):
    dt = _ALPHA * dx * dx / _D
    got = diffuse_1d(u0, diffusivity=_D, dx=dx, dt=dt, steps=steps, boundary=boundary)
    return got, steps * dt


# --- each boundary against a closed form ------------------------------------------------------


def test_a_dirichlet_wall_decays_the_sine_mode_at_its_analytical_rate() -> None:
    """``sin(πx/L)`` is zero at both walls, so it satisfies an absorbing boundary exactly and
    decays as ``exp(-Dπ²t/L²)`` for all time."""
    dx, x = _grid(201)
    u0 = [math.sin(math.pi * xi) for xi in x]
    got, t = _run(u0, dx, boundary="dirichlet", steps=400)
    exact = [math.exp(-_D * math.pi**2 * t) * v for v in u0]
    assert max(abs(a - b) for a, b in zip(got, exact)) < 1e-5


def test_a_periodic_wall_decays_the_cosine_mode_at_its_analytical_rate() -> None:
    """The grid excludes the far endpoint: under periodicity ``x=0`` and ``x=L`` are one point, and
    including both makes the wrap span an extra cell — a convention error that looks exactly like a
    solver error, and did, until the grid was built the way periodicity requires."""
    dx, x = _grid(200, endpoint=False)
    k = 2 * math.pi
    u0 = [math.cos(k * xi) for xi in x]
    got, t = _run(u0, dx, boundary="periodic", steps=400)
    exact = [math.exp(-_D * k * k * t) * v for v in u0]
    assert max(abs(a - b) for a, b in zip(got, exact)) < 1e-5


def test_the_zero_flux_wall_decays_the_cosine_mode_at_its_analytical_rate() -> None:
    """``cos(πx/L)`` has zero gradient at both walls. Held to a looser bound than the other two on
    purpose — see the convergence test below, which measures why."""
    dx, x = _grid(201)
    u0 = [math.cos(math.pi * xi) for xi in x]
    got, t = _run(u0, dx, boundary="no-flux", steps=400)
    exact = [math.exp(-_D * math.pi**2 * t) * v for v in u0]
    assert max(abs(a - b) for a, b in zip(got, exact)) < 5e-3


# --- what each does to mass, which needs no convention ----------------------------------------


def _mass(profile, dx):
    return sum(profile) * dx


def test_the_three_boundaries_do_the_three_things_to_mass() -> None:
    dx, x = _grid(201)
    u0 = [math.exp(-((xi - 0.5) ** 2) / (2 * 0.01)) for xi in x]
    before = _mass(u0, dx)

    reflected, _ = _run(u0, dx, boundary="no-flux", steps=4000)
    wrapped, _ = _run(u0, dx, boundary="periodic", steps=4000)
    absorbed, _ = _run(u0, dx, boundary="dirichlet", steps=4000)

    assert _mass(reflected, dx) == pytest.approx(before, rel=1e-12), "zero-flux conserves mass"
    assert _mass(wrapped, dx) == pytest.approx(before, rel=1e-12), "periodic conserves mass"
    assert _mass(absorbed, dx) < before * 0.99, "an absorbing wall takes material out"
    # And the absorbing wall is actually held at its value, not merely fed a neighbour.
    assert absorbed[0] == 0.0 and absorbed[-1] == 0.0


def test_a_non_zero_dirichlet_value_is_held_at_both_ends() -> None:
    """The wall is a *value*, not only an absorber: held at 2.0, an initially empty domain fills
    from both ends. Without `boundary_value` the option would only ever mean "absorbing"."""
    dx, x = _grid(101)
    dt = _ALPHA * dx * dx / _D
    got = diffuse_1d(
        [0.0] * len(x),
        diffusivity=_D,
        dx=dx,
        dt=dt,
        steps=500,
        boundary="dirichlet",
        boundary_value=2.0,
    )
    assert got[0] == pytest.approx(2.0) and got[-1] == pytest.approx(2.0)
    # And it soaks inward from the walls rather than staying pinned to the initial zero.
    assert got[1] > 0.0 and got[-2] > 0.0


# --- the accuracy the boundary actually buys --------------------------------------------------


@pytest.mark.parametrize(
    "boundary, mode, expected_order",
    [
        # Second order: the error falls by four when the grid halves.
        ("dirichlet", math.sin, 4.0),
        # First order: it falls by two. The mirrored ghost point sets a zero gradient half a cell
        # *outside* the domain, at x = -dx/2 rather than at x = 0, and that half-cell offset is
        # first-order in dx. The interior stencil is second-order in both cases — so wherever the
        # wall influences the answer, this solver's accuracy is set by its boundary and not by its
        # stencil, which is a fact about every published spatial certificate and was written down
        # nowhere.
        ("no-flux", math.cos, 2.0),
    ],
)
def test_the_boundary_treatment_sets_the_order_of_accuracy(boundary, mode, expected_order) -> None:
    errors = []
    for points in (101, 201, 401):
        dx, x = _grid(points)
        dt = _ALPHA * dx * dx / _D
        steps = max(1, round(0.0658 / dt))
        u0 = [mode(math.pi * xi) for xi in x]
        got = diffuse_1d(u0, diffusivity=_D, dx=dx, dt=dt, steps=steps, boundary=boundary)
        t = steps * dt
        exact = [math.exp(-_D * math.pi**2 * t) * v for v in u0]
        errors.append(max(abs(a - b) for a, b in zip(got, exact)))
    for coarse, fine in zip(errors, errors[1:]):
        assert coarse / fine == pytest.approx(expected_order, rel=0.1), (
            f"{boundary}: error ratio {coarse / fine:.2f}, expected {expected_order}"
        )


# --- the contract -----------------------------------------------------------------------------


def test_the_default_is_what_every_published_certificate_was_computed_under() -> None:
    """The compatibility guarantee, pinned. Every spatial certificate in this repository was
    produced before the other boundaries existed, so a changed default would silently re-mean
    all of them."""
    dx, x = _grid(101)
    u0 = [math.exp(-((xi - 0.5) ** 2) / (2 * 0.01)) for xi in x]
    dt = _ALPHA * dx * dx / _D
    assert diffuse_1d(u0, diffusivity=_D, dx=dx, dt=dt, steps=200) == diffuse_1d(
        u0, diffusivity=_D, dx=dx, dt=dt, steps=200, boundary="no-flux"
    )


def test_an_unknown_boundary_is_refused_by_name() -> None:
    dx, x = _grid(51)
    with pytest.raises(ValueError, match="unknown boundary"):
        diffuse_1d([0.0] * len(x), diffusivity=_D, dx=dx, dt=1e-4, steps=1, boundary="absorbing")
    assert set(BOUNDARIES) == {"no-flux", "dirichlet", "periodic"}


# --- where the measurement is allowed to live -------------------------------------------------


def test_the_measured_cost_is_on_the_claim_and_the_question_stays_one_question() -> None:
    """A verification-queue item is keyed by its question, so a per-claim number in the boundary
    assumption's *basis* gives three claims three different questions: one solver limitation stops
    merging into one item with three dependents and its impact reads as 1 instead of 3 —
    understating exactly what the queue ranks by. The number belongs on the claim's protocol line,
    where the rest of that run's facts already are.
    """
    from reprolith import certificate_digest, queue_report
    from reprolith.model import PaperIdentity
    from reprolith.spatial import SpatialClaim, certify_spatial, gaussian_profile, solver_pin

    L, N = 20.0, 201
    dx = 2 * L / (N - 1)
    centers = [-L + i * dx for i in range(N)]

    def claim(claim_id: str, D: float, var0: float, steps: int) -> SpatialClaim:
        dt = 0.2 * dx * dx / D
        return SpatialClaim(
            claim_id=claim_id,
            quantity="diffused concentration profile",
            initial=tuple(gaussian_profile(centers, mass=10.0, variance=var0)),
            reference=tuple(
                gaussian_profile(centers, mass=10.0, variance=var0 + 2 * D * steps * dt)
            ),
            source_location="closed-form",
            diffusivity=D,
            dx=dx,
            dt=dt,
            steps=steps,
        )

    cert = certify_spatial(
        paper=PaperIdentity(title="three profiles", doi=""),
        engine_pin=solver_pin(),
        claims=[claim("a", 1.0, 1.0, 200), claim("b", 2.0, 1.5, 160)],
    )
    boundary = [a for a in cert.assumptions if a.id.startswith("spatial-boundary-")]
    assert len(boundary) == 2, "one assumption per judged claim"
    assert len({a.basis for a in boundary}) == 1, "and one question between them"

    report = queue_report([(certificate_digest(cert), cert)])
    items = [i for i in report["engine_limits"] if "boundary" in i["question"]]
    assert len(items) == 1, "two claims, one solver limitation, one item"
    assert items[0]["impact"] == 1, "one certificate carries it"

    # The measurement is still published, per claim, where the discretization is.
    protocols = [a.protocol for a in cert.assessments]
    assert all("zero-flux (Neumann) boundaries" in p for p in protocols)
    assert all("that wall costs this claim" in p for p in protocols)
    # Two different claims, two different measured costs — which is why it cannot be in the basis.
    assert protocols[0] != protocols[1]


def test_the_reported_cost_is_the_worst_alternative_not_a_convenient_one() -> None:
    """Found by mutation: replacing "the alternative that moves the judged distance most" with
    "the alphabetically first" survived the whole suite. Nothing checked which one is reported, and
    reporting the *least* moving wall would understate what the choice costs — the one direction a
    number about an assumption must never err in.
    """
    from reprolith.oracle import normalized_curve_distance
    from reprolith.spatial import (
        SpatialClaim,
        boundary_sensitivity,
        diffuse_1d,
        gaussian_profile,
    )

    # A domain narrow enough for the walls to matter: the profile is wide against the box, so the
    # three boundaries genuinely disagree and there is a worst one to pick.
    length, points = 3.0, 121
    dx = 2 * length / (points - 1)
    centers = [-length + i * dx for i in range(points)]
    diffusivity, steps = 1.0, 900
    dt = 0.2 * dx * dx / diffusivity
    initial = tuple(gaussian_profile(centers, mass=10.0, variance=1.0))
    reference = tuple(
        gaussian_profile(centers, mass=10.0, variance=1.0 + 2 * diffusivity * steps * dt)
    )
    claim = SpatialClaim(
        claim_id="narrow", quantity="profile", initial=initial, reference=reference,
        source_location="closed-form", diffusivity=diffusivity, dx=dx, dt=dt, steps=steps,
    )

    def distance(boundary: str) -> float:
        return normalized_curve_distance(
            reference,
            diffuse_1d(
                initial, diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, boundary=boundary
            ),
        )

    judged = distance("no-flux")
    alternatives = {name: distance(name) for name in ("dirichlet", "periodic")}
    # The premise: on this domain the two alternatives really do differ, or the check is vacuous.
    assert abs(alternatives["dirichlet"] - alternatives["periodic"]) > 1e-6

    measured = boundary_sensitivity(claim)
    assert measured is not None
    expected = max(alternatives, key=lambda name: abs(alternatives[name] - judged))
    assert measured["worst_alternative"] == expected
    assert measured["moved_by"] == pytest.approx(abs(alternatives[expected] - judged))
    assert measured["moved_by"] >= abs(alternatives[
        "dirichlet" if expected == "periodic" else "periodic"
    ] - judged)


def test_a_symmetric_profile_centred_in_the_box_makes_wrapping_and_mirroring_identical() -> None:
    """A physical identity that checks the two implementations against each other where they must
    agree: for a profile symmetric about the centre of the domain, what leaves one end under
    periodicity is exactly what the mirror reflects back, so the two runs coincide to floating
    point. It also says why `dirichlet` is always the worst alternative on these claims — removing
    mass changes a profile more than rearranging it.
    """
    from reprolith.spatial import diffuse_1d, gaussian_profile

    length, points = 3.0, 121
    dx = 2 * length / (points - 1)
    centers = [-length + i * dx for i in range(points)]
    dt = 0.2 * dx * dx / 1.0
    initial = tuple(gaussian_profile(centers, mass=10.0, variance=1.0))
    run = lambda b: diffuse_1d(  # noqa: E731
        initial, diffusivity=1.0, dx=dx, dt=dt, steps=900, boundary=b
    )
    assert max(abs(a - b) for a, b in zip(run("no-flux"), run("periodic"))) < 1e-12
    # And the absorbing wall is genuinely different, so this is not three names for one run.
    assert max(abs(a - b) for a, b in zip(run("no-flux"), run("dirichlet"))) > 1e-3
