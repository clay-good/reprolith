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

from collections.abc import Sequence
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


__all__ = ["LintResult", "lint_curve"]
