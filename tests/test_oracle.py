"""The simulation oracle's comparison core (bootstrap tasks 4.1-4.5)."""

from __future__ import annotations

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
    assert relative_error(0.0, 3.0) == 3.0  # zero reference falls back to absolute
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
