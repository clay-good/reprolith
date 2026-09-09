"""A claim whose source states an *unbounded* domain, run on a grid that has edges.

This is the last item the verification queue listed as an alternative a reader was told about and
could not have: "an unbounded domain (not implemented, so not measured)". It sat under three
standing certificates whose reference is the closed-form Gaussian — a free-space solution — so the
one domain those claims actually assert was the one the engine could not honour.

An infinite grid cannot be run, so the claim is neither trusted nor refused. Two of the edge rules
this solver has **bracket** free space for a diffusive claim: a zero-flux wall reflects back
everything that reaches it, a Dirichlet-at-zero wall absorbs it, and the free-space solution — which
lets it leave and never return — lies between. The distance between those runs therefore bounds how
far either sits from the unbounded one, and the claim is judged only when that bound is a small
fraction of its own pass tolerance. The third wall this solver runs, periodic, brackets nothing and
is measured anyway: a bound taken over more walls is only ever larger.

The test that matters most here is the last one. The first version of this rule compared the wall's
effect to the claim's own residual, and a domain small enough for the wall to reflect a third of
the mass back *passed* it — the residual was large because the wall had wrecked the profile, so the
wall looked small against it. A statement about the domain has to be tested against the domain.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from reprolith import (
    UNBOUNDED,
    OverallVerdict,
    PaperIdentity,
    SpatialClaim,
    Verdict,
    certify_spatial,
    gaussian_profile,
)
from reprolith.spatial import (
    UNBOUNDED_WALL_BUDGET,
    solver_pin,
    unbounded_is_honoured,
    wall_bracket,
)

_D, _DIFFUSION_NUMBER = 1.0, 0.2


def _claim(half_width: float, points: int, *, steps: int = 1000, variance: float = 1.0,
           mass: float = 10.0, boundary: str | None = UNBOUNDED) -> SpatialClaim:
    """A Gaussian diffusing on a domain of the given half-width, judged against free space."""
    dx = 2 * half_width / (points - 1)
    centers = tuple(-half_width + i * dx for i in range(points))
    dt = _DIFFUSION_NUMBER * dx * dx / _D
    return SpatialClaim(
        claim_id=f"L{half_width}", quantity="diffused concentration profile",
        initial=tuple(gaussian_profile(centers, mass=mass, variance=variance)),
        reference=tuple(gaussian_profile(centers, mass=mass, variance=variance + 2 * _D * steps * dt)),
        source_location="closed-form", diffusivity=_D, dx=dx, dt=dt, steps=steps,
        boundary=boundary,
    )


def _certify(claim: SpatialClaim):
    return certify_spatial(
        paper=PaperIdentity(title="a Gaussian on an unbounded line", doi=""),
        engine_pin=solver_pin(), claims=[claim],
    )


# --- the field itself -------------------------------------------------------------------------

def test_unbounded_is_not_an_edge_rule_this_solver_runs() -> None:
    """It is a statement about the source, so it never reaches the stepper as a wall."""
    claim = _claim(20.0, 201)
    assert claim.states_unbounded
    assert claim.wall == "no-flux"          # a grid has edges whatever the paper says
    assert not claim.wall_is_reprolith_s    # but the domain is the source's, so nothing is assumed


def test_an_unknown_boundary_is_still_refused() -> None:
    with pytest.raises(ValueError, match="unbounded"):
        _claim(20.0, 201, boundary="infinite")


# --- the bracket ------------------------------------------------------------------------------

def test_the_bracket_shrinks_as_the_domain_widens() -> None:
    """The measured statistic on five domains: monotone once the walls stop dominating, and
    spanning six orders between the narrowest and the one this class ships.

    It is deliberately *not* asserted monotone at the narrow end. At a half-width of 3 the absorbing
    wall has taken nearly all the mass and the reflecting wall has kept all of it, so both profiles
    are far from free space and the normalized distance between them saturates below what it reads
    at 5. That is a bound behaving like a bound — every one of these is orders above the budget,
    which is the only thing the verdict turns on.
    """
    bounds = {L: wall_bracket(_claim(L, points))
              for L, points in ((3.0, 31), (5.0, 51), (7.0, 71), (10.0, 101), (20.0, 201))}
    assert all(b is not None for b in bounds.values())
    assert bounds[5.0] > bounds[7.0] > bounds[10.0] > bounds[20.0]
    assert bounds[3.0] > 0.1 and bounds[20.0] < 1e-5


def test_the_bracket_is_measured_between_the_walls_and_not_against_the_reference() -> None:
    """Change only what the claim reports, and the bound must not move.

    This is the defect the first version had, stated as a test: keyed on the residual, a claim
    reporting nonsense would have looked *better* honoured than one reporting the right answer.
    """
    honest = _claim(10.0, 101)
    wrong = replace(honest, reference=tuple(0.0 for _ in honest.reference))
    assert wall_bracket(honest) == wall_bracket(wrong)


# --- what it does to a verdict ----------------------------------------------------------------

def test_a_wide_domain_is_judged_and_carries_no_assumption() -> None:
    cert = _certify(_claim(20.0, 201))
    content = cert.content()
    assert content["overall"] == OverallVerdict.REPRODUCED.value
    assert content["assumptions"] == []
    assert content["assessments"][0]["verdict"] == Verdict.REPRODUCED.value


def test_the_protocol_reports_the_bracket_it_was_judged_under() -> None:
    protocol = _certify(_claim(20.0, 201)).content()["assessments"][0]["protocol"]
    measured = unbounded_is_honoured(_claim(20.0, 201))
    assert "unbounded domain, verified rather than assumed" in protocol
    assert f"{measured['wall_bracket']:.3e}" in protocol
    assert "the source's unbounded domain does not have" in protocol


def test_a_domain_too_narrow_abstains_with_the_number_that_made_it_abstain() -> None:
    """The case the first rule got wrong: here the wall reflects mass back, and it is caught."""
    narrow = _claim(3.0, 31)
    measured = unbounded_is_honoured(narrow)
    assert measured is not None and not measured["honoured"]
    assert measured["wall_bracket"] > measured["budget"]

    assessment = _certify(narrow).content()["assessments"][0]
    assert assessment["verdict"] == Verdict.NOT_EVALUABLE.value
    reason = assessment["root_cause"]
    assert f"{measured['wall_bracket']:.3e}" in reason
    assert "run it on a wider grid, or state the wall the source used" in reason


def test_a_narrow_domain_reproduces_when_it_states_its_wall_instead() -> None:
    """The abstention is about the *unbounded* statement, not about the grid being small.

    The same run, told the truth about which wall its source used, is judged normally — so the
    refusal above is a refusal to substitute, and not this class declining small domains.
    """
    stated = _claim(3.0, 31, boundary="no-flux")
    assert _certify(stated).content()["assessments"][0]["verdict"] != Verdict.NOT_EVALUABLE.value


def test_a_claim_sitting_on_its_verdict_line_is_not_honoured_by_a_small_bound() -> None:
    """The gap a single budget leaves, and the sentence it made an overstatement.

    A bound under a tenth of the pass *width* is not a bound under a tenth of what separates *this*
    claim from its threshold. A claim landing a hair from the line is decided by an error far under
    the whole tolerance — small and decisive at once, which is exactly what this rule exists to
    prevent. So the bound is tested against the margin as well.

    Built by shifting the reference until the judged distance lands microscopically past the pass
    line: the grid is the shipped one, the bracket is the shipped 2.2e-06, and only the margin
    moves.
    """
    from reprolith.spatial import diffuse_1d

    base = _claim(20.0, 201)
    predicted = list(diffuse_1d(
        base.initial, diffusivity=base.diffusivity, dx=base.dx, dt=base.dt, steps=base.steps,
    ))
    peak = max(predicted)
    comfortable = unbounded_is_honoured(
        replace(base, reference=tuple(v + 0.05 * peak for v in predicted))
    )
    on_the_line = unbounded_is_honoured(
        replace(base, reference=tuple(v + 0.100002 * peak for v in predicted))
    )
    assert comfortable is not None and on_the_line is not None
    # Same grid, same wall, same bracket — only the claim's distance from its threshold differs.
    assert comfortable["wall_bracket"] == on_the_line["wall_bracket"]
    assert comfortable["honoured"] and not on_the_line["honoured"]
    assert on_the_line["wall_bracket"] > on_the_line["margin_budget"]


def test_the_budget_test_is_what_stops_a_wrecked_profile() -> None:
    """The two conditions are required together, which is what makes reading the residual safe.

    The margin test reads the claim's own distance, which is the quantity that made the first
    version of this rule circular — so it is never the whole test. What refuses a domain whose wall
    has reflected a third of the mass back is the budget, measured between runs and untouchable by
    the residual. Both are checked here, on the narrowest grid: the wall's effect is orders above
    the budget, and it is the budget the verdict turns on.
    """
    narrow = unbounded_is_honoured(_claim(3.0, 31))
    assert narrow is not None
    assert narrow["wall_bracket"] > narrow["budget"]
    assert not narrow["honoured"]
    # And the margin the residual offers is no defence: on this grid it is large *because* the wall
    # wrecked the profile, and it buys nothing, because both tests must pass.
    assert narrow["margin_to_a_verdict_line"] > 1.0


def test_the_budget_is_a_fraction_of_the_pass_tolerance_and_not_a_free_number() -> None:
    measured = unbounded_is_honoured(_claim(20.0, 201))
    assert measured["budget"] == pytest.approx(UNBOUNDED_WALL_BUDGET * measured["pass_within"])
    assert measured["wall_bracket"] < measured["budget"] / 1000  # the shipped grid, with room


def test_an_unrunnable_claim_abstains_for_its_own_reason_and_not_the_wall_s() -> None:
    """An unstable discretization is the claim's problem; the bracket reports that it cannot say."""
    claim = _claim(20.0, 201)
    unstable = replace(claim, dt=claim.dt * 10)
    assert wall_bracket(unstable) is None
    assert unbounded_is_honoured(unstable) is None
    assessment = _certify(unstable).content()["assessments"][0]
    assert assessment["verdict"] == Verdict.NOT_EVALUABLE.value


