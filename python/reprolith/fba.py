"""Constraint-based (FBA) reproduction: the optimization oracle (spec: constraint-based-class).

Flux-balance analysis checks a different kind of claim than the PK/PD curve oracle: not "does
the model regenerate a time course" but "does the model's optimization reproduce the reported
outcome" — the objective value under a steady-state, capacity-constrained network. This module
adds only that new comparison method; it reuses the shared contracts, returning the same
:class:`~reprolith.model.ClaimAssessment` the certificate consumes, judged with the same oracle.

The objective value is well-defined even when the flux distribution that achieves it is not
(alternate optima), so an objective-value claim is reproduced or not without guessing among
equivalent flux vectors. Solving the linear program uses the optional ``fba`` extra (scipy);
it is imported lazily, so the core stays dependency-free.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .model import ClaimAssessment
from .oracle import Attribution, ReferenceKind, Tolerance, judge_scalar


class FbaUnavailable(RuntimeError):
    """Raised when an FBA is requested but the optional ``fba`` extra (scipy) is not installed."""


class InfeasibleFba(RuntimeError):
    """Raised when the flux-balance problem has no bounded, feasible optimum."""


def _linprog() -> Any:
    try:
        from scipy.optimize import linprog
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise FbaUnavailable(
            "constraint-based reproduction needs the 'fba' extra (scipy); "
            "install with pip install 'reprolith[fba]'"
        ) from exc
    return linprog


def solve_objective(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
) -> float:
    """Maximize the objective flux subject to steady state and reaction bounds.

    ``stoichiometry`` is the S matrix (one row per metabolite, one column per reaction);
    ``objective`` weights the reactions in the objective; ``lower``/``upper`` are per-reaction
    flux bounds (``None`` upper for unbounded). Returns the optimal objective value, or raises
    :class:`InfeasibleFba` if the problem is infeasible or unbounded.
    """
    linprog = _linprog()
    result = linprog(
        c=[-x for x in objective],  # linprog minimizes; FBA maximizes
        A_eq=[list(row) for row in stoichiometry],
        b_eq=[0.0] * len(stoichiometry),
        bounds=list(zip(lower, upper)),
        method="highs",
    )
    if not result.success:
        raise InfeasibleFba(f"the flux-balance problem is not solvable: {result.message}")
    return float(-result.fun)


def judge_objective(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: float,
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Reproduce an FBA objective-value claim: solve the LP and judge it against the reported value.

    Uses the oracle's scalar comparison and honesty invariants, so a partial or failed verdict
    still requires an attribution and a load-bearing assumption still qualifies the result.
    """
    predicted = solve_objective(stoichiometry, objective, lower, upper)
    return judge_scalar(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        reported=reported,
        predicted=predicted,
        reference_kind=reference_kind,
        tolerance=tolerance,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def reaction_essentiality(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    threshold: float = 1e-6,
) -> frozenset[int]:
    """The indices of reactions whose knockout collapses the objective — the essential set.

    A reaction is essential if constraining its flux to zero drops the optimum below
    ``threshold`` of the unperturbed optimum (or makes the problem infeasible). This is the
    second FBA fingerprint the spec names (spec: constraint-based-class), and it too is
    well-defined regardless of alternate optima.
    """
    baseline = solve_objective(stoichiometry, objective, lower, upper)
    if baseline <= 0.0:
        return frozenset()
    essential: set[int] = set()
    for i in range(len(objective)):
        knocked_lower = [0.0 if j == i else lo for j, lo in enumerate(lower)]
        knocked_upper: list[float | None] = [0.0 if j == i else up for j, up in enumerate(upper)]
        try:
            optimum = solve_objective(stoichiometry, objective, knocked_lower, knocked_upper)
        except InfeasibleFba:
            optimum = 0.0
        if optimum < threshold * baseline:
            essential.add(i)
    return frozenset(essential)


def essentiality_agreement(computed: frozenset[int], reported: frozenset[int]) -> float:
    """Fraction of reactions the computed and reported essential sets agree on, over their union.

    1.0 is a perfect match; 0.0 is complete disagreement. An empty union (nothing essential
    either way) counts as full agreement.
    """
    union = computed | reported
    if not union:
        return 1.0
    return len(computed & reported) / len(union)


__all__ = [
    "FbaUnavailable",
    "InfeasibleFba",
    "essentiality_agreement",
    "judge_objective",
    "reaction_essentiality",
    "solve_objective",
]
