"""Validate the FBA dual — shadow prices and reduced costs — against the primal (roadmap #3).

The FROG fingerprint reads a flux-balance optimum from the primal side (objective, flux ranges,
deletions). Its economic dual — how much each metabolite and each capacity limit is worth at the
optimum — is a separate, standard output (COBRApy exposes it as ``shadow_prices`` /
``reduced_costs``). :func:`reprolith.shadow_prices` computes it from the LP's dual variables.

These tests prove the returned duals are the true sensitivities of the *maximized* objective, and
they do it non-circularly: the reference is the derivative of the primal optimum estimated by
re-solving perturbed LPs (numerical differentiation), which shares nothing with reading scipy's
dual marginals. Definition, sign, and complementary slackness are all pinned this way. Needs the
optional ``fba`` extra (scipy).
"""

from __future__ import annotations

import pytest

pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")

from reprolith import shadow_prices, solve_objective  # noqa: E402
from scipy.optimize import linprog  # noqa: E402

# A small metabolic network with a nontrivial dual. Metabolites A, B; reactions:
#   r1: import A          (0..10, the limiting substrate)
#   r2: A -> B            (0..inf)
#   r3: B -> biomass      (0..inf, the objective)
#   r4: import B directly (0..2, a secondary limited source)
# Steady state forces r2 = r1 and r3 = r2 + r4, so the optimum is r1_max + r4_max = 12, with both
# imports pinned at their upper bounds and r2, r3 in the interior.
_S = [[1.0, -1.0, 0.0, 0.0], [0.0, 1.0, -1.0, 1.0]]
_OBJ = [0.0, 0.0, 1.0, 0.0]
_LOWER = [0.0, 0.0, 0.0, 0.0]
_UPPER: list[float | None] = [10.0, None, None, 2.0]

_EPS = 1e-6


def _optimum_with_net_production(net: list[float]) -> float:
    """Independent reference: the maximized objective when metabolite i must net-produce ``net[i]``.

    Solves the same LP with a nonzero right-hand side on the mass-balance constraints, using
    scipy directly. Differentiating this in ``net`` gives each metabolite's shadow price without
    ever touching the dual marginals the production code reads.
    """
    result = linprog(
        c=[-x for x in _OBJ],
        A_eq=_S,
        b_eq=net,
        bounds=list(zip(_LOWER, _UPPER)),
        method="highs",
    )
    assert result.success
    return float(-result.fun)


def _optimum_with_bound(reaction: int, new_upper: float) -> float:
    """Independent reference: the optimum when one reaction's upper bound is moved to ``new_upper``."""
    upper = list(_UPPER)
    upper[reaction] = new_upper
    return solve_objective(_S, _OBJ, _LOWER, upper)


def test_metabolite_shadow_prices_are_the_primal_optimum_sensitivity() -> None:
    # Shadow price of metabolite i is dZ*/db_i. Compare each returned price to a central finite
    # difference of the primal optimum in that metabolite's net-production requirement.
    prices = shadow_prices(_S, _OBJ, _LOWER, _UPPER).metabolites
    for i in range(len(_S)):
        plus = _optimum_with_net_production([_EPS if k == i else 0.0 for k in range(len(_S))])
        minus = _optimum_with_net_production([-_EPS if k == i else 0.0 for k in range(len(_S))])
        finite_difference = (plus - minus) / (2 * _EPS)
        assert prices[i] == pytest.approx(finite_difference, abs=1e-4)


def test_reaction_reduced_costs_match_the_bound_sensitivity() -> None:
    # Reduced cost of a reaction at its bound is dZ*/d(bound). r1 and r4 sit at their upper bounds,
    # so relaxing either raises the optimum by exactly its reduced cost.
    reduced = shadow_prices(_S, _OBJ, _LOWER, _UPPER).reactions
    base = solve_objective(_S, _OBJ, _LOWER, _UPPER)
    for reaction, bound in ((0, 10.0), (3, 2.0)):
        finite_difference = (_optimum_with_bound(reaction, bound + _EPS) - base) / _EPS
        assert reduced[reaction] == pytest.approx(finite_difference, abs=1e-4)
        assert reduced[reaction] > 0  # a binding limit has strictly positive value here


def test_complementary_slackness_zeroes_interior_reactions() -> None:
    # r2 and r3 carry flux strictly inside their bounds, so relaxing those bounds cannot help and
    # their reduced cost must be exactly zero — the complementary-slackness half of LP duality.
    reduced = shadow_prices(_S, _OBJ, _LOWER, _UPPER).reactions
    assert reduced[1] == pytest.approx(0.0, abs=1e-9)
    assert reduced[2] == pytest.approx(0.0, abs=1e-9)


def test_strong_duality_reconstructs_the_optimum_from_the_binding_bounds() -> None:
    # LP strong duality: with a zero right-hand side the primal optimum equals the value of the
    # binding capacity limits, sum over reactions of reduced_cost * bound. Reconstructing Z* from
    # the dual alone is the theorem's headline consequence.
    reduced = shadow_prices(_S, _OBJ, _LOWER, _UPPER).reactions
    bounds = [10.0, 0.0, 0.0, 2.0]  # only the binding upper bounds contribute
    dual_value = sum(rc * b for rc, b in zip(reduced, bounds))
    assert dual_value == pytest.approx(solve_objective(_S, _OBJ, _LOWER, _UPPER))


def test_infeasible_problem_raises() -> None:
    from reprolith import InfeasibleFba

    # Force r1 to import at least 5 while capping the biomass drain at 1: mass balance on A/B is
    # then unsatisfiable, so the dual is undefined and the solve must raise, not return a number.
    lower = [5.0, 0.0, 0.0, 0.0]
    upper: list[float | None] = [10.0, 1.0, 1.0, 0.0]
    with pytest.raises(InfeasibleFba):
        shadow_prices(_S, _OBJ, lower, upper)