def test_free_space_is_what_the_reference_actually_is() -> None:
    """Sanity: the reference these claims are judged against is the infinite-domain solution.

    Nothing in the engine depends on this, but the whole slice does — if the reported profile were
    a finite-domain solution, stating `unbounded` would be the wrong claim to make.
    """
    L, points, steps = 20.0, 201, 1000
    claim = _claim(L, points, steps=steps)
    elapsed = steps * claim.dt
    peak = max(claim.reference)
    assert peak == pytest.approx(10.0 / math.sqrt(2 * math.pi * (1.0 + 2 * _D * elapsed)), rel=1e-12)


def test_a_wavelength_claim_cannot_state_an_unbounded_domain_and_says_why() -> None:
    """The opposite case, and the refusal explains the difference rather than listing two names.

    A wall far from the mass leaves a profile alone, which is why an unbounded profile claim can be
    measured. A wavelength is the quantity the wall *creates*: the measurable values are 2L/m under
    zero flux and L/m under periodicity, so a domain with no walls has no mode set for the reported
    number to be one of. Refusing it is right; refusing it with only a list of accepted strings
    would send somebody who read the profile page looking for a bug.
    """
    from reprolith import PatternClaim

    with pytest.raises(ValueError, match="no mode set for the reported number to be one of"):
        PatternClaim(
            claim_id="w", quantity="Turing pattern wavelength", kinetics="schnakenberg",
            reported=16.0, source_location="Fig 2", a=0.1, b=0.9, du=1.0, dv=40.0,
            length=50.0, points=201, dt=1e-4, steps=6000, confirm_steps=2000,
            boundary=UNBOUNDED,
        )
