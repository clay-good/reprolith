"""The inline deterministic linter (bootstrap task 6.2).

The common agent pattern is to check a single model against a single claim inline — no catalog
lifecycle, no certificate — and gate a workflow on a fast, deterministic pass/fail (spec:
``mcp-server`` — "Deterministic linter mode"). This composes the two pieces that already exist:
run the supplied SBML model under the pinned engine, then judge the output against the claim's
reference with the oracle's comparison and declared tolerance.

Both halves are deterministic, so the linter is too: the same model and claim yield the same
verdict, which is exactly what lets an agent treat it as a gate. The verdict never travels as a
bare boolean — the result carries its method, discrepancy, tolerance, and the inescapable scope
flag (spec: "Scope flag is inescapable over MCP too").

Running the engine needs the optional ``engine`` extra; the comparison itself is dependency-free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .engine import simulate
from .enums import Verdict
from .oracle import (
    ComparisonMethod,
    ReferenceKind,
    Tolerance,
    default_tolerance,
    normalized_curve_distance,
    relative_error,
    verdict_for,
)
from .scope import Scope


@dataclass(frozen=True)
class LintResult:
    """A single inline check's verdict, with the qualifications that must travel with it."""

    verdict: Verdict
    method: str
    discrepancy: str
    tolerance: str
    scope: Scope = Scope()

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "method": self.method,
            "discrepancy": self.discrepancy,
            "tolerance": self.tolerance,
            "scope": self.scope.to_dict(),
        }


def lint_curve(
    sbml: str,
    species: str,
    *,
    reference: Sequence[float],
    duration: float,
    steps: int,
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
) -> LintResult:
    """Check a supplied SBML model's ``species`` curve against a claim's reference points.

    Simulates the model under the pinned engine over ``[0, duration]`` at ``steps`` uniform
    intervals — so ``reference`` must supply ``steps + 1`` values at those same points — and
    returns the verdict, the normalized distance, and the tolerance used. Deterministic: the
    same model and reference always yield the same result.
    """
    _, predicted = simulate(sbml, species, duration=duration, steps=steps)
    if len(reference) != len(predicted):
        raise ValueError(
            f"reference has {len(reference)} points but the model was sampled at "
            f"{len(predicted)}; sample the reference at the same {steps + 1} points"
        )
    tol = tolerance or default_tolerance(
        ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind
    )
    distance = normalized_curve_distance(reference, predicted)
    return LintResult(
        verdict=verdict_for(distance, tol),
        method=ComparisonMethod.CURVE_NORMALIZED_DISTANCE.value,
        discrepancy=f"normalized distance {distance:.4f}",
        tolerance=tol.label(),
    )


def lint_objective(
    sbml: str,
    *,
    reported: float,
    medium: Mapping[str, float] | None = None,
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
) -> LintResult:
    """Check a supplied SBML-fbc model's optimal objective against a reported value (inline FBA).

    The constraint-based counterpart of :func:`lint_curve`: ingest the model, apply the optional
    ``medium`` (each entry an exchange reaction's maximum uptake, applied as that reaction's uptake
    bound), solve the objective linear program, and judge the optimum against ``reported`` with the
    scalar oracle and its declared tolerance. Same deterministic, scope-flagged ``LintResult`` an
    agent can gate on — never a bare boolean.

    Needs the ``engine`` extra (python-libsbml for fbc ingest) and the ``fba`` extra (scipy's LP
    solver), both imported lazily. A ``medium`` entry naming a reaction the model does not contain
    raises, so a typo is surfaced rather than silently ignored.
    """
    from .fba import solve_objective
    from .sbml import ingest_fbc_sbml

    model = ingest_fbc_sbml(sbml)
    lower = list(model.lower)
    for reaction_id, uptake in (medium or {}).items():
        if reaction_id not in model.reaction_ids:
            raise ValueError(
                f"medium names reaction {reaction_id!r}, which the model does not contain"
            )
        lower[model.reaction_index(reaction_id)] = -abs(uptake)
    predicted = solve_objective(model.stoichiometry, model.objective, lower, model.upper)
    tol = tolerance or default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, reference_kind)
    error = relative_error(reported, predicted)
    return LintResult(
        verdict=verdict_for(error, tol),
        method=ComparisonMethod.SCALAR_RELATIVE_ERROR.value,
        discrepancy=f"relative error {error:.4f} (optimum {predicted:.6g} vs reported {reported:.6g})",
        tolerance=tol.label(),
    )


def lint_steady_state(
    rules: Mapping[str, str],
    reported: Mapping[str, int],
) -> LintResult:
    """Check whether a reported steady state is a fixed point of a supplied Boolean network.

    The logical-class counterpart of :func:`lint_curve`: ``rules`` maps each node to a Boolean
    expression over the others (e.g. ``{"A": "!B", "B": "!A"}``), and ``reported`` assigns every
    node a 0/1 value. The network's synchronous fixed points are computed exactly and the reported
    state is checked for membership — a dependency-free, deterministic gate an agent can rely on.
    The comparison is an exact attractor-set match, so there is no numeric tolerance to declare.
    """
    from .logical import parse_boolean_network

    network = parse_boolean_network(rules)
    if set(reported) != set(network.nodes):
        raise ValueError("reported state must assign exactly the network's nodes")
    target = tuple(1 if reported[n] else 0 for n in network.nodes)
    fixed = {tuple(1 if fp[n] else 0 for n in network.nodes) for fp in network.fixed_points()}
    matched = target in fixed
    discrepancy = (
        "reported steady state is a fixed point"
        if matched
        else f"reported state is not a fixed point (network has {len(fixed)} fixed point(s))"
    )
    return LintResult(
        verdict=Verdict.REPRODUCED if matched else Verdict.FAILED,
        method=ComparisonMethod.ATTRACTOR_SET_MATCH.value,
        discrepancy=discrepancy,
        tolerance="exact (attractor-set-match)",
    )


__all__ = ["LintResult", "lint_curve", "lint_objective", "lint_steady_state"]
