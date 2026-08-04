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
    judge_objective,
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
