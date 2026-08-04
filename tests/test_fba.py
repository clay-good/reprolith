"""The constraint-based (FBA) oracle: LP objective reproduction (spec: constraint-based-class).

Needs the optional ``fba`` extra (scipy); the module skips without it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    Attribution,
    EnginePin,
    FailureMode,
    Fault,
    InfeasibleFba,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    build_certificate,
    essentiality_agreement,
    flux_variability,
    judge_objective,
    reaction_essentiality,
    solve_objective,
)

# A tiny network: v_in -> A -> v_out(objective). Steady state on A means v_in = v_out; the
# objective (v_out) is capped by v_in's upper bound of 8, so the optimum is 8.
_S = [[1.0, -1.0]]  # one metabolite A, two reactions (v_in, v_out)
_OBJECTIVE = [0.0, 1.0]  # maximize v_out
_LOWER = [0.0, 0.0]
_UPPER = [8.0, None]


def test_solves_the_objective_optimum() -> None:
    assert solve_objective(_S, _OBJECTIVE, _LOWER, _UPPER) == pytest.approx(8.0)


def test_reported_objective_reproduces_and_perturbed_fails() -> None:
    good = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=8.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
    )
    assert good.verdict is Verdict.REPRODUCED

    bad = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=4.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
        attribution=Attribution(mode=FailureMode.MANUSCRIPT_ERROR, implicated="reported objective",
                                fault=Fault.MANUSCRIPT),
    )
    assert bad.verdict is Verdict.FAILED


def test_fba_assessment_feeds_the_certificate() -> None:
    assessment = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=8.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
    )
    cert = build_certificate(
        paper=PaperIdentity(title="An FBA model"),
        engine_pin=EnginePin(engine="scipy-highs", version="1.x"),
        assessments=[assessment],
    )
    assert cert.overall is OverallVerdict.REPRODUCED  # the shared certificate contract is reused


def test_infeasible_problem_raises() -> None:
    # Force infeasibility: v_out lower-bounded above what v_in can supply.
    with pytest.raises(InfeasibleFba):
        solve_objective(_S, _OBJECTIVE, [0.0, 20.0], [8.0, None])


def test_both_reactions_are_essential() -> None:
    # In v_in -> A -> v_out, knocking out either reaction starves the objective, so both
    # reactions are essential.
    assert reaction_essentiality(_S, _OBJECTIVE, _LOWER, _UPPER) == frozenset({0, 1})


def test_a_redundant_reaction_is_not_essential() -> None:
    # Add a second inflow v_in2 -> A. Now either inflow alone can feed v_out (its bound is 8),
    # so neither inflow is essential on its own; only the single outflow remains essential.
    stoich = [[1.0, 1.0, -1.0]]  # v_in, v_in2, v_out
    objective = [0.0, 0.0, 1.0]
    lower = [0.0, 0.0, 0.0]
    upper: list[float | None] = [8.0, 8.0, None]
    assert reaction_essentiality(stoich, objective, lower, upper) == frozenset({2})


def test_essentiality_agreement_scores_overlap() -> None:
    assert essentiality_agreement(frozenset({0, 1}), frozenset({0, 1})) == pytest.approx(1.0)
    assert essentiality_agreement(frozenset({0, 1}), frozenset({0, 2})) == pytest.approx(1 / 3)
    assert essentiality_agreement(frozenset(), frozenset()) == pytest.approx(1.0)


def test_fva_pins_a_forced_flux() -> None:
    # In the linear chain, steady state forces v_in = v_out = 8 at the optimum, so FVA reports
    # each as a single pinned value — a claim on either flux could be certified exactly.
    ranges = flux_variability(_S, _OBJECTIVE, _LOWER, _UPPER)
    assert ranges[0] == pytest.approx((8.0, 8.0))
    assert ranges[1] == pytest.approx((8.0, 8.0))


def test_fva_reports_the_alternate_optima_range() -> None:
    # v_in -> A, then two parallel routes A -> B (r1, r2), then B -> v_out (objective). The
    # optimum (10) is achieved by any split r1 + r2 = 10, so FVA honestly reports each parallel
    # flux as the whole interval [0, 10] rather than committing to one ambiguous value.
    stoich = [
        [1.0, -1.0, -1.0, 0.0],  # A: v_in - r1 - r2
        [0.0, 1.0, 1.0, -1.0],  # B: r1 + r2 - v_out
    ]
    objective = [0.0, 0.0, 0.0, 1.0]
    lower = [0.0, 0.0, 0.0, 0.0]
    upper: list[float | None] = [10.0, None, None, None]

    ranges = flux_variability(stoich, objective, lower, upper)
    assert ranges[0] == pytest.approx((10.0, 10.0))  # inflow forced
    assert ranges[1] == pytest.approx((0.0, 10.0))  # parallel route — free within the optimum
    assert ranges[2] == pytest.approx((0.0, 10.0))
    assert ranges[3] == pytest.approx((10.0, 10.0))  # objective outflow forced
