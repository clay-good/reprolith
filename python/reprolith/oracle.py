"""The simulation oracle's comparison core (bootstrap tasks 4.1–4.5).

The oracle is Reprolith's deterministic judge: it compares a reconstruction's output against
a paper's own claim, within a declared tolerance, and returns a per-claim
:class:`~reprolith.model.ClaimAssessment` of ``reproduced``, ``partial``, ``failed``, or
``not-evaluable``. What lives here is the *judgment*: the comparison math, the documented
class-default tolerances, abstention, and root-cause attribution — everything that must be
trustworthy before the reconstructor is clever (design goal 2).

What does **not** live here is the simulator that produces the predicted output from an SBML
model under a pinned engine; that is the deferred, dependency-heavy half of the oracle. These
functions take an already-produced ``predicted`` value or series, so the judgment is pure,
deterministic, and unit-testable without an engine (spec: ``simulation-oracle``).

The tolerance defaults below are documented MVP-initial values with a stated basis; the
discipline loop (task 7.4) refines them from evidence rather than leaving them as magic
numbers.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .enums import ReproductionLevel, Verdict
from .model import ClaimAssessment


class ComparisonMethod(str, Enum):
    """How an output is compared to its reference."""

    SCALAR_RELATIVE_ERROR = "scalar-relative-error"
    CURVE_NORMALIZED_DISTANCE = "curve-normalized-distance"
    DISTRIBUTION_BAND_DISTANCE = "distribution-band-distance"
    FINGERPRINT_COMPARISON = "fingerprint-comparison"
    ATTRACTOR_SET_MATCH = "attractor-set-match"


class ReferenceKind(str, Enum):
    """What the claim is compared against; a figure-only reference widens tolerance."""

    NUMERIC = "numeric"
    DIGITIZED_FIGURE = "digitized-figure"


class ToleranceSource(str, Enum):
    """Where a tolerance came from — never an unexplained magic number."""

    CLASS_DEFAULT = "class-default"
    PAPER_STATED = "paper-stated"
    REVIEWER_OVERRIDE = "reviewer-override"


class FailureMode(str, Enum):
    """The maintained set of root-cause categories for a non-reproducing verdict.

    Failure modes are specialized per model class (spec: ``simulation-oracle`` — "Root-caused
    failures"; ``constraint-based-class`` — "Known constraint-based failure modes are
    first-class"). The first group is PK/PD; the second is constraint-based (FBA). Two are shared
    across classes: ``ENGINE_SENSITIVITY`` also names LP solver sensitivity, and
    ``MANUSCRIPT_ERROR``/``ASSUMPTION_DEPENDENCE`` are class-agnostic. ``UNCATEGORIZED`` is the
    escape hatch: a failure fitting none of the catalogued causes is recorded as uncategorized and
    flags the set to be extended, so the catalog never silently misclassifies."""

    # PK/PD (ODE curve-matching) root causes.
    MISSING_PARAMETER = "missing-parameter"
    UNIT_MISMATCH = "unit-mismatch"
    AMBIGUOUS_INITIAL_CONDITION = "ambiguous-initial-condition"
    # PK/PD population (distributional) root causes (spec: simulation-oracle — "Population-specific
    # failure modes").
    UNSPECIFIED_VARIABILITY_MODEL = "unspecified-between-subject-variability-model"
    UNSPECIFIED_POPULATION_SAMPLING = "unspecified-population-size-or-sampling"
    # Estimation-reproduction root causes: re-fitting recovers a different estimate (spec:
    # simulation-oracle — "Estimation reproduction is a distinct verdict").
    UNSTATED_ESTIMATION_METHOD = "unstated-estimation-method-or-objective"
    UNSTATED_STARTING_VALUES = "unstated-parameter-starting-values"
    LOCAL_OPTIMUM = "convergence-to-a-different-local-optimum"
    ENGINE_SENSITIVITY = "engine-algorithm-sensitivity"
    MANUSCRIPT_ERROR = "apparent-manuscript-error"
    ASSUMPTION_DEPENDENCE = "load-bearing-assumption-dependence"
    # Constraint-based (FBA) root causes (spec: constraint-based-class). LP solver sensitivity is
    # named by the shared ``ENGINE_SENSITIVITY`` above.
    UNSPECIFIED_MEDIUM = "unspecified-medium-or-exchange-bounds"
    AMBIGUOUS_OBJECTIVE = "ambiguous-biomass-or-objective-definition"
    INCONSISTENT_GENE_ASSOCIATIONS = "missing-or-inconsistent-gene-reaction-associations"
    ALTERNATE_OPTIMA = "alternate-optima-flux-ambiguity"
    # Logical / Boolean-network root causes (spec: logical-class — "Catalogued root causes").
    UNSPECIFIED_UPDATE_SCHEME = "unspecified-update-scheme"
    AMBIGUOUS_LOGIC_RULE = "ambiguous-or-missing-logic-rule"
    UNSPECIFIED_INITIAL_STATE = "unspecified-initial-state-or-inputs"
    # Escape hatch for a failure fitting none of the above (spec: "recorded as uncategorized").
    UNCATEGORIZED = "uncategorized"


class Fault(str, Enum):
    """Whether a shortfall looks more like the paper's fault or the reconstruction's.

    Always a hypothesis, never a proven cause (spec: "Distinguishing paper fault from
    reconstruction fault").
    """

    MANUSCRIPT = "manuscript"
    RECONSTRUCTION = "reconstruction"


@dataclass(frozen=True)
class Tolerance:
    """A declared pass/partial threshold with its provenance.

    A measured discrepancy at or below ``reproduced_within`` is ``reproduced``; at or below
    ``partial_within`` is ``partial``; above it is ``failed``. Any non-default tolerance must
    state a rationale — a paper-stated precision or a reviewer's reason — so no threshold is a
    magic number.
    """

    reproduced_within: float
    partial_within: float
    source: ToleranceSource
    rationale: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.reproduced_within <= self.partial_within:
            raise ValueError("require 0 <= reproduced_within <= partial_within")
        if self.source is not ToleranceSource.CLASS_DEFAULT and not (self.rationale or "").strip():
            raise ValueError(f"a {self.source.value} tolerance must state a rationale")

    def label(self) -> str:
        return (
            f"reproduced<={self.reproduced_within:.3g}, "
            f"partial<={self.partial_within:.3g} ({self.source.value})"
        )


@dataclass(frozen=True)
class Attribution:
    """The root cause of a non-pass: a category, the implicated element, and a fault guess."""

    mode: FailureMode
    implicated: str
    fault: Fault


@dataclass(frozen=True)
class PercentileBand:
    """One percentile curve of a population envelope: a percentile and its trajectory.

    A population figure is a set of these — e.g. the 5th, 50th, and 95th percentile of the
    simulated concentration over time. ``percentile`` is in the open interval (0, 100); the
    band label (``P5``, ``P50``, …) is derived from it so a discrepancy can name the band that
    governed the verdict.
    """

    percentile: float
    curve: tuple[float, ...]

    def __post_init__(self) -> None:
        if not 0.0 < self.percentile < 100.0:
            raise ValueError("percentile must be in the open interval (0, 100)")
        if not self.curve:
            raise ValueError("a percentile band needs at least one sample point")

    def label(self) -> str:
        return f"P{self.percentile:g}"


# Documented MVP-initial class defaults. Simulation reproduction of a deterministic ODE model
# should match closely; the slack absorbs digitization and rounding, and is wider for a
# figure-only reference to reflect its added uncertainty. Refined by the discipline loop (7.4).
_DEFAULTS: dict[tuple[ComparisonMethod, ReferenceKind], Tolerance] = {
    (ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC): Tolerance(
        0.05, 0.15, ToleranceSource.CLASS_DEFAULT
    ),
    (ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.DIGITIZED_FIGURE): Tolerance(
        0.15, 0.30, ToleranceSource.CLASS_DEFAULT
    ),
    (ComparisonMethod.CURVE_NORMALIZED_DISTANCE, ReferenceKind.NUMERIC): Tolerance(
        0.10, 0.25, ToleranceSource.CLASS_DEFAULT
    ),
    (ComparisonMethod.CURVE_NORMALIZED_DISTANCE, ReferenceKind.DIGITIZED_FIGURE): Tolerance(
        0.20, 0.40, ToleranceSource.CLASS_DEFAULT
    ),
    # A population envelope is judged by its worst-matched percentile band and carries the
    # Monte-Carlo sampling error of a simulated population, so its band-distance defaults are
    # wider than a single deterministic trajectory's (spec: "Distributional tolerance provenance").
    (ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, ReferenceKind.NUMERIC): Tolerance(
        0.15, 0.35, ToleranceSource.CLASS_DEFAULT
    ),
    (ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, ReferenceKind.DIGITIZED_FIGURE): Tolerance(
        0.25, 0.50, ToleranceSource.CLASS_DEFAULT
    ),
}


def default_tolerance(method: ComparisonMethod, reference_kind: ReferenceKind) -> Tolerance:
    """The documented class-default tolerance for a comparison method and reference kind."""
    return _DEFAULTS[(method, reference_kind)]


# Estimation reproduction re-fits parameters from raw data, so a recovered estimate is sensitive
# to the optimizer, its starting values, and the objective — looser than reproducing a reported
# scalar from a fixed model. This documented default reflects that; it is keyed by reproduction
# level, not comparison method (spec: "Estimation reproduction is a distinct verdict").
_ESTIMATION_DEFAULT = Tolerance(0.10, 0.25, ToleranceSource.CLASS_DEFAULT)


def relative_error(reported: float, predicted: float) -> float:
    """Relative error of ``predicted`` against the ``reported`` value.

    Normalized by the reported magnitude; when the reported value is exactly zero, falls back
    to the absolute difference so a nonzero prediction is not divided away.
    """
    if reported == 0.0:
        return abs(predicted)
    return abs(predicted - reported) / abs(reported)


def normalized_curve_distance(reference: Sequence[float], predicted: Sequence[float]) -> float:
    """Root-mean-square distance between two aligned curves, normalized by the reference span.

    ``reference`` and ``predicted`` are y-values at the same sample points (the reconstruction
    is simulated at the reference's times). Normalizing by the reference's range makes the
    distance a unitless fraction comparable to a tolerance. A flat reference falls back to its
    mean magnitude.
    """
    if len(reference) != len(predicted):
        raise ValueError("reference and predicted must be sampled at the same points")
    if not reference:
        raise ValueError("need at least one sample point")
    n = len(reference)
    mse = sum((p - r) ** 2 for r, p in zip(reference, predicted)) / n
    rmse = math.sqrt(mse)
    span = max(reference) - min(reference)
    if span == 0.0:
        span = abs(sum(reference) / n)
    if span == 0.0:
        return 0.0 if rmse == 0.0 else float("inf")
    return rmse / span


def band_envelope_distance(
    reference: Sequence[PercentileBand], predicted: Sequence[PercentileBand]
) -> tuple[float, PercentileBand]:
    """Distance between two population envelopes, governed by their worst-matched band.

    ``reference`` and ``predicted`` are the reported and simulated percentile bands. The two
    envelopes must describe the same percentiles; each reference band is compared to the
    predicted band at the same percentile via :func:`normalized_curve_distance`, and the
    envelope's distance is the *worst* (largest) band distance — a well-matched median cannot
    hide a divergent tail, because the whole point of a population claim is its spread. Returns
    the worst distance together with the reference band that produced it, so the discrepancy can
    name the governing percentile.
    """
    if not reference or not predicted:
        raise ValueError("both envelopes need at least one percentile band")
    ref_by_pct = {b.percentile: b for b in reference}
    pred_by_pct = {b.percentile: b for b in predicted}
    if len(ref_by_pct) != len(reference) or len(pred_by_pct) != len(predicted):
        raise ValueError("percentiles within an envelope must be distinct")
    if ref_by_pct.keys() != pred_by_pct.keys():
        raise ValueError("reference and predicted envelopes must cover the same percentiles")
    worst_distance = -1.0
    worst_band = reference[0]
    for pct in sorted(ref_by_pct):
        ref_band, pred_band = ref_by_pct[pct], pred_by_pct[pct]
        distance = normalized_curve_distance(ref_band.curve, pred_band.curve)
        if distance > worst_distance:
            worst_distance, worst_band = distance, ref_band
    return worst_distance, worst_band


def verdict_for(measure: float, tol: Tolerance) -> Verdict:
    """Classify a measured discrepancy against a tolerance into a per-claim verdict.

    At or below ``reproduced_within`` is ``reproduced``; at or below ``partial_within`` is
    ``partial``; above it is ``failed``. This is the raw classification the inline linter uses;
    the full judge functions wrap it with method, tolerance provenance, and attribution.
    """
    if measure <= tol.reproduced_within:
        return Verdict.REPRODUCED
    if measure <= tol.partial_within:
        return Verdict.PARTIAL
    return Verdict.FAILED


def _assemble(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    method: ComparisonMethod,
    measure: float,
    discrepancy: str,
    tol: Tolerance,
    reference_kind: ReferenceKind,
    attribution: Attribution | None,
    assumption_qualified: bool,
    level: ReproductionLevel = ReproductionLevel.SIMULATION,
) -> ClaimAssessment:
    verdict = verdict_for(measure, tol)
    if verdict in (Verdict.PARTIAL, Verdict.FAILED):
        if attribution is None:
            raise ValueError("a partial or failed verdict must carry a root-cause attribution")
        root_cause: str | None = attribution.mode.value
        implicated: str | None = attribution.implicated
        fault: str | None = attribution.fault.value
    else:
        root_cause = implicated = fault = None
    return ClaimAssessment(
        claim_id=claim_id,
        quantity=quantity,
        verdict=verdict,
        source_location=source_location,
        level=level,
        method=method.value,
        tolerance=tol.label(),
        tolerance_source=tol.source.value,
        discrepancy=discrepancy,
        root_cause=root_cause,
        implicated=implicated,
        fault_hypothesis=fault,
        reference_kind=reference_kind.value,
        assumption_qualified=assumption_qualified,
    )


def judge_scalar(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: float,
    predicted: float,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    tolerance: Tolerance | None = None,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a scalar PK/PD metric (AUC, Cmax, clearance, half-life, …) by relative error.

    Uses the documented class default when ``tolerance`` is unset. A ``partial`` or ``failed``
    outcome requires an ``attribution`` (category + implicated element + fault hypothesis).
    """
    tol = tolerance or default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, reference_kind)
    err = relative_error(reported, predicted)
    return _assemble(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        method=ComparisonMethod.SCALAR_RELATIVE_ERROR,
        measure=err,
        discrepancy=f"relative error {err:.4f}",
        tol=tol,
        reference_kind=reference_kind,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def judge_estimation(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: float,
    recovered: float,
    tolerance: Tolerance | None = None,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge an *estimation* claim: a parameter estimate re-derived by re-fitting from raw data.

    This is the second, stronger level of reproduction (spec: simulation-oracle — "Estimation
    reproduction is a distinct verdict"). It is attempted only when the paper ships the raw data
    to re-fit against; the re-fitting itself — running the paper's stated estimation to recover
    an estimate — is the deferred, engine-dependent half, exactly as the simulator is for
    :func:`judge_scalar`. Given an already-``recovered`` estimate, this compares it to the
    paper's ``reported`` estimate by relative error and records the verdict at
    ``ReproductionLevel.ESTIMATION`` so it is reported separately from simulation reproduction.

    Uses the documented estimation-class default (wider than a simulation scalar, because a
    re-fit is sensitive to the optimizer and its starting values) when ``tolerance`` is unset. A
    ``partial`` or ``failed`` outcome requires an ``attribution``.
    """
    tol = tolerance or _ESTIMATION_DEFAULT
    err = relative_error(reported, recovered)
    return _assemble(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        method=ComparisonMethod.SCALAR_RELATIVE_ERROR,
        measure=err,
        discrepancy=f"relative error {err:.4f}",
        tol=tol,
        reference_kind=ReferenceKind.NUMERIC,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
        level=ReproductionLevel.ESTIMATION,
    )


def judge_curve(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reference: Sequence[float],
    predicted: Sequence[float],
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    tolerance: Tolerance | None = None,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a sampled concentration/effect-time curve by normalized distance.

    Uses the documented class default when ``tolerance`` is unset. A ``partial`` or ``failed``
    outcome requires an ``attribution``.
    """
    tol = tolerance or default_tolerance(
        ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind
    )
    dist = normalized_curve_distance(reference, predicted)
    return _assemble(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        method=ComparisonMethod.CURVE_NORMALIZED_DISTANCE,
        measure=dist,
        discrepancy=f"normalized distance {dist:.4f}",
        tol=tol,
        reference_kind=reference_kind,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def judge_distribution(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reference: Sequence[PercentileBand],
    predicted: Sequence[PercentileBand],
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    tolerance: Tolerance | None = None,
    attribution: Attribution | None = None,
    assumption_qualified: bool = True,
) -> ClaimAssessment:
    """Judge a population envelope claim by its worst-matched percentile band.

    A population figure (a percentile envelope or prediction interval over time) is compared
    band-for-band; the verdict is governed by the worst-matched band so a good median cannot
    mask a divergent tail. Uses the documented distributional class default when ``tolerance``
    is unset — wider than a single trajectory's to absorb population sampling error.

    ``assumption_qualified`` defaults to ``True``: reproducing a population depends on the
    reconstructed between-subject variability model and the sampling, load-bearing assumptions
    a manuscript often under-specifies, so the verdict is qualified unless the caller states the
    variability model was fully specified and the sampling made deterministic (spec:
    simulation-oracle — "Population reproduction is a qualified verdict"). A ``partial`` or
    ``failed`` outcome still requires an ``attribution``.

    A single variability *scalar* (a CV%, a between-subject SD, one percentile value) is not an
    envelope; judge it with :func:`judge_scalar` by relative error.
    """
    tol = tolerance or default_tolerance(
        ComparisonMethod.DISTRIBUTION_BAND_DISTANCE, reference_kind
    )
    distance, worst_band = band_envelope_distance(reference, predicted)
    return _assemble(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        method=ComparisonMethod.DISTRIBUTION_BAND_DISTANCE,
        measure=distance,
        discrepancy=f"worst band {worst_band.label()} normalized distance {distance:.4f}",
        tol=tol,
        reference_kind=reference_kind,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def assess_match(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    matched: bool,
    method: ComparisonMethod,
    discrepancy: str,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Assemble a pass/fail assessment for a comparison that is a match-or-not, not a scalar error.

    Some reproductions are judged by whether two structured objects agree (a standardized
    fingerprint, a set of deletion outcomes), not by a numeric distance. This maps that boolean to
    the shared assessment contract — ``matched`` reproduces, otherwise it fails — so such a verdict
    carries the same tolerance provenance and attribution invariant as a scalar one. A non-match
    still requires an ``attribution``.
    """
    tol = Tolerance(0.0, 0.0, ToleranceSource.CLASS_DEFAULT)
    return _assemble(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        method=method,
        measure=0.0 if matched else 1.0,
        discrepancy=discrepancy,
        tol=tol,
        reference_kind=reference_kind,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def not_evaluable(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reason: str,
    reference_kind: ReferenceKind = ReferenceKind.DIGITIZED_FIGURE,
) -> ClaimAssessment:
    """Abstain on a claim whose reference is unusable, rather than guess a pass or fail.

    Used when there is no numeric data and no digitizable figure to compare against; the
    abstention keeps the agreement metric meaningful (design D2).
    """
    return ClaimAssessment(
        claim_id=claim_id,
        quantity=quantity,
        verdict=Verdict.NOT_EVALUABLE,
        source_location=source_location,
        discrepancy=None,
        root_cause=reason,
        reference_kind=reference_kind.value,
    )


__all__ = [
    "Attribution",
    "ComparisonMethod",
    "Fault",
    "FailureMode",
    "PercentileBand",
    "ReferenceKind",
    "Tolerance",
    "ToleranceSource",
    "assess_match",
    "band_envelope_distance",
    "default_tolerance",
    "judge_curve",
    "judge_distribution",
    "judge_estimation",
    "judge_scalar",
    "normalized_curve_distance",
    "not_evaluable",
    "relative_error",
    "verdict_for",
]
