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

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .engine import simulate
from .enums import ReproductionLevel, Verdict
from .oracle import (
    ComparisonMethod,
    PercentileBand,
    ReferenceKind,
    Tolerance,
    band_envelope_distance,
    band_worst_point,
    default_tolerance,
    estimation_default_tolerance,
    normalized_curve_distance,
    relative_error,
    require_documented_default,
    verdict_for,
    worst_point_deviation,
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
    #: The sampling a sampled check rests on (seed, ensemble size, duration). A deterministic
    #: check has none and omits the key; a sampled one without it reports a number the caller
    #: cannot re-run, which is the same hole the certificate path closed.
    protocol: str | None = None

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "verdict": self.verdict.value,
            "method": self.method,
            "discrepancy": self.discrepancy,
            "tolerance": self.tolerance,
            "scope": self.scope.to_dict(),
        }
        if self.protocol is not None:
            record["protocol"] = self.protocol
        return record


def _checked(
    tol: Tolerance,
    method: ComparisonMethod,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    level: ReproductionLevel = ReproductionLevel.SIMULATION,
) -> Tolerance:
    """Hold a linted tolerance to the same provenance rule the certifying judge holds it to.

    The judge refuses a ``class-default`` pair that is not *this* comparison's documented default,
    because the widest pair in the table would otherwise certify a 24% error under a provenance
    reading ``class-default``. The linter checked nothing, so an agent could gate its work on a
    verdict the certificate would refuse to publish — the same linter-versus-judge drift, one
    table row over.
    """
    require_documented_default(tol, method, reference_kind, level)
    return tol


def _all_finite(*series: Sequence[float]) -> bool:
    return all(math.isfinite(v) for values in series for v in values)


def _not_evaluable(method: ComparisonMethod, tolerance: Tolerance) -> LintResult:
    """Abstain: the run produced nothing comparable, which is not the same as producing a wrong value."""
    return LintResult(
        verdict=Verdict.NOT_EVALUABLE,
        method=method.value,
        discrepancy="the run produced non-finite output; there is no comparable value to judge",
        tolerance=tolerance.label(),
    )


def _curve_lint(reference: Sequence[float], predicted: Sequence[float], tol: Tolerance) -> LintResult:
    """Judge a curve the way :func:`reprolith.judge_curve` does — average *and* worst point.

    The inline linter and the certificate path have to answer the same question the same way: an
    agent gates its work on the linter and then publishes through the judge, so a rule that lives
    in only one of them means the linter green-lights a reconstruction the certificate refuses. The
    worst-point rule was added to the judge alone, and a doubled peak that the judge calls
    `not-reproduced` linted as a clean pass on a 201-point curve.
    """
    distance = normalized_curve_distance(reference, predicted)
    worst = worst_point_deviation(reference, predicted)
    scaled_worst = (
        worst * (tol.reproduced_within / tol.partial_within) if tol.partial_within > 0.0 else worst
    )
    return LintResult(
        verdict=verdict_for(max(distance, scaled_worst), tol),
        method=ComparisonMethod.CURVE_NORMALIZED_DISTANCE.value,
        discrepancy=(
            f"normalized distance {distance:.4f}, worst point {worst:.4f} of span "
            f"(pass budget {tol.partial_within:.4f})"
        ),
        tolerance=tol.label(),
    )


