"""Estimation reproduction — re-fit from raw data (roadmap #8).

The stronger, level-2 reproduction: when a paper ships the raw data, re-fit the model and check
the *reported parameter estimates*, not just the shown curve. The re-fitting itself is the
deferred, engine-dependent half; the judge here compares an already-recovered estimate to the
paper's reported one, at ``ReproductionLevel.ESTIMATION``, reported separately (spec:
simulation-oracle — "Estimation reproduction is a distinct verdict").
"""

from __future__ import annotations

import pytest
from reprolith import (
    Attribution,
    EnginePin,
    FailureMode,
    Fault,
    PaperIdentity,
    ReproductionLevel,
    Tolerance,
    ToleranceSource,
    Verdict,
    build_certificate,
    judge_estimation,
    judge_scalar,
)

_SHORTFALL = Attribution(
    mode=FailureMode.UNSTATED_STARTING_VALUES,
    implicated="clearance estimate (paper omits optimizer starting values)",
    fault=Fault.MANUSCRIPT,
)


def test_recovered_estimate_matching_report_reproduces_at_estimation_level() -> None:
    a = judge_estimation(
        claim_id="c", quantity="CL/F estimate", source_location="Table 3",
        reported=3.20, recovered=3.30,  # ~3% off, inside the 10% estimation default
    )
    assert a.verdict is Verdict.REPRODUCED
    assert a.level is ReproductionLevel.ESTIMATION  # reported separately from simulation


def test_estimation_default_is_wider_than_a_simulation_scalar() -> None:
    # An 8% miss: failed as a simulation scalar (5%/15% -> partial actually), but the estimation
    # default (10%/25%) treats the same miss as reproduced, reflecting re-fit sensitivity.
    reported, recovered = 100.0, 108.0
    sim = judge_scalar(
        claim_id="c", quantity="CL", source_location="Table 3",
        reported=reported, predicted=recovered, attribution=_SHORTFALL,
    )
    est = judge_estimation(
        claim_id="c", quantity="CL", source_location="Table 3",
        reported=reported, recovered=recovered,
    )
    assert sim.verdict is Verdict.PARTIAL  # 8% is partial under the 5%/15% simulation default
    assert est.verdict is Verdict.REPRODUCED  # but reproduced under the 10%/25% estimation default


def test_poor_refit_fails_with_estimation_specific_cause() -> None:
    a = judge_estimation(
        claim_id="c", quantity="Vc estimate", source_location="Table 3",
        reported=10.0, recovered=18.0,  # 80% off
        attribution=Attribution(
            mode=FailureMode.LOCAL_OPTIMUM,
            implicated="central volume (converged to a different optimum)",
            fault=Fault.RECONSTRUCTION,
        ),
    )
    assert a.verdict is Verdict.FAILED
    assert a.root_cause == "convergence-to-a-different-local-optimum"
    assert a.fault_hypothesis == "reconstruction"


def test_non_pass_without_attribution_is_rejected() -> None:
    with pytest.raises(ValueError):
        judge_estimation(
            claim_id="c", quantity="CL", source_location="Table 3",
            reported=10.0, recovered=20.0,  # fails, but no attribution
        )


def test_paper_stated_precision_overrides_the_default() -> None:
    tol = Tolerance(
        0.02, 0.05, ToleranceSource.PAPER_STATED, rationale="paper reports estimates to 2% RSE"
    )
    a = judge_estimation(
        claim_id="c", quantity="ka estimate", source_location="Table 3",
        reported=1.00, recovered=1.08, tolerance=tol, attribution=_SHORTFALL,
    )
    assert a.tolerance_source == "paper-stated"
    assert a.verdict is Verdict.FAILED  # 8% blows the tight 2%/5% paper band


def test_estimation_verdict_is_distinguishable_in_a_mixed_certificate() -> None:
    # A paper certified at both levels keeps the two verdicts separable by their level field.
    sim = judge_scalar(
        claim_id="sim", quantity="AUC", source_location="Fig 2", reported=100.0, predicted=101.0
    )
    est = judge_estimation(
        claim_id="est", quantity="CL estimate", source_location="Table 3",
        reported=3.2, recovered=3.3,
    )
    cert = build_certificate(
        paper=PaperIdentity(doi="10.0/est", title="A data-shipping PK paper"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        assessments=[sim, est],
    )
    levels = {a.claim_id: a.level for a in cert.assessments}
    assert levels["sim"] is ReproductionLevel.SIMULATION
    assert levels["est"] is ReproductionLevel.ESTIMATION


def test_repeated_evaluation_is_identical() -> None:
    def run():
        return judge_estimation(
            claim_id="c", quantity="CL", source_location="Table 3",
            reported=3.2, recovered=3.35,
        )

    assert run() == run()


def test_lint_estimation_inline_verdict() -> None:
    from reprolith import lint_estimation

    good = lint_estimation(3.20, 3.30)  # ~3%, inside the 10% estimation default
    assert good.verdict is Verdict.REPRODUCED
    assert good.scope.machine  # the scope flag travels with the verdict
    assert "estimation" in good.discrepancy

    bad = lint_estimation(10.0, 18.0)  # 80% off
    assert bad.verdict is Verdict.FAILED
