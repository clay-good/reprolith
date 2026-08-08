"""Parsimonious FBA (pFBA): the minimal-total-flux tie-break among alternate optima.

Plain FBA fixes the objective but usually leaves the flux vector ambiguous, so `judge_flux` must
abstain on any reaction the optimum does not pin. pFBA (Lewis et al. 2010) resolves that by choosing
the optimal vector with the least total flux Σ|vᵢ| — the standard parsimony assumption. These tests
check the solver against analytically known minimal-flux solutions, non-circularly: the reference is
the flux distribution the minimization must select, not a number this engine chose. Needs the ``fba``
extra (scipy).
"""

from __future__ import annotations

import pytest

pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    InfeasibleFba,
    flux_variability,
    parsimonious_fluxes,
    solve_objective,
)

# Two routes from A to B: a direct one (r_short) and a detour through C (r_long1, r_long2). Both
# carry the same objective flux, but the detour spends flux on two reactions instead of one, so the
# minimal-total-flux solution must send everything through the short route.
#   metabolites A, B, C; reactions r_in, r_short, r_long1, r_long2, r_out(objective)
_S = [
    [1.0, -1.0, -1.0, 0.0, 0.0],  # A: r_in - r_short - r_long1
    [0.0, 1.0, 0.0, 1.0, -1.0],   # B: r_short + r_long2 - r_out
    [0.0, 0.0, 1.0, -1.0, 0.0],   # C: r_long1 - r_long2
]
_OBJ = [0.0, 0.0, 0.0, 0.0, 1.0]
_LOWER = [0.0, 0.0, 0.0, 0.0, 0.0]
_UPPER: list[float | None] = [10.0, None, None, None, None]
_R_SHORT, _R_LONG1, _R_LONG2, _R_OUT = 1, 2, 3, 4


def test_pfba_selects_the_short_route_and_preserves_the_optimum() -> None:
    solution = parsimonious_fluxes(_S, _OBJ, _LOWER, _UPPER)
    # The optimum is untouched, and the detour carries no flux — the short route is uniquely chosen.
    assert solution.objective_value == pytest.approx(10.0)
    assert solution.fluxes[_R_OUT] == pytest.approx(10.0)
    assert solution.fluxes[_R_SHORT] == pytest.approx(10.0)
    assert solution.fluxes[_R_LONG1] == pytest.approx(0.0, abs=1e-9)
    assert solution.fluxes[_R_LONG2] == pytest.approx(0.0, abs=1e-9)


def test_pfba_total_flux_is_the_analytic_minimum() -> None:
    solution = parsimonious_fluxes(_S, _OBJ, _LOWER, _UPPER)
    # Short route: |r_in| + |r_short| + |r_out| = 10 + 10 + 10 = 30. The detour would spend 40
    # (r_long1 + r_long2 = 20 instead of r_short = 10), so 30 is the minimum.
    assert solution.total_flux == pytest.approx(30.0)
    # And it really is the total absolute flux of the returned vector.
    assert solution.total_flux == pytest.approx(sum(abs(v) for v in solution.fluxes))


def test_pfba_resolves_an_ambiguity_that_fva_leaves_open() -> None:
    # FVA reports the short-route flux as the whole interval [0, 10] — the optimum does not pin it,
    # so judge_flux would abstain. pFBA commits to a single, motivated value. This is exactly the
    # gap pFBA fills.
    interval = flux_variability(_S, _OBJ, _LOWER, _UPPER)[_R_SHORT]
    assert interval[0] == pytest.approx(0.0) and interval[1] == pytest.approx(10.0)
    assert interval[1] - interval[0] > 1e-6  # genuinely unpinned
    assert parsimonious_fluxes(_S, _OBJ, _LOWER, _UPPER).fluxes[_R_SHORT] == pytest.approx(10.0)


def test_pfba_flux_vector_is_a_steady_state() -> None:
    fluxes = parsimonious_fluxes(_S, _OBJ, _LOWER, _UPPER).fluxes
    for row in _S:
        assert sum(coeff * v for coeff, v in zip(row, fluxes)) == pytest.approx(0.0, abs=1e-9)


def test_pfba_recovers_the_unique_fluxes_of_a_pinned_chain() -> None:
    # A linear chain has no alternate optima: v_in = v_out = 8 is forced, and pFBA must return
    # exactly that — the minimal-flux solution of a unique optimum is the optimum itself.
    chain_s = [[1.0, -1.0]]
    chain_obj = [0.0, 1.0]
    chain_lower = [0.0, 0.0]
    chain_upper: list[float | None] = [8.0, None]
    solution = parsimonious_fluxes(chain_s, chain_obj, chain_lower, chain_upper)
    assert solution.objective_value == pytest.approx(solve_objective(chain_s, chain_obj, chain_lower, chain_upper))
    assert solution.fluxes == pytest.approx((8.0, 8.0))
    assert solution.total_flux == pytest.approx(16.0)


def test_pfba_raises_on_an_infeasible_problem() -> None:
    lower = [5.0, 0.0, 0.0, 0.0, 0.0]  # force r_in >= 5 while capping the drain makes A unbalanceable
    upper: list[float | None] = [10.0, 1.0, 0.0, 0.0, 0.0]
    with pytest.raises(InfeasibleFba):
        parsimonious_fluxes(_S, _OBJ, lower, upper)


def test_pfba_preserves_the_optimum_on_the_real_e_coli_core_model() -> None:
    # Beyond the toy networks: on the real genome-scale-ingested E. coli core model, pFBA must still
    # hit the independently-known aerobic growth rate (0.873922 /h) and return a genuine steady
    # state. Non-circular: the growth rate is the documented value, not one this engine picked.
    from pathlib import Path

    pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
    from reprolith.sbml import ingest_fbc_sbml

    model_path = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
    model = ingest_fbc_sbml(model_path.read_text(encoding="utf-8"))
    solution = parsimonious_fluxes(model.stoichiometry, model.objective, model.lower, model.upper)
    assert solution.objective_value == pytest.approx(0.873922, rel=1e-4)
    for row in model.stoichiometry:
        assert sum(coeff * v for coeff, v in zip(row, solution.fluxes)) == pytest.approx(0.0, abs=1e-6)
