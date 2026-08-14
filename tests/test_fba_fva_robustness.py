"""Flux variability holds the objective at its optimum, which is a numerical knife-edge.

At ``fraction_of_optimum`` == 1.0 the floor equals the separately-recomputed optimum, so
``objective . v >= optimum`` sits exactly on the feasible region's boundary. A reaction with wide
placeholder bounds makes that LP badly scaled, and a solver whose presolve rounds a hair more
aggressively (HiGHS builds differ across platforms) can wrongly call an otherwise-solvable reaction
infeasible — which reddened CI on one Python/scipy build but not another. These tests pin the
per-reaction fallback that rescues the knife-edge case, using a stub solver so they run everywhere,
independent of the installed LP backend.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from reprolith.fba import _extreme_at_optimum

_ARGS = {
    "select": [1.0, 0.0],
    "a_ub": [[-1.0, 0.0]],
    "floor": 0.7,
    "a_eq": [[1.0, -1.0]],
    "b_eq": [0.0],
    "bounds": [(-1e6, 1e6), (-1e6, 1e6)],
    "optimum": 0.7,
}


def _call(linprog: Any) -> float | None:
    return _extreme_at_optimum(linprog, **_ARGS)


def test_solvable_reaction_takes_the_first_solve_and_never_relaxes() -> None:
    calls: list[float] = []

    def linprog(**kwargs: Any) -> Any:
        calls.append(kwargs["b_ub"][0])
        return SimpleNamespace(success=True, fun=0.005819627)

    assert _call(linprog) == 0.005819627
    # A single solve at the exact floor; no relaxed retry, so a feasible reaction never drifts.
    assert calls == [-0.7]


def test_knife_edge_infeasible_reaction_is_rescued_by_a_relaxed_retry() -> None:
    calls: list[float] = []

    def linprog(**kwargs: Any) -> Any:
        floor = -kwargs["b_ub"][0]
        calls.append(floor)
        # The exact-optimum solve tips infeasible; the slightly relaxed retry succeeds.
        if floor >= 0.7:
            return SimpleNamespace(success=False, fun=None, message="infeasible")
        return SimpleNamespace(success=True, fun=0.005819627)

    assert _call(linprog) == 0.005819627
    assert len(calls) == 2
    # The retry floor is relaxed below the optimum, but by less than the reported flux magnitude.
    assert calls[1] < 0.7
    assert 0.7 - calls[1] < 1e-5


def test_genuinely_infeasible_reaction_returns_none_even_after_the_retry() -> None:
    def linprog(**kwargs: Any) -> Any:
        return SimpleNamespace(success=False, fun=None, message="infeasible")

    assert _call(linprog) is None
