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
from collections.abc import Iterable, Sequence
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
    # Weaker than a set match, and named so: two networks can agree on how many attractors they
    # have, and on the length of each, while sharing not one state between them. A reference that
    # reports counts and periods rather than the attractors themselves can only support this.
    ATTRACTOR_SIGNATURE_MATCH = "attractor-signature-match"


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
    # Stochastic (SSA) root causes: a mean judged from a finite ensemble misses by chance at a
    # rate the ensemble size sets, which is a cause of the shortfall and not a fault in either
    # the paper or the model.
    FINITE_ENSEMBLE_SAMPLING = "finite-ensemble-sampling-noise"
    # Escape hatch for a failure fitting none of the above (spec: "recorded as uncategorized").
    UNCATEGORIZED = "uncategorized"


class Fault(str, Enum):
    """Whether a shortfall looks more like the paper's fault or the reconstruction's.

    Always a hypothesis, never a proven cause (spec: "Distinguishing paper fault from
    reconstruction fault").
    """

    MANUSCRIPT = "manuscript"
    RECONSTRUCTION = "reconstruction"


# The documented class-default thresholds, listed here rather than derived from the table below
# because the table is built out of Tolerance instances that this validation runs against.
_DEFAULT_THRESHOLDS = frozenset(
    {
        (0.05, 0.15), (0.15, 0.30), (0.10, 0.25), (0.20, 0.40), (0.15, 0.35), (0.25, 0.50),
        (0.0, 0.0),  # an exact match (an attractor set, a FROG fingerprint) has no slack to declare
    }
)


