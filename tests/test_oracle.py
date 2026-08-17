"""The simulation oracle's comparison core (bootstrap tasks 4.1-4.5)."""

from __future__ import annotations

import math

import pytest
from reprolith import (
    Attribution,
    FailureMode,
    Fault,
    ReferenceKind,
    Tolerance,
    ToleranceSource,
    Verdict,
    judge_curve,
    judge_scalar,
    normalized_curve_distance,
    not_evaluable,
    relative_error,
    verdict_for,
)

_SHORTFALL = Attribution(
    mode=FailureMode.AMBIGUOUS_INITIAL_CONDITION,
    implicated="initial gut amount (dossier param A0)",
    fault=Fault.MANUSCRIPT,
)


# --- 4.1 curve and scalar comparison against declared tolerances -------------------


def test_known_good_scalar_reproduces_and_perturbed_fails() -> None:
    good = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Table 2", reported=100.0, predicted=101.0
    )
    assert good.verdict is Verdict.REPRODUCED  # 1% error, within 5% default

    bad = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Table 2",
        reported=100.0, predicted=180.0, attribution=_SHORTFALL,  # 80% error
    )
    assert bad.verdict is Verdict.FAILED


def test_scalar_partial_band() -> None:
    mid = judge_scalar(
        claim_id="c", quantity="Cmax", source_location="Fig 1",
        reported=100.0, predicted=110.0, attribution=_SHORTFALL,  # 10% -> partial band
    )
    assert mid.verdict is Verdict.PARTIAL


def test_known_good_curve_reproduces_and_perturbed_fails() -> None:
    reference = [1.0, 2.0, 4.0, 8.0, 4.0, 2.0]
    good = judge_curve(
        claim_id="c", quantity="C(t)", source_location="Fig 3",
        reference=reference, predicted=[1.02, 1.98, 4.05, 7.9, 4.1, 1.95],
    )
    assert good.verdict is Verdict.REPRODUCED

    bad = judge_curve(
        claim_id="c", quantity="C(t)", source_location="Fig 3",
        reference=reference, predicted=[1.0, 2.0, 4.0, 2.0, 8.0, 6.0], attribution=_SHORTFALL,
    )
    assert bad.verdict is Verdict.FAILED


def test_comparison_helpers_are_correct() -> None:
    assert relative_error(100.0, 110.0) == pytest.approx(0.10)
    # A reported zero has no magnitude to normalize by. Exact agreement passes; anything else is
    # judged against the scale the claim is zero relative to, and refuses without one — an
    # absolute fallback made the verdict a function of the claim's units.
    assert relative_error(0.0, 0.0) == 0.0
    assert relative_error(0.0, 3.0, zero_scale=60.0) == pytest.approx(0.05)
    with pytest.raises(ValueError, match="no magnitude"):
        relative_error(0.0, 3.0)
    assert normalized_curve_distance([0.0, 10.0], [0.0, 10.0]) == 0.0
    assert normalized_curve_distance([0.0, 10.0], [1.0, 11.0]) == pytest.approx(0.1)


def test_verdict_for_classifies_against_tolerance() -> None:
    tol = Tolerance(0.10, 0.25, ToleranceSource.CLASS_DEFAULT)
    assert verdict_for(0.05, tol) is Verdict.REPRODUCED
    assert verdict_for(0.20, tol) is Verdict.PARTIAL
    assert verdict_for(0.40, tol) is Verdict.FAILED


# --- 4.2 class-default tolerances and principled overrides -------------------------


def test_default_tolerance_is_recorded_when_unset() -> None:
    a = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Table 2", reported=100.0, predicted=101.0
    )
    assert a.tolerance_source == "class-default"
    assert "class-default" in a.tolerance


def test_figure_reference_widens_the_default_tolerance() -> None:
    # A 12% error is partial against numeric (5%/15%), but a digitized figure's wider band
    # (15%/30%) treats the same error as reproduced.
    numeric_j = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Fig 2",
        reported=100.0, predicted=112.0, attribution=_SHORTFALL,
    )
    figure_j = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Fig 2",
        reported=100.0, predicted=112.0, reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    assert numeric_j.verdict is Verdict.PARTIAL
    assert figure_j.verdict is Verdict.REPRODUCED
    assert figure_j.reference_kind == "digitized-figure"


