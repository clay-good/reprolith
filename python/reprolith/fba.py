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
from dataclasses import dataclass
from typing import Any

from .model import ClaimAssessment
from .oracle import Attribution, ReferenceKind, Tolerance, judge_scalar, not_evaluable


@dataclass(frozen=True)
class FbaModel:
    """A constraint-based model in the form the oracle solves: the S matrix, the objective, the
    per-reaction flux bounds, and the species/reaction ids that give each row and column a name.

    This is what SBML-fbc ingestion produces (:func:`reprolith.ingest_fbc_sbml`), so a published
    model can be fed straight to :func:`solve_objective`, :func:`flux_variability`, and the judges.
    """

    species_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    stoichiometry: tuple[tuple[float, ...], ...]
    objective: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float | None, ...]

    def reaction_index(self, reaction_id: str) -> int:
        """The column index of a reaction id, for judging that reaction's flux by name."""
        return self.reaction_ids.index(reaction_id)


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


def flux_variability(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    fraction_of_optimum: float = 1.0,
) -> list[tuple[float, float]]:
    """The min and max each reaction's flux can take while the objective stays optimal.

    This is the honest answer to the alternate-optima problem the spec names (spec:
    constraint-based-class): a single optimal flux vector is ambiguous when many achieve the
    same objective, so instead of picking one, FVA reports the whole feasible interval per
    reaction at (a ``fraction_of_optimum`` of) the optimum. A reaction pinned to a single value
    reproduces exactly; one with a wide interval cannot be certified to a single reported flux.

    Returns one ``(min, max)`` tuple per reaction, in reaction order.
    """
    linprog = _linprog()
    optimum = solve_objective(stoichiometry, objective, lower, upper)
    floor = fraction_of_optimum * optimum
    a_eq = [list(row) for row in stoichiometry]
    b_eq = [0.0] * len(stoichiometry)
    # Hold the objective at (a fraction of) its optimum: objective . v >= floor, written for a
    # <=-form solver as -objective . v <= -floor.
    a_ub = [[-x for x in objective]]
    b_ub = [-floor]
    bounds = list(zip(lower, upper))
    ranges: list[tuple[float, float]] = []
    for i in range(len(objective)):
        select = [1.0 if j == i else 0.0 for j in range(len(objective))]
        lo = linprog(c=select, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
        hi = linprog(
            c=[-x for x in select], A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs"
        )
        if not lo.success or not hi.success:
            raise InfeasibleFba(f"flux-variability problem is not solvable for reaction {i}")
        ranges.append((float(lo.fun), float(-hi.fun)))
    return ranges


def judge_flux(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: float,
    interval: tuple[float, float],
    pin_tolerance: float = 1e-6,
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a reported reaction flux against its flux-variability interval — honestly.

    ``interval`` is the ``(min, max)`` this reaction can take at the optimum (from
    :func:`flux_variability`). The verdict follows the spec's honesty rule for alternate optima
    (spec: constraint-based-class), which is design goal 2 in this setting:

    * The interval **pins** the flux (min == max within ``pin_tolerance``) and contains the
      reported value → the model uniquely produces it: judged as reproduced via the scalar oracle.
    * The reported value lies **inside a non-trivial interval** → the model is *consistent with*
      the value but does not determine it; certifying "reproduced" would overstate, so we abstain
      (``not-evaluable``) rather than claim a pass the alternate optima do not earn.
    * The reported value lies **outside** the feasible interval → the model cannot achieve this
      flux at the optimum: judged against the nearest feasible flux, so it lands partial/failed
      (and, like any non-pass, requires an ``attribution``).
    """
    lo, hi = interval
    slack = pin_tolerance * max(1.0, abs(lo), abs(hi))
    inside = lo - slack <= reported <= hi + slack
    pinned = (hi - lo) <= slack

    if inside and pinned:
        return judge_scalar(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reported=reported,
            predicted=(lo + hi) / 2.0,
            reference_kind=reference_kind,
            tolerance=tolerance,
            attribution=attribution,
            assumption_qualified=assumption_qualified,
        )
    if inside:
        return not_evaluable(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reason=(
                f"the model does not uniquely determine this flux at the optimum: the "
                f"flux-variability interval [{lo:.4g}, {hi:.4g}] contains the reported "
                f"{reported:.4g} but leaves it free (alternate optima)"
            ),
            reference_kind=reference_kind,
        )
    nearest = lo if reported < lo else hi
    return judge_scalar(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        reported=reported,
        predicted=nearest,
        reference_kind=reference_kind,
        tolerance=tolerance,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


@dataclass(frozen=True)
class FrogFingerprint:
    """A standardized, solver-independent reproducibility fingerprint for a constraint-based model.

    Named for the FROG analysis the field uses (Flux optimum, Reaction variability, Objective,
    Gene/reaction deletion). It bundles the three reaction-level results the constraint-based-class
    spec names — the optimal objective value, each reaction's flux-variability interval, and the
    objective remaining after each reaction is deleted — so a verdict can be the comparison of two
    fingerprints rather than of a single number. (Gene-level deletion is a further extension that
    needs gene–reaction associations the fbc ingest does not yet capture.)
    """

    reaction_ids: tuple[str, ...]
    objective_value: float
    variability: tuple[tuple[float, float], ...]
    deletion_objectives: tuple[float, ...]


@dataclass(frozen=True)
class FrogComparison:
    """The component-wise agreement of two FROG fingerprints, with the disagreements named."""

    objective_agrees: bool
    variability_agrees: bool
    deletion_agrees: bool
    disagreements: tuple[str, ...]

    @property
    def agrees(self) -> bool:
        return self.objective_agrees and self.variability_agrees and self.deletion_agrees


def frog_fingerprint(model: FbaModel, *, fraction_of_optimum: float = 1.0) -> FrogFingerprint:
    """Compute the FROG fingerprint of a constraint-based model (spec: constraint-based-class).

    The objective value and each reaction's variability interval come from :func:`solve_objective`
    and :func:`flux_variability`; the deletion objective for a reaction is the optimum with that
    reaction's flux constrained to zero (0.0 if the knockout makes the model infeasible). Every
    component is well-defined regardless of alternate optima, so the fingerprint is portable.
    """
    objective_value = solve_objective(
        model.stoichiometry, model.objective, model.lower, model.upper
    )
    variability = flux_variability(
        model.stoichiometry,
        model.objective,
        model.lower,
        model.upper,
        fraction_of_optimum=fraction_of_optimum,
    )
    deletion: list[float] = []
    for i in range(len(model.reaction_ids)):
        knocked_lower = [0.0 if j == i else lo for j, lo in enumerate(model.lower)]
        knocked_upper: list[float | None] = [
            0.0 if j == i else up for j, up in enumerate(model.upper)
        ]
        try:
            deletion.append(
                solve_objective(model.stoichiometry, model.objective, knocked_lower, knocked_upper)
            )
        except InfeasibleFba:
            deletion.append(0.0)
    return FrogFingerprint(
        reaction_ids=model.reaction_ids,
        objective_value=objective_value,
        variability=tuple(variability),
        deletion_objectives=tuple(deletion),
    )


def _close(a: float, b: float, rel_tol: float) -> bool:
    return abs(a - b) <= rel_tol * max(1.0, abs(a), abs(b))


def compare_frog(
    computed: FrogFingerprint, reported: FrogFingerprint, *, rel_tol: float = 1e-6
) -> FrogComparison:
    """Compare two FROG fingerprints component-wise, aligning reactions by id.

    The objective values, each shared reaction's variability bounds, and each shared reaction's
    deletion objective must agree within ``rel_tol``. Reactions present in only one fingerprint are
    recorded as disagreements, so a structural mismatch is never hidden by a numeric pass.
    """
    disagreements: list[str] = []

    objective_agrees = _close(computed.objective_value, reported.objective_value, rel_tol)
    if not objective_agrees:
        disagreements.append(
            f"objective {computed.objective_value:.6g} != {reported.objective_value:.6g}"
        )

    reported_index = {rid: i for i, rid in enumerate(reported.reaction_ids)}
    only_computed = [r for r in computed.reaction_ids if r not in reported_index]
    only_reported = [r for r in reported.reaction_ids if r not in set(computed.reaction_ids)]
    for rid in only_computed + only_reported:
        disagreements.append(f"reaction {rid} present in only one fingerprint")

    variability_agrees = True
    deletion_agrees = True
    for i, rid in enumerate(computed.reaction_ids):
        if rid not in reported_index:
            variability_agrees = deletion_agrees = False
            continue
        j = reported_index[rid]
        (clo, chi), (rlo, rhi) = computed.variability[i], reported.variability[j]
        if not (_close(clo, rlo, rel_tol) and _close(chi, rhi, rel_tol)):
            variability_agrees = False
            disagreements.append(
                f"variability {rid}: [{clo:.6g}, {chi:.6g}] != [{rlo:.6g}, {rhi:.6g}]"
            )
        if not _close(computed.deletion_objectives[i], reported.deletion_objectives[j], rel_tol):
            deletion_agrees = False
            disagreements.append(
                f"deletion {rid}: {computed.deletion_objectives[i]:.6g} != "
                f"{reported.deletion_objectives[j]:.6g}"
            )

    if only_computed or only_reported:
        variability_agrees = deletion_agrees = False

    return FrogComparison(
        objective_agrees=objective_agrees,
        variability_agrees=variability_agrees,
        deletion_agrees=deletion_agrees,
        disagreements=tuple(disagreements),
    )


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
    "FbaModel",
    "FbaUnavailable",
    "FrogComparison",
    "FrogFingerprint",
    "InfeasibleFba",
    "compare_frog",
    "essentiality_agreement",
    "flux_variability",
    "frog_fingerprint",
    "judge_flux",
    "judge_objective",
    "reaction_essentiality",
    "solve_objective",
]
