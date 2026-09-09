"""The objective of an FBA optimum is "well-defined regardless of alternate optima" — measured.

That sentence appears twice in `reprolith.fba`, once for the objective value and once for the
essential set, and it is what lets this class publish a growth rate as a reproduction at all: an LP
with alternate optima has many flux distributions attaining the optimum, and if the *number* moved
among them, a certificate would be reporting whichever vertex the solver happened to reach.

It was an annotation used as if it were a check — true, load-bearing, and never run. This runs it,
and it runs it on the case the claim is actually about: a network with genuine alternate optima,
confirmed as such by flux variability, rather than only on a model that happens not to be
degenerate. A measurement that could not have failed measures nothing.

The lever is a **permutation of the reaction ordering**. It relabels the columns of the LP without
changing the feasible set or the objective, so the simplex may land on a different optimal vertex —
which is exactly the freedom "regardless of alternate optima" is a claim about. The objective value
must not move with it.
"""

from __future__ import annotations

import random
from pathlib import Path

from reprolith.fba import flux_variability, solve_objective
from reprolith.sbml import ingest_fbc_sbml

_ROOT = Path(__file__).resolve().parents[1]

#: A -> B by two parallel routes of equal yield, then B -> biomass. Any split between the routes
#: attains the same objective, so the optimal *vertex* is not unique while the optimal *value* is.
_S = ((1.0, -1.0, -1.0, 0.0), (0.0, 1.0, 1.0, -1.0))
_OBJECTIVE = (0.0, 0.0, 0.0, 1.0)
_LOWER = (0.0, 0.0, 0.0, 0.0)
_UPPER = (10.0, 10.0, 10.0, 1000.0)
_ROUTE_A = 1


def _permuted(order: list[int]) -> float:
    return solve_objective(
        [[row[j] for j in order] for row in _S],
        [_OBJECTIVE[j] for j in order],
        [_LOWER[j] for j in order],
        [_UPPER[j] for j in order],
    )


def test_the_toy_network_really_does_have_alternate_optima() -> None:
    """Otherwise the test below measures a uniqueness nothing was threatening.

    Flux variability at the full optimum: route A can carry anything from nothing to the whole
    flux, which is the degeneracy the objective's uniqueness has to survive.
    """
    (low, high), = flux_variability(
        _S, _OBJECTIVE, _LOWER, _UPPER, fraction_of_optimum=1.0, reactions=[_ROUTE_A]
    )
    assert low == 0.0
    assert high == 10.0


def test_the_objective_does_not_move_among_those_optima() -> None:
    base = solve_objective(_S, _OBJECTIVE, _LOWER, _UPPER)
    assert base == 10.0
    for seed in range(20):
        order = list(range(len(_OBJECTIVE)))
        random.Random(seed).shuffle(order)
        # Exactly equal, not approximately: the claim in the docstring is that the value is
        # well-defined, and a tolerance here would be conceding that it drifts a little.
        assert _permuted(order) == base


def test_it_holds_on_the_model_this_repository_ships() -> None:
    """The toy proves the principle; the shipped model is the one a certificate rests on.

    E. coli core, whose growth rate is the constraint-based worked example: 1.3e-16 relative at
    worst across five permutations — machine precision, against the 5% that separates a pass from a
    failure for this class.
    """
    model = ingest_fbc_sbml(
        (_ROOT / "datasets" / "constraint_based" / "e_coli_core.xml").read_text(encoding="utf-8")
    )
    base = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    worst = 0.0
    for seed in range(5):
        order = list(range(len(model.objective)))
        random.Random(seed).shuffle(order)
        value = solve_objective(
            [[row[j] for j in order] for row in model.stoichiometry],
            [model.objective[j] for j in order],
            [model.lower[j] for j in order],
            [model.upper[j] for j in order],
        )
        worst = max(worst, abs(value - base) / abs(base))
    assert worst < 1e-12