def test_override_without_rationale_is_rejected() -> None:
    with pytest.raises(ValueError):
        Tolerance(0.05, 0.15, ToleranceSource.REVIEWER_OVERRIDE)  # no rationale
    # With a rationale it is accepted and recorded as an override.
    tol = Tolerance(0.02, 0.05, ToleranceSource.REVIEWER_OVERRIDE, rationale="paper reports 2% CV")
    a = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Table 2",
        reported=100.0, predicted=101.0, tolerance=tol,
    )
    assert a.tolerance_source == "reviewer-override"


def test_invalid_tolerance_bounds_rejected() -> None:
    with pytest.raises(ValueError):
        Tolerance(0.30, 0.10, ToleranceSource.CLASS_DEFAULT)  # reproduced > partial


# --- 4.3 not-evaluable abstention --------------------------------------------------


def test_figure_only_claim_without_data_abstains() -> None:
    a = not_evaluable(
        claim_id="c", quantity="terminal half-life", source_location="Fig 4",
        reason="figure has no digitizable reference data",
    )
    assert a.verdict is Verdict.NOT_EVALUABLE
    assert a.discrepancy is None  # it abstains rather than manufacturing a number
    assert "no digitizable" in a.root_cause


def test_non_finite_reconstruction_output_abstains_rather_than_failing() -> None:
    # A diverging integrator yields NaN/inf. Left to the numeric path that classifies as `failed`
    # (NaN <= tol is False) and then demands a root-cause attribution it has no basis for — so with
    # no attribution the judge used to raise, and with one it manufactured a misattributed failure.
    # The honest verdict is not-evaluable: the run produced no comparable value.
    curve = judge_curve(
        claim_id="c", quantity="concentration", source_location="T1",
        reference=[1.0, 2.0, 3.0], predicted=[1.0, float("nan"), 3.0],
    )
    assert curve.verdict is Verdict.NOT_EVALUABLE
    assert curve.discrepancy is None and "non-finite" in curve.root_cause

    scalar = judge_scalar(
        claim_id="c", quantity="Cmax", source_location="T1",
        reported=10.0, predicted=float("inf"),
    )
    assert scalar.verdict is Verdict.NOT_EVALUABLE

    # A finite comparison is unaffected: a genuine mismatch is still judged, not abstained.
    good = judge_scalar(
        claim_id="c", quantity="Cmax", source_location="T1", reported=10.0, predicted=10.2
    )
    assert good.verdict is Verdict.REPRODUCED


# --- 4.4 root-cause attribution with implicated element and fault hypothesis --------


def test_non_pass_carries_category_and_implicated_element() -> None:
    a = judge_scalar(
        claim_id="c", quantity="Cmax", source_location="Fig 1",
        reported=100.0, predicted=180.0,
        attribution=Attribution(
            mode=FailureMode.UNIT_MISMATCH, implicated="dose units (mg vs mg/kg)",
            fault=Fault.MANUSCRIPT,
        ),
    )
    assert a.verdict is Verdict.FAILED
    assert a.root_cause == "unit-mismatch"
    assert a.implicated == "dose units (mg vs mg/kg)"
    assert a.fault_hypothesis == "manuscript"  # a hypothesis, paper vs reconstruction


def test_non_pass_without_attribution_is_rejected() -> None:
    with pytest.raises(ValueError):
        judge_scalar(
            claim_id="c", quantity="Cmax", source_location="Fig 1",
            reported=100.0, predicted=180.0,  # would fail, but no attribution supplied
        )


def test_clean_pass_has_no_root_cause() -> None:
    a = judge_scalar(
        claim_id="c", quantity="AUC", source_location="Table 2", reported=100.0, predicted=100.0
    )
    assert a.root_cause is None and a.implicated is None and a.fault_hypothesis is None


# --- 4.5 determinism of verdict and discrepancy ------------------------------------


def test_repeated_evaluation_is_identical() -> None:
    def run():
        return judge_curve(
            claim_id="c", quantity="C(t)", source_location="Fig 3",
            reference=[1.0, 2.0, 4.0, 8.0], predicted=[1.1, 2.2, 3.7, 8.4],
            attribution=_SHORTFALL,
        )

    a, b = run(), run()
    assert a == b  # frozen dataclass equality: verdict, discrepancy, everything
    assert a.discrepancy == b.discrepancy


