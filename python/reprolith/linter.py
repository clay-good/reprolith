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
    PercentileBand,
    ReferenceKind,
    Tolerance,
    band_envelope_distance,
    default_tolerance,
    estimation_default_tolerance,
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


def lint_stochastic(
    sbml: str,
    *,
    species: int,
    reported_mean: float,
    duration: float,
    trajectories: int,
    seed: int,
    tolerance: Tolerance | None = None,
) -> LintResult:
    """Check a supplied SBML reaction network's mean species count against a reported value (inline SSA).

    The stochastic counterpart of :func:`lint_objective`: ingest the SBML reaction network, run a
    pinned Gillespie SSA ensemble, and judge the mean of ``species`` at ``duration`` against
    ``reported_mean`` with the scalar oracle. Deterministic in ``seed`` — the same network and
    protocol always yield the same scope-flagged verdict an agent can gate on.

    Needs the ``engine`` extra (python-libsbml for ingestion); the SSA itself is pure.
    """
    from .sbml import ingest_stochastic_sbml
    from .stochastic import ensemble_final_counts, species_mean_variance

    names, reactions, initial = ingest_stochastic_sbml(sbml)
    ensemble = ensemble_final_counts(
        len(names), reactions, initial, duration=duration, trajectories=trajectories, seed=seed
    )
    mean, _ = species_mean_variance(ensemble, species)
    tol = tolerance or default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC)
    error = relative_error(reported_mean, mean)
    return LintResult(
        verdict=verdict_for(error, tol),
        method=ComparisonMethod.SCALAR_RELATIVE_ERROR.value,
        discrepancy=f"relative error {error:.4f} (mean {mean:.4g} vs reported {reported_mean:.4g})",
        tolerance=tol.label(),
    )


def lint_diffusion(
    initial: Sequence[float],
    reference: Sequence[float],
    *,
    diffusivity: float,
    dx: float,
    dt: float,
    steps: int,
    decay: float = 0.0,
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
) -> LintResult:
    """Check a 1-D reaction-diffusion profile against a reported one (inline spatial reproduction).

    The spatial counterpart of :func:`lint_curve`: evolve ``initial`` under diffusion (and optional
    first-order ``decay``) for ``steps`` steps of ``dt`` at spacing ``dx``, and judge the resulting
    profile against ``reference`` by normalized curve distance. Pure and dependency-free — no engine
    extra — and deterministic, so the same discretization always yields the same scope-flagged
    verdict. Rejects a time step past the explicit-scheme stability limit (via :func:`diffuse_1d`).
    """
    from .spatial import diffuse_1d

    predicted = diffuse_1d(initial, diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, decay=decay)
    tol = tolerance or default_tolerance(ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind)
    distance = normalized_curve_distance(reference, predicted)
    return LintResult(
        verdict=verdict_for(distance, tol),
        method=ComparisonMethod.CURVE_NORMALIZED_DISTANCE.value,
        discrepancy=f"normalized distance {distance:.4f}",
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


def lint_estimation(
    reported: float,
    recovered: float,
    *,
    tolerance: Tolerance | None = None,
) -> LintResult:
    """Check a re-derived parameter estimate against a paper's reported estimate (inline estimation).

    The estimation counterpart of :func:`lint_curve`: given a ``recovered`` estimate (the caller
    ran the re-fit — the engine-dependent half) and the paper's ``reported`` estimate, judge them by
    relative error against the documented estimation-level default tolerance, which is wider than a
    simulation scalar's because a re-fit is sensitive to the optimizer and its starting values.
    Deterministic and dependency-free — the same pair always yields the same scope-flagged verdict.
    """
    tol = tolerance or estimation_default_tolerance()
    error = relative_error(reported, recovered)
    return LintResult(
        verdict=verdict_for(error, tol),
        method=ComparisonMethod.SCALAR_RELATIVE_ERROR.value,
        discrepancy=f"relative error {error:.4f} (estimation: recovered {recovered:.6g} vs reported {reported:.6g})",
        tolerance=tol.label(),
    )


def lint_distribution(
    reported: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
    *,
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
) -> LintResult:
    """Check a simulated population envelope against a reported one (inline population reproduction).

    The population counterpart of :func:`lint_curve`: ``reported`` and ``predicted`` are percentile
    bands, each a ``{"percentile": p, "curve": [...]}`` mapping. The verdict is governed by the
    worst-matched band (so a good median cannot mask a divergent tail) against the documented
    distributional default tolerance, wider than a single trajectory's to absorb population sampling
    error. Deterministic and dependency-free.
    """
    ref_bands = tuple(PercentileBand(float(b["percentile"]), tuple(b["curve"])) for b in reported)
    pred_bands = tuple(PercentileBand(float(b["percentile"]), tuple(b["curve"])) for b in predicted)
    tol = tolerance or default_tolerance(
        ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, reference_kind
    )
    distance, worst_band = band_envelope_distance(ref_bands, pred_bands)
    return LintResult(
        verdict=verdict_for(distance, tol),
        method=ComparisonMethod.DISTRIBUTION_BAND_DISTANCE.value,
        discrepancy=f"worst band {worst_band.label()} normalized distance {distance:.4f}",
        tolerance=tol.label(),
    )


__all__ = [
    "LintResult",
    "lint_curve",
    "lint_diffusion",
    "lint_distribution",
    "lint_estimation",
    "lint_objective",
    "lint_steady_state",
    "lint_stochastic",
]
