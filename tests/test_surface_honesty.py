"""What the agent- and human-facing surfaces may not overstate (spec: mcp-server, presubmission).

Four holes an audit pass found in the read surfaces, held closed here:

* the pre-submission report — the one that says "ready to submit" — served a certificate that had
  since been corrected, with no sign that it had;
* `gaps` was the single read path that returned per-claim verdicts with no scope flag beside them;
* neither the human certificate nor the published registry showed supersession at all, so a
  withdrawn `reproduced` and the `not-reproduced` that replaced it rendered as two equal records;
* an argument of the wrong *shape* crashed a tool instead of being refused.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from reprolith import (
    Attribution,
    Catalog,
    CertificateLedger,
    ClaimAssessment,
    EnginePin,
    FailureMode,
    Fault,
    PaperIdentity,
    ReprolithQuery,
    RunMetadata,
    Verdict,
    build_certificate,
    certificate_digest,
    render_human,
    render_registry,
)
from reprolith.mcp_server import handle_request

_PIN = EnginePin(engine="test-engine", version="0.0.0")
_PAPER = PaperIdentity(title="A paper certified twice", doi="10.0/twice")
_RUN = RunMetadata(created_at="2026-08-17T00:00:00Z", actor="test", tool_version="0.0.1")


def _assessment(verdict: Verdict) -> ClaimAssessment:
    attribution = (
        None
        if verdict is Verdict.REPRODUCED
        else Attribution(
            mode=FailureMode.UNIT_MISMATCH, implicated="dose units", fault=Fault.MANUSCRIPT
        )
    )
    return ClaimAssessment(
        claim_id="c1", quantity="plasma Cmax", verdict=verdict, source_location="Table 1",
        root_cause=attribution.mode.value if attribution else None,
        implicated=attribution.implicated if attribution else None,
        fault_hypothesis=attribution.fault.value if attribution else None,
    )


def _corrected_pair() -> tuple[object, object]:
    """A `reproduced` certificate and the `not-reproduced` correction that superseded it."""
    original = build_certificate(paper=_PAPER, engine_pin=_PIN, assessments=[_assessment(Verdict.REPRODUCED)])
    correction = build_certificate(
        paper=_PAPER, engine_pin=_PIN, assessments=[_assessment(Verdict.FAILED)],
        supersedes=original,
    )
    return original, correction


def _query_with_correction() -> tuple[ReprolithQuery, str]:
    original, correction = _corrected_pair()
    ledger = CertificateLedger()
    ledger.issue(original)
    ledger.issue(correction)
    return ReprolithQuery(Catalog(), ledger), certificate_digest(original)


def test_presubmission_says_the_certificate_it_reports_on_was_superseded() -> None:
    query, stale = _query_with_correction()
    report = query.presubmission(stale)
    assert report is not None
    # The readiness signal an author acts on must not be computed from a withdrawn record without
    # saying so: `verdict` already carried this, and this report has more riding on it.
    assert report["superseded_by"] == query.verdict(stale)["superseded_by"]
    assert report["superseded_by"]


def test_gaps_returns_its_verdicts_with_the_scope_flag() -> None:
    query, stale = _query_with_correction()
    report = query.gaps(stale)
    assert report is not None
    assert report["scope"]["machine"] and report["scope"]["human"]
    assert report["superseded_by"]
    # The gap items still carry their per-claim verdicts — now with something qualifying them.
    # (The superseded record reproduced cleanly, so its own gap list is empty; the correction that
    # replaced it is the one with a claim that fell short.)
    _, correction = _corrected_pair()
    current = query.gaps(certificate_digest(correction))
    assert current is not None
    assert [item["claim_id"] for item in current["gaps"]] == ["c1"]
    assert current["scope"]["machine"] and current["superseded_by"] is None


def test_the_human_certificate_shows_what_it_replaced() -> None:
    original, correction = _corrected_pair()
    assert "Supersedes:" not in render_human(original, _RUN)  # a first certification replaces nothing
    text = render_human(correction, _RUN)
    assert f"Supersedes: {certificate_digest(original)}" in text


def test_the_registry_does_not_publish_a_withdrawn_verdict_as_a_current_one() -> None:
    original, correction = _corrected_pair()
    html = render_registry([("ode-pkpd", original), ("ode-pkpd", correction)])
    assert "superseded" in html
    # The withdrawn card names its replacement, so a reader comparing two cards for one paper can
    # tell which is the answer.
    assert certificate_digest(correction) in html
    assert html.count('data-superseded="yes"') == 1


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("lint_steady_state", {"rules": ["A"], "reported": {"A": 1}}),
        ("lint_steady_state", {"rules": {"A": "A"}, "reported": ["A"]}),
        ("lint_distribution", {"reported": ["oops"], "predicted": ["oops"]}),
        ("status", {"title": {"a": 1}}),
    ],
)
def test_a_malformed_argument_is_refused_rather_than_crashing_the_tool(
    tool: str, arguments: dict[str, object]
) -> None:
    query = ReprolithQuery(Catalog(), CertificateLedger())
    response = handle_request(
        query,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    )
    assert response is not None
    # A tool-level refusal the caller can read, not an exception escaping a documented pure function.
    assert response["result"]["isError"] is True
    assert response["result"]["content"][0]["text"].startswith("error: ")


def test_an_inline_stochastic_check_abstains_when_its_ensemble_cannot_resolve_the_claim() -> None:
    """The linter and the certificate path share one rule about what an ensemble can decide.

    At ten trajectories a provably correct immigration-death model misses its 5% claim on most
    seeds, so a confident `failed` is a false accusation an agent gates a workflow on, and a
    confident `reproduced` is luck the caller cannot see.
    """
    from reprolith.stochastic import unresolvable_ensemble_reason

    # Poisson: mean 10, variance 10. The standard error is 10% of the mean at ten trajectories and
    # 0.8% at 1600, against a 5% pass threshold.
    assert unresolvable_ensemble_reason(reported_mean=10.0, variance=10.0, trajectories=10)
    assert unresolvable_ensemble_reason(reported_mean=10.0, variance=10.0, trajectories=1600) is None


def test_a_lint_result_omits_the_protocol_key_when_there_is_no_sampling() -> None:
    from reprolith import LintResult

    deterministic = LintResult(
        verdict=Verdict.REPRODUCED, method="scalar-relative-error",
        discrepancy="relative error 0.0100", tolerance="reproduced<=0.05 (class-default)",
    )
    assert "protocol" not in deterministic.to_dict()
    sampled = replace(deterministic, protocol="SSA ensemble: 400 trajectories to t=40, seed 1")
    assert sampled.to_dict()["protocol"].startswith("SSA ensemble")


def test_the_curve_linter_and_the_curve_judge_answer_the_same_question() -> None:
    """An agent gates on the linter and publishes through the judge; they must not disagree.

    The worst-point rule landed in the judge alone, so a reconstruction whose peak is twice the
    paper's — the miss an RMSE over many samples averages away — was refused by `judge_curve` and
    green-lit by `lint_curve`, on the same numbers.
    """
    from reprolith import judge_curve
    from reprolith.linter import _curve_lint
    from reprolith.oracle import ComparisonMethod, ReferenceKind, default_tolerance

    reference = tuple(1.0 for _ in range(201))
    doubled_peak = tuple(2.0 if i == 100 else 1.0 for i in range(201))
    tol = default_tolerance(ComparisonMethod.CURVE_NORMALIZED_DISTANCE, ReferenceKind.NUMERIC)

    linted = _curve_lint(reference, doubled_peak, tol)
    judged = judge_curve(
        claim_id="c", quantity="a curve with one doubled point", source_location="Fig 1",
        reference=reference, predicted=doubled_peak,
        attribution=Attribution(mode=FailureMode.UNCATEGORIZED, implicated="the peak",
                                fault=Fault.RECONSTRUCTION),
    )
    assert linted.verdict is judged.verdict is not Verdict.REPRODUCED
    assert "worst point" in linted.discrepancy


def test_a_reported_zero_abstains_at_the_linter_as_it_does_at_the_judge() -> None:
    """A lethality claim reports zero, and a relative error against zero is undefined.

    The judge abstains and names what the claim needs; the linter raised, so the agent-facing
    surface answered the canonical constraint-based claim shape with a server error.
    """
    from reprolith.linter import lint_estimation

    abstained = lint_estimation(reported=0.0, recovered=0.05)
    assert abstained.verdict is Verdict.NOT_EVALUABLE
    assert "zero" in abstained.discrepancy
    # An exactly-zero recovery is exact agreement and still passes without a scale.
    assert lint_estimation(reported=0.0, recovered=0.0).verdict is Verdict.REPRODUCED


def test_ready_to_submit_is_withheld_when_a_claim_could_not_be_evaluated() -> None:
    """The fix list ranks an abstention first; the readiness line said everything reproduced.

    `derive_overall` drops abstentions before deciding, by design, so a certificate with one clean
    pass and one un-judgeable claim is `reproduced` — and this report has to look for itself.
    """
    from reprolith import presubmission_report

    cert = build_certificate(
        paper=_PAPER, engine_pin=_PIN,
        assessments=[
            _assessment(Verdict.REPRODUCED),
            replace(_assessment(Verdict.NOT_EVALUABLE), claim_id="c2", root_cause="no reference"),
        ],
    )
    report = presubmission_report(cert)
    assert report["ready_to_submit"] is False
    assert "every claim reproduces cleanly" not in report["readiness"]
    assert report["fix_list"][0]["claim_id"] == "c2"


def test_every_class_front_end_can_publish_a_miss_it_was_not_handed_a_cause_for() -> None:
    """A front-end that raises on an uncategorized miss can only ever emit a pass or a traceback.

    Four classes learned this in an earlier pass; the estimation, population, and logical
    front-ends were missed, and each of them takes claims whose `shortfall` defaults to None.
    """
    from reprolith import (
        EstimationClaim,
        LogicalClaim,
        OverallVerdict,
        PercentileBand,
        PopulationClaim,
        certify_estimation,
        certify_logical,
        certify_population,
    )

    protocol = "least squares, Nelder-Mead from Table 2, over the shipped dataset"
    estimation = certify_estimation(
        paper=_PAPER, engine_pin=_PIN,
        claims=[EstimationClaim(claim_id="cl", quantity="CL/F", reported=3.2, recovered=9.9,
                                source_location="Table 3", protocol=protocol)],
    )
    assert estimation.overall is OverallVerdict.NOT_REPRODUCED
    assert estimation.assessments[0].root_cause == "uncategorized"
    assert estimation.assessments[0].fault_hypothesis == "reconstruction"  # never a bare accusation

    bands = (PercentileBand(percentile=50, curve=(1.0, 2.0, 3.0)),)
    wrong = (PercentileBand(percentile=50, curve=(9.0, 9.0, 9.0)),)
    population = certify_population(
        paper=_PAPER, engine_pin=_PIN,
        claims=[PopulationClaim(claim_id="p", quantity="P50 envelope", reported=bands,
                                predicted=wrong, source_location="Fig 4",
                                protocol="500 subjects, seed 7")],
    )
    assert population.overall is OverallVerdict.NOT_REPRODUCED
    assert population.assessments[0].root_cause == "uncategorized"

    from reprolith.logical import solver_pin_for

    logical = certify_logical(
        # The logical pin has to name the path that ran (enumeration or SAT); the shared `_PIN`
        # here names neither, and this test is about the root cause, not the pin.
        paper=_PAPER, engine_pin=solver_pin_for(nodes=2),
        claims=[LogicalClaim(claim_id="fp", quantity="the reported steady state",
                             rules={"A": "!B", "B": "!A"}, reported={"A": 1, "B": 1},
                             source_location="Fig 2")],
    )
    assert logical.overall is OverallVerdict.NOT_REPRODUCED
    assert logical.assessments[0].root_cause == "uncategorized"