def test_a_diverged_band_governs_the_envelope_instead_of_being_skipped() -> None:
    """NaN comparisons are all false, so a running maximum must not step over a diverged tail."""
    from reprolith import PercentileBand, band_envelope_distance

    ref = (
        PercentileBand(5.0, (0.4, 0.9, 1.6)),
        PercentileBand(50.0, (1.0, 2.0, 3.6)),
        PercentileBand(95.0, (1.8, 3.4, 6.0)),
    )
    # The reconstruction's upper tail diverged; the median and lower band match exactly.
    nan = float("nan")
    predicted = (ref[0], ref[1], PercentileBand(95.0, (nan, nan, nan)))
    distance, worst = band_envelope_distance(ref, predicted)
    assert math.isnan(distance)  # never a clean 0.0, and never the -1.0 sentinel
    assert worst.percentile == 95.0


def test_a_tolerance_may_not_call_itself_a_class_default_unless_it_is_one() -> None:
    """Otherwise the rationale requirement is trivially escaped by relabelling the provenance."""
    from reprolith import Tolerance, ToleranceSource

    with pytest.raises(ValueError, match="not one of the documented class defaults"):
        Tolerance(10.0, 10.0, ToleranceSource.CLASS_DEFAULT)
    # The same width is fine when it is declared as the judgment call it is.
    wide = Tolerance(10.0, 10.0, ToleranceSource.REVIEWER_OVERRIDE, rationale="order-of-magnitude check")
    assert wide.label().endswith("(reviewer-override)")


def test_a_class_default_tolerance_must_be_this_comparisons_default() -> None:
    # Tolerance alone can only check membership in the flat set of every documented default, so the
    # widest pair in the table (a digitized-figure population envelope) could be adopted by a plain
    # numeric scalar claim: a 24% relative error certified `reproduced` under a provenance reading
    # `class-default`, which is exactly the escape the rationale requirement exists to close.
    import pytest
    from reprolith.oracle import Tolerance, ToleranceSource, judge_scalar

    widest = Tolerance(0.25, 0.50, ToleranceSource.CLASS_DEFAULT)
    with pytest.raises(ValueError, match="not the class default"):
        judge_scalar(claim_id="c1", quantity="Cmax", source_location="Table 1",
                     reported=100.0, predicted=124.0, tolerance=widest)
    # The same width is fine once it is declared for what it is, with a reason.
    stated = Tolerance(0.25, 0.50, ToleranceSource.PAPER_STATED,
                       rationale="the paper reports Cmax to one significant figure")
    assessment = judge_scalar(claim_id="c1", quantity="Cmax", source_location="Table 1",
                              reported=100.0, predicted=124.0, tolerance=stated)
    assert assessment.verdict.value == "reproduced"
    assert assessment.tolerance_source == "paper-stated"


def test_a_localized_miss_is_not_averaged_into_a_pass() -> None:
    """An RMSE divides a single bad point by the sample count, and the sampler picks the count.

    Measured on a 201-point one-compartment PK curve, a reconstruction whose Cmax is *twice* the
    paper's scores a normalized distance of 0.0705 — a clean pass under the 10% curve default —
    because 200 well-matched points absorb it. Cmax is exactly what such a paper reports, and
    sampling more finely buys more room for the peak, so the verdict has to answer to the worst
    point as well as to the average.
    """
    import math

    from reprolith import worst_point_deviation

    times = [i * 0.1 for i in range(201)]
    reference = [100 * math.exp(-0.3 * t) * (1 - math.exp(-1.5 * t)) for t in times]
    doubled_peak = list(reference)
    peak = max(range(len(reference)), key=lambda i: reference[i])
    doubled_peak[peak] *= 2.0

    # The average alone still calls it a pass; the worst point is a full span out.
    assert normalized_curve_distance(reference, doubled_peak) == pytest.approx(0.0705, abs=5e-4)
    assert worst_point_deviation(reference, doubled_peak) == pytest.approx(1.0, abs=1e-3)

    verdict = judge_curve(
        claim_id="c", quantity="plasma concentration", source_location="Fig 1",
        reference=reference, predicted=doubled_peak,
        attribution=Attribution(
            mode=FailureMode.UNCATEGORIZED, implicated="peak", fault=Fault.RECONSTRUCTION
        ),
    )
    assert verdict.verdict is Verdict.FAILED
    assert "worst point" in verdict.discrepancy

    # A curve that is uniformly 2% high still reproduces: the guard is about localized misses,
    # and on the committed corpus the worst point runs 2.2x-9x the RMSE ratio with both under 1e-3.
    uniform = judge_curve(
        claim_id="c", quantity="plasma concentration", source_location="Fig 1",
        reference=reference, predicted=[v * 1.02 for v in reference],
    )
    assert uniform.verdict is Verdict.REPRODUCED