@dataclass(frozen=True)
class Tolerance:
    """A declared pass/partial threshold with its provenance.

    A measured discrepancy at or below ``reproduced_within`` is ``reproduced``; at or below
    ``partial_within`` is ``partial``; above it is ``failed``. Any non-default tolerance must
    state a rationale — a paper-stated precision or a reviewer's reason — so no threshold is a
    magic number.

    A tolerance may only *call itself* a class default if its thresholds are one of the documented
    defaults below. Otherwise the rationale requirement is trivially escaped: declare any width you
    like as ``class-default``, and the certificate reports a 900% error as reproduced under a
    provenance that reads like a considered decision nobody has to justify.
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
        thresholds = (self.reproduced_within, self.partial_within)
        if self.source is ToleranceSource.CLASS_DEFAULT and thresholds not in _DEFAULT_THRESHOLDS:
            raise ValueError(
                f"{thresholds} is not one of the documented class defaults; a tolerance this "
                "wide or narrow is a paper-stated or reviewer-override choice and must state "
                "its rationale"
            )

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


def estimation_default_tolerance() -> Tolerance:
    """The documented estimation-level default tolerance (wider than a simulation scalar's)."""
    return _ESTIMATION_DEFAULT


def relative_error(reported: float, predicted: float, *, zero_scale: float | None = None) -> float:
    """Relative error of ``predicted`` against the ``reported`` value.

    Normalized by the reported magnitude. A reported value of exactly zero has no magnitude to
    normalize by, so it needs a ``zero_scale`` — the size the claim is zero *relative to* (a
    wild-type growth rate, the numerical width of a pinned flux interval). With one, the error is
    the prediction as a fraction of that scale; without one, the comparison is not defined and the
    caller is expected to abstain rather than compare (:func:`judge_scalar` does).

    It used to fall back to the bare absolute difference, which silently made the verdict a
    function of the claim's units: a knockout the paper calls lethal, against a model growing at
    0.05 1/h, read as a 0.05 "relative error" and certified as reproduced — while the identical
    claim stated in 1/day failed. A unitless tolerance cannot be compared against a raw magnitude.
    """
    if reported == 0.0:
        if predicted == 0.0:
            return 0.0  # exact agreement needs no scale
        if zero_scale is None or zero_scale == 0.0:
            raise ValueError(
                "a reported value of zero has no magnitude to judge a relative error against; "
                "state the scale it is zero relative to (zero_scale)"
            )
        return abs(predicted) / abs(zero_scale)
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


def worst_point_deviation(reference: Sequence[float], predicted: Sequence[float]) -> float:
    """The largest single-point gap between two aligned curves, as a fraction of the reference span.

    The companion to :func:`normalized_curve_distance`, and the reason it is needed: an RMSE is an
    average, so a localized miss is divided by the sample count. The error a single point may carry
    while the RMSE stays under a threshold ``t`` is ``t·√N`` times the span — half the span at 25
    samples, the whole span at 100, three times it at 1000. Measured on a 201-point PK curve, a
    reconstruction whose Cmax is *twice* the paper's scores 0.0705 and reads as a clean
    reproduction, and Cmax is exactly what such a paper reports. Worse, the sample count is the
    reconstruction's own choice, so sampling more finely buys tolerance for the peak.

    Normalized the same way the RMSE is, so the two are comparable and a tolerance means the same
    kind of thing against both.
    """
    if len(reference) != len(predicted):
        raise ValueError("reference and predicted must be sampled at the same points")
    if not reference:
        raise ValueError("need at least one sample point")
    n = len(reference)
    worst = max(abs(p - r) for r, p in zip(reference, predicted))
    span = max(reference) - min(reference)
    if span == 0.0:
        span = abs(sum(reference) / n)
    if span == 0.0:
        return 0.0 if worst == 0.0 else float("inf")
    return worst / span


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

    A NaN band distance — a diverged tail — is the worst case, not a skipped one. Comparisons
    against NaN are all false, so a running maximum seeded with a sentinel would step over exactly
    the band that failed and report the best-matched tail instead, inverting the rule this function
    exists to enforce.
    """
    if not reference or not predicted:
        raise ValueError("both envelopes need at least one percentile band")
    ref_by_pct = {b.percentile: b for b in reference}
    pred_by_pct = {b.percentile: b for b in predicted}
    if len(ref_by_pct) != len(reference) or len(pred_by_pct) != len(predicted):
        raise ValueError("percentiles within an envelope must be distinct")
    if ref_by_pct.keys() != pred_by_pct.keys():
        raise ValueError("reference and predicted envelopes must cover the same percentiles")
    worst_distance: float | None = None
    worst_band = reference[0]
    for pct in sorted(ref_by_pct):
        ref_band, pred_band = ref_by_pct[pct], pred_by_pct[pct]
        distance = normalized_curve_distance(ref_band.curve, pred_band.curve)
        if worst_distance is None or math.isnan(distance) or distance > worst_distance:
            worst_distance, worst_band = distance, ref_band
        if math.isnan(worst_distance):
            break
    assert worst_distance is not None  # the envelopes are non-empty and cover the same percentiles
    return worst_distance, worst_band


def _non_finite_abstention(
    values: Iterable[float],
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reference_kind: ReferenceKind,
    level: ReproductionLevel = ReproductionLevel.SIMULATION,
) -> ClaimAssessment | None:
    """Abstain when any value feeding the comparison is non-finite, else ``None``.

    A NaN or infinity among the reconstruction's output (a diverging integrator, a stiff blow-up)
    or the reference means there is nothing meaningful to compare. Left to the numeric path a NaN
    would silently classify as ``failed`` (``NaN <= tol`` is ``False``) and then demand a root-cause
    attribution it has no basis for — turning an un-judgeable run into either a crash or a
    mislabeled, misattributed failure. The honest verdict is ``not-evaluable``: the run produced no
    comparable value, which is not the same as producing a wrong one.
    """
    if all(math.isfinite(v) for v in values):
        return None
    return not_evaluable(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        reason="the reconstruction produced non-finite output; the run did not converge to a comparable value",
        reference_kind=reference_kind,
        level=level,
    )


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


def _require_default_is_the_default(
    tol: Tolerance,
    method: ComparisonMethod,
    reference_kind: ReferenceKind,
    level: ReproductionLevel,
) -> None:
    """Refuse a ``class-default`` tolerance that is not *this* comparison's documented default.

    :class:`Tolerance` can only check membership in the flat set of every documented pair, because
    it does not know which comparison it is for. That is not enough: the widest pair in the table
    (a digitized-figure population envelope, 0.25/0.50) is a documented default, so a plain numeric
    scalar claim could adopt it and certify a 24% relative error as ``reproduced`` under a
    provenance reading ``class-default`` — the exact escape the rationale requirement exists to
    close. Here both the method and the reference kind are known, so the default is exactly one
    pair. An exact comparison (an attractor signature, a FROG fingerprint) has no entry in the
    table and is held to 0/0.
    """
    if tol.source is not ToleranceSource.CLASS_DEFAULT:
        return
    if level is ReproductionLevel.ESTIMATION:
        expected: Tolerance | None = _ESTIMATION_DEFAULT
    else:
        expected = _DEFAULTS.get((method, reference_kind))
    allowed = (
        (expected.reproduced_within, expected.partial_within) if expected else (0.0, 0.0)
    )
    if (tol.reproduced_within, tol.partial_within) != allowed:
        raise ValueError(
            f"{(tol.reproduced_within, tol.partial_within)} is not the class default for "
            f"{method.value} against a {reference_kind.value} reference (that is {allowed}); "
            "a different width is a paper-stated or reviewer-override choice and must state "
            "its rationale"
        )


def undetermined_shortfall(quantity: str) -> Attribution:
    """The root cause for a non-pass whose cause has not been determined.

    A partial or failed verdict must carry an attribution, which is right: a certificate that says
    "did not reproduce" and nothing else tells the field nothing. But the requirement was enforced
    by *raising* when a caller supplied none, and a class front-end that has no cause to supply
    then cannot publish a true negative at all — its only outcomes are a pass or a traceback, and
    the agreement rate it reports is guaranteed rather than measured.

    So an unattributed shortfall is recorded as one: ``uncategorized`` (the catalogue's own escape
    hatch, which flags the set to be extended) against the claim's quantity, with the fault
    hypothesis pointing at the *reconstruction*. That direction is deliberate — Reprolith does not
    accuse a manuscript of an error it has not diagnosed, and the humble hypothesis is that the
    thing it built is what fell short. A caller that knows better supplies its own attribution and
    this is never reached.
    """
    return Attribution(
        mode=FailureMode.UNCATEGORIZED, implicated=quantity, fault=Fault.RECONSTRUCTION
    )


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
    tolerance_label: str | None = None,
) -> ClaimAssessment:
    _require_default_is_the_default(tol, method, reference_kind, level)
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
        tolerance=tolerance_label or tol.label(),
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
    zero_scale: float | None = None,
) -> ClaimAssessment:
    """Judge a scalar PK/PD metric (AUC, Cmax, clearance, half-life, …) by relative error.

    Uses the documented class default when ``tolerance`` is unset. A ``partial`` or ``failed``
    outcome requires an ``attribution`` (category + implicated element + fault hypothesis).

    A *reported zero* — a knockout the paper calls lethal, a flux it says carries nothing — has no
    magnitude for a relative tolerance to mean anything against. An exactly-zero prediction is exact
    agreement and passes; anything else is judged as a fraction of ``zero_scale``, the size the
    claim is zero relative to, and without that scale the claim abstains. It used to fall back to
    the absolute difference, which made the verdict depend on the claim's units: a model growing at
    0.05 1/h passed a lethality claim as a "5% error", and the same claim in 1/day failed.
    """
    abstention = _non_finite_abstention(
        (reported, predicted), claim_id=claim_id, quantity=quantity,
        source_location=source_location, reference_kind=reference_kind,
    )
    if abstention is not None:
        return abstention
    tol = tolerance or default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, reference_kind)
    if reported == 0.0 and predicted != 0.0 and zero_scale is None:
        return not_evaluable(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reason=(
                f"the reported value is zero and the run gives {predicted:.6g}, so there is no "
                "magnitude to judge a relative error against; the claim needs the scale it is "
                "zero relative to (e.g. the unperturbed value) before a verdict means anything"
            ),
            reference_kind=reference_kind,
        )
    err = relative_error(reported, predicted, zero_scale=zero_scale)
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
    abstention = _non_finite_abstention(
        (reported, recovered), claim_id=claim_id, quantity=quantity,
        source_location=source_location, reference_kind=ReferenceKind.NUMERIC,
        level=ReproductionLevel.ESTIMATION,
    )
    if abstention is not None:
        return abstention
    tol = tolerance or _ESTIMATION_DEFAULT
    if reported == 0.0 and recovered != 0.0:
        # The same abstention `judge_scalar` makes: a reported zero has no magnitude for a
        # relative tolerance, and an estimation claim can report one (a rate constant a paper
        # fits to zero). Without this the judge raised where its sibling abstains.
        return not_evaluable(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reason=(
                f"the reported estimate is zero and the re-fit recovered {recovered:.6g}, so there "
                "is no magnitude to judge a relative error against; the claim needs the scale it "
                "is zero relative to before a verdict means anything"
            ),
            reference_kind=ReferenceKind.NUMERIC,
            level=ReproductionLevel.ESTIMATION,
        )
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
    abstention = _non_finite_abstention(
        (*reference, *predicted), claim_id=claim_id, quantity=quantity,
        source_location=source_location, reference_kind=reference_kind,
    )
    if abstention is not None:
        return abstention
    tol = tolerance or default_tolerance(
        ComparisonMethod.CURVE_NORMALIZED_DISTANCE, reference_kind
    )
    dist = normalized_curve_distance(reference, predicted)
    worst = worst_point_deviation(reference, predicted)
    # The verdict answers to both statistics: the average agreement, and the worst single point.
    # The worst point's budget is the tolerance's own *partial* threshold — the width it already
    # calls tolerable — rescaled onto the pass threshold so one number governs. No new constant is
    # introduced, and on the committed corpus the worst point runs 2.2x-9x the RMSE ratio with
    # both under 1e-3, so nothing that genuinely reproduces comes near the bound.
    scaled_worst = (
        worst * (tol.reproduced_within / tol.partial_within) if tol.partial_within > 0.0 else worst
    )
    measure = max(dist, scaled_worst)
    return _assemble(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        method=ComparisonMethod.CURVE_NORMALIZED_DISTANCE,
        measure=measure,
        discrepancy=(
            # Named as the *pass* budget, because that is what it is: a worst point under it
            # contributes a clean pass, and one above it is judged on the same partial/failed
            # scale as the average. Calling it "the budget" read as a bound the verdict honoured,
            # so a `partial` could report a worst point of 0.62 against a "budget" of 0.25.
            f"normalized distance {dist:.4f}, worst point {worst:.4f} of span "
            f"(pass budget {tol.partial_within:.4f})"
        ),
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
    abstention = _non_finite_abstention(
        (*(v for b in reference for v in b.curve), *(v for b in predicted for v in b.curve)),
        claim_id=claim_id, quantity=quantity,
        source_location=source_location, reference_kind=reference_kind,
    )
    if abstention is not None:
        return abstention
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
    exact_on: str | None = None,
) -> ClaimAssessment:
    """Assemble a pass/fail assessment for a comparison that is a match-or-not, not a scalar error.

    Some reproductions are judged by whether two structured objects agree (a standardized
    fingerprint, a set of deletion outcomes), not by a numeric distance. This maps that boolean to
    the shared assessment contract — ``matched`` reproduces, otherwise it fails — so such a verdict
    carries the same tolerance provenance and attribution invariant as a scalar one. A non-match
    still requires an ``attribution``.

    ``exact_on`` names *what* agreed exactly, and is how the certificate should state it. Without
    it the tolerance renders as ``reproduced<=0, partial<=0``, which a reader takes for an exact
    match of the whole quantity — but a boolean comparison is only ever exact on the projection it
    compared, and a zero written in the tolerance column cannot say which projection that was.
    """
    tol = Tolerance(0.0, 0.0, ToleranceSource.CLASS_DEFAULT)
    return _assemble(
        tolerance_label=f"exact match on {exact_on}" if exact_on else None,
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
    level: ReproductionLevel = ReproductionLevel.SIMULATION,
) -> ClaimAssessment:
    """Abstain on a claim whose reference is unusable, rather than guess a pass or fail.

    Used when there is no numeric data and no digitizable figure to compare against; the
    abstention keeps the agreement metric meaningful (design D2).

    ``level`` travels because an abstention is still a claim of a kind: an estimation claim that
    could not be judged was being filed at simulation level, so the surfaces that treat estimation
    separately — the never-green badge, the machine summary, the gap report — did not see it.
    """
    return ClaimAssessment(
        claim_id=claim_id,
        quantity=quantity,
        verdict=Verdict.NOT_EVALUABLE,
        source_location=source_location,
        discrepancy=None,
        root_cause=reason,
        reference_kind=reference_kind.value,
        level=level,
    )


__all__ = [
    "undetermined_shortfall",
    "worst_point_deviation",
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
    "estimation_default_tolerance",
    "judge_curve",
    "judge_distribution",
    "judge_estimation",
    "judge_scalar",
    "normalized_curve_distance",
    "not_evaluable",
    "relative_error",
    "verdict_for",
]