def _reported_zero_lint(
    reported: float, predicted: float, method: ComparisonMethod, tol: Tolerance
) -> LintResult | None:
    """Abstain on a reported zero with no scale, the way :func:`reprolith.judge_scalar` does.

    A lethality claim — the canonical constraint-based claim shape — reports zero, and
    :func:`relative_error` raises without the scale that zero is relative to. The judge turns that
    into an abstention; the linter propagated the exception, so an agent linting the claim got a
    server error where the certificate would have said "not evaluable, and here is what it needs".
    """
    if reported == 0.0 and predicted != 0.0:
        return LintResult(
            verdict=Verdict.NOT_EVALUABLE,
            method=method.value,
            discrepancy=(
                f"the reported value is zero and the run gives {predicted:.6g}, so there is no "
                "magnitude to judge a relative error against; state the scale the claim is zero "
                "relative to (e.g. the unperturbed value)"
            ),
            tolerance=tol.label(),
        )
    return None


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
    tol = _checked(
        tolerance or default_tolerance(ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind),
        ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind,
    )
    if not _all_finite(reference, predicted):
        return _not_evaluable(ComparisonMethod.CURVE_NORMALIZED_DISTANCE, tol)
    return _curve_lint(reference, predicted, tol)


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
    tol = _checked(
        tolerance or default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, reference_kind),
        ComparisonMethod.SCALAR_RELATIVE_ERROR, reference_kind,
    )
    if not _all_finite((reported, predicted)):
        return _not_evaluable(ComparisonMethod.SCALAR_RELATIVE_ERROR, tol)
    unscaled_zero = _reported_zero_lint(
        reported, predicted, ComparisonMethod.SCALAR_RELATIVE_ERROR, tol
    )
    if unscaled_zero is not None:
        return unscaled_zero
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
    max_events: int | None = None,
) -> LintResult:
    """Check a supplied SBML reaction network's mean species count against a reported value (inline SSA).

    The stochastic counterpart of :func:`lint_objective`: ingest the SBML reaction network, run a
    pinned Gillespie SSA ensemble, and judge the mean of ``species`` at ``duration`` against
    ``reported_mean`` with the scalar oracle. Deterministic in ``seed`` — the same network and
    protocol always yield the same scope-flagged verdict an agent can gate on.

    ``max_events`` bounds the per-trajectory SSA work (see :func:`reprolith.stochastic.gillespie`);
    the MCP boundary passes a finite ceiling so a large ``duration`` or rate cannot wedge the server.

    Two things this shares with the certificate path, because a caller gating a workflow on an
    inline verdict needs them at least as much as a reader of a certificate does. The result records
    the sampling protocol that produced it, so the number can be re-run. And an ensemble whose own
    noise is too large to decide the claim abstains rather than answering: at ten trajectories a
    provably correct immigration-death model fails its 5% claim on most seeds, so a confident
    `failed` there is a false accusation, and a confident `reproduced` is luck the caller cannot
    see.

    Needs the ``engine`` extra (python-libsbml for ingestion); the SSA itself is pure.
    """
    from .sbml import ingest_stochastic_sbml
    from .stochastic import (
        ensemble_final_counts,
        species_mean_variance,
        unresolvable_ensemble_reason,
    )

    names, reactions, initial = ingest_stochastic_sbml(sbml)
    ensemble = ensemble_final_counts(
        len(names), reactions, initial, duration=duration, trajectories=trajectories, seed=seed,
        max_events=max_events,
    )
    mean, variance = species_mean_variance(ensemble, species)
    tol = _checked(
        tolerance or default_tolerance(
            ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
        ),
        ComparisonMethod.SCALAR_RELATIVE_ERROR,
    )
    protocol = f"SSA ensemble: {trajectories} trajectories to t={duration:g}, seed {seed}"
    if not _all_finite((reported_mean, mean)):
        return replace(
            _not_evaluable(ComparisonMethod.SCALAR_RELATIVE_ERROR, tol), protocol=protocol
        )
    # An extinction claim reports zero, and `relative_error` raises without the scale it is zero
    # relative to. Its two siblings, `lint_objective` and `lint_estimation`, turn that into an
    # abstention; this one propagated the exception through the MCP boundary as a server error.
    unscaled_zero = _reported_zero_lint(
        reported_mean, mean, ComparisonMethod.SCALAR_RELATIVE_ERROR, tol
    )
    if unscaled_zero is not None:
        return replace(unscaled_zero, protocol=protocol)
    unresolvable = unresolvable_ensemble_reason(
        reported_mean=reported_mean, variance=variance, trajectories=trajectories, tolerance=tol,
    )
    if unresolvable is not None:
        return LintResult(
            verdict=Verdict.NOT_EVALUABLE,
            method=ComparisonMethod.SCALAR_RELATIVE_ERROR.value,
            discrepancy=unresolvable,
            tolerance=tol.label(),
            protocol=protocol,
        )
    error = relative_error(reported_mean, mean)
    return LintResult(
        verdict=verdict_for(error, tol),
        method=ComparisonMethod.SCALAR_RELATIVE_ERROR.value,
        discrepancy=f"relative error {error:.4f} (mean {mean:.4g} vs reported {reported_mean:.4g})",
        tolerance=tol.label(),
        protocol=protocol,
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
    verdict. Rejects a time step past the explicit-scheme stability limit, or one too small to
    advance the profile at all (via :func:`diffuse_1d`), and abstains rather than returning a
    confident verdict when the run diverges to a non-finite profile — the same rule the certifying
    oracle applies.
    """
    from .spatial import diffuse_1d

    if steps < 1:
        raise ValueError("steps must be at least 1: a zero-step run returns the initial profile")
    predicted = diffuse_1d(initial, diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, decay=decay)
    tol = _checked(
        tolerance or default_tolerance(ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind),
        ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind,
    )
    # The same protocol string `certify_spatial` attaches, for the same reason it argues at length
    # there: the discretization *is* the run, and the boundary condition is one this solver imposes
    # rather than one the caller chose — a reader of an inline verdict cannot see either anywhere
    # else. This surface published a bare `reproduced` with neither.
    protocol = (
        f"1-D finite difference: D={diffusivity!r}, dx={dx!r}, dt={dt!r}, {steps} steps"
        + (f", decay={decay!r}" if decay else "")
        + ", zero-flux (Neumann) boundaries"
    )
    if not _all_finite(reference, predicted):
        return replace(
            _not_evaluable(ComparisonMethod.CURVE_NORMALIZED_DISTANCE, tol), protocol=protocol
        )
    return replace(_curve_lint(reference, predicted, tol), protocol=protocol)


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
    # Truthiness is the wrong reading of a reported level: the JSON string "0" and the level 0.4
    # are both truthy, so a state that is not a fixed point would be rewritten into one that is
    # and linted green. A Boolean node is 0 or 1 or it is not a Boolean node.
    for node, level in reported.items():
        if isinstance(level, bool) or not isinstance(level, int) or level not in (0, 1):
            raise ValueError(
                f"node {node!r} has reported level {level!r}; a Boolean state assigns each node "
                "the integer 0 or 1"
            )
    target = tuple(int(reported[n]) for n in network.nodes)
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
    tol = _checked(
        tolerance or estimation_default_tolerance(),
        ComparisonMethod.SCALAR_RELATIVE_ERROR,
        level=ReproductionLevel.ESTIMATION,
    )
    if not _all_finite((reported, recovered)):
        return _not_evaluable(ComparisonMethod.SCALAR_RELATIVE_ERROR, tol)
    unscaled_zero = _reported_zero_lint(
        reported, recovered, ComparisonMethod.SCALAR_RELATIVE_ERROR, tol
    )
    if unscaled_zero is not None:
        return unscaled_zero
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
    error. Deterministic and dependency-free. A diverged band makes the envelope un-judgeable, so
    non-finite input abstains rather than returning a verdict — the same rule the certifying oracle
    applies.
    """
    ref_bands = tuple(PercentileBand(float(b["percentile"]), tuple(b["curve"])) for b in reported)
    pred_bands = tuple(PercentileBand(float(b["percentile"]), tuple(b["curve"])) for b in predicted)
    tol = _checked(
        tolerance or default_tolerance(
            ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, reference_kind
        ),
        ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, reference_kind,
    )
    if not _all_finite(
        [v for band in ref_bands for v in band.curve],
        [v for band in pred_bands for v in band.curve],
    ):
        return _not_evaluable(ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, tol)
    distance, worst_band = band_envelope_distance(ref_bands, pred_bands)
    worst, worst_point_band = band_worst_point(ref_bands, pred_bands)
    scaled_worst = (
        worst * (tol.reproduced_within / tol.partial_within) if tol.partial_within > 0.0 else worst
    )
    return LintResult(
        verdict=verdict_for(max(distance, scaled_worst), tol),
        method=ComparisonMethod.DISTRIBUTION_BAND_DISTANCE.value,
        discrepancy=(
            f"worst band {worst_band.label()} normalized distance {distance:.4f}, worst point "
            f"{worst:.4f} of span in {worst_point_band.label()} "
            f"(pass budget {tol.partial_within:.4f})"
        ),
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
