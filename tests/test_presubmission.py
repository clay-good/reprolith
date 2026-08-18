"""The author-facing pre-submission check (spec: presubmission-check; roadmap #10).

An author runs the same engine on their own model before publishing and gets a readiness signal
plus a prioritized "fix before you submit" list — derived from a certificate, never recomputed.
"""

from __future__ import annotations

import json

from reprolith import (
    Assumption,
    Attribution,
    Catalog,
    CertificateLedger,
    EnginePin,
    FailureMode,
    Fault,
    OverallVerdict,
    PaperIdentity,
    ReprolithQuery,
    build_certificate,
    handle_request,
    judge_scalar,
    not_evaluable,
    presubmission_report,
    render_presubmission_human,
)

_PIN = EnginePin(engine="copasi", version="4.46")


def _reproduced(claim_id: str = "c1") -> object:
    return judge_scalar(
        claim_id=claim_id, quantity="AUC", source_location="Table 1",
        reported=100.0, predicted=101.0,
    )


def _cert(assessments, assumptions=(), gap_report=()):
    return build_certificate(
        paper=PaperIdentity(title="Author's PK model", doi="10.9/pre"),
        engine_pin=_PIN, assessments=assessments, assumptions=assumptions, gap_report=gap_report,
    )


def test_clean_reproduction_is_ready_with_empty_fix_list() -> None:
    report = presubmission_report(_cert([_reproduced()]))
    assert report["ready_to_submit"] is True
    assert report["overall"] == "reproduced"
    assert report["fix_list"] == []
    assert "Ready to submit" in report["readiness"]


def test_fix_list_is_ordered_by_impact() -> None:
    failed = judge_scalar(
        claim_id="fail", quantity="Cmax", source_location="Fig 2",
        reported=100.0, predicted=200.0,
        attribution=Attribution(
            mode=FailureMode.UNIT_MISMATCH, implicated="dose units (mg vs mg/kg)",
            fault=Fault.MANUSCRIPT,
        ),
    )
    partial = judge_scalar(
        claim_id="part", quantity="half-life", source_location="Table 2",
        reported=100.0, predicted=110.0,
        attribution=Attribution(
            mode=FailureMode.AMBIGUOUS_INITIAL_CONDITION, implicated="initial gut amount",
            fault=Fault.MANUSCRIPT,
        ),
    )
    blind = not_evaluable(
        claim_id="blind", quantity="terminal slope", source_location="Fig 4",
        reason="figure has no digitizable reference data",
    )
    asm = Assumption(
        id="a1", description="steady-state initial condition", chosen="C(0)=Css",
        basis="stated dosing implies steady state", load_bearing=True,
    )
    # Claims added out of priority order on purpose; the report must reorder them.
    report = presubmission_report(
        _cert([partial, _reproduced("ok"), blind, failed], assumptions=[asm], gap_report=["note X"])
    )
    kinds_priorities = [(i["kind"], i["priority"]) for i in report["fix_list"]]
    # not-evaluable(1) < failed(2) < partial(3) < level(4) < assumption(5) < note(6); a cleanly
    # reproduced simulation claim is excluded.
    assert [p for _, p in kinds_priorities] == [1, 2, 3, 5, 6]
    assert report["fix_list"][0]["claim_id"] == "blind"
    assert report["fix_list"][1]["claim_id"] == "fail"
    assert report["fix_list"][1]["fix"] == "dose units (mg vs mg/kg)"


def test_partial_is_not_ready_even_though_no_claim_failed() -> None:
    partial = judge_scalar(
        claim_id="part", quantity="Cmax", source_location="Fig 2",
        reported=100.0, predicted=110.0,
        attribution=Attribution(
            mode=FailureMode.UNIT_MISMATCH, implicated="units", fault=Fault.MANUSCRIPT,
        ),
    )
    report = presubmission_report(_cert([_reproduced(), partial]))
    assert report["ready_to_submit"] is False
    assert report["overall"] == "partially-reproduced"


def test_assumption_qualified_reproduction_is_not_ready() -> None:
    # Every claim reproduces, but one rests on a load-bearing assumption: not a clean pass, so the
    # ready signal must be false (spec: "can never be green while any claim is assumption-qualified").
    qualified = judge_scalar(
        claim_id="q", quantity="AUC", source_location="Table 1",
        reported=100.0, predicted=101.0, assumption_qualified=True,
    )
    cert = _cert([qualified])
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    report = presubmission_report(cert)
    assert report["ready_to_submit"] is False


def test_non_load_bearing_assumption_is_not_in_the_fix_list() -> None:
    asm = Assumption(
        id="a1", description="cosmetic label", chosen="x", basis="convention", load_bearing=False,
    )
    report = presubmission_report(_cert([_reproduced()], assumptions=[asm]))
    assert report["fix_list"] == []  # only load-bearing assumptions are actionable


def test_scope_travels_and_cannot_be_emptied() -> None:
    report = presubmission_report(_cert([_reproduced()]))
    assert report["scope"]["machine"]
    assert report["scope"]["human"]


def test_human_render_reads_as_an_author_checklist() -> None:
    failed = judge_scalar(
        claim_id="fail", quantity="Cmax", source_location="Fig 2",
        reported=100.0, predicted=200.0,
        attribution=Attribution(
            mode=FailureMode.UNIT_MISMATCH, implicated="dose units", fault=Fault.MANUSCRIPT,
        ),
    )
    text = render_presubmission_human(_cert([failed]))
    assert "PRE-SUBMISSION REPRODUCIBILITY CHECK" in text
    assert "NOT YET READY" in text
    assert "fix:" in text
    assert "SCOPE" in text


def test_presubmission_over_mcp_surface() -> None:
    ledger = CertificateLedger()
    digest = ledger.issue(_cert([_reproduced()]))
    query = ReprolithQuery(Catalog(), ledger)
    resp = handle_request(query, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "presubmission", "arguments": {"digest": digest}},
    })
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["ready_to_submit"] is True
    assert data["scope"]["machine"]


def test_report_is_derived_not_recomputed() -> None:
    # The per-claim and overall verdicts in the report are exactly the certificate's.
    cert = _cert([_reproduced("c1")])
    report = presubmission_report(cert)
    assert report["overall"] == cert.overall.value
    assert [c["verdict"] for c in report["per_claim"]] == [a.verdict.value for a in cert.assessments]


def test_a_certificate_carrying_a_gap_note_is_not_ready_to_submit() -> None:
    # Readiness consulted only the verdicts and the per-claim assumption flags, so a certificate
    # whose gap report records something the artifact never stated read as READY TO SUBMIT above a
    # fix list naming what to fix first — contradicting this module's own promise that a ready
    # certificate yields an empty fix list.
    report = presubmission_report(
        _cert([_reproduced()], gap_report=("the reported dose units were ambiguous; mg assumed",))
    )
    assert report["ready_to_submit"] is False
    assert report["fix_list"]


def test_an_estimation_reproduction_never_reads_as_a_clean_simulation_pass() -> None:
    """Re-fitting a parameter is a weaker result than running the described model.

    The two reproduction levels exist so they are never conflated, but every derived surface —
    badge colour, machine summary, gap report, readiness — keyed on the verdict alone, so a
    certificate where no simulation was ever run rendered green and said READY TO SUBMIT.
    """
    from reprolith import ClaimAssessment, ReproductionLevel, Verdict, render_badge
    from reprolith.render import estimation_claims, gap_items

    cert = _cert([
        ClaimAssessment(
            claim_id="e1", quantity="clearance", verdict=Verdict.REPRODUCED,
            source_location="Table 2", level=ReproductionLevel.ESTIMATION,
            protocol="maximum likelihood, Nelder-Mead, shipped dataset",
        )
    ])
    assert cert.overall is OverallVerdict.REPRODUCED  # the claim did reproduce, at its own level
    assert estimation_claims(cert) == ["e1"]
    assert "#4c1" not in render_badge(cert)  # green is reserved for a simulation reproduction
    assert "estimation" in render_badge(cert)
    assert [g["claim_id"] for g in gap_items(cert)] == ["e1"]

    report = presubmission_report(cert)
    assert report["ready_to_submit"] is False
    assert "every claim reproduces cleanly" not in report["readiness"]
    assert [i["kind"] for i in report["fix_list"]] == ["level"]


def test_the_fix_list_names_both_reasons_a_clean_pass_was_withheld() -> None:
    """"Not yet ready … address the fix list" over an empty fix list, in two reachable cases.

    A claim that reproduced only under an assumption Reprolith supplied (with no Assumption object
    carrying it — what the claims-dataset path produces), and an assumption awaiting expert
    confirmation that is not itself load-bearing. `derive_overall` honors both; the sibling gap
    report lists both; this report listed neither.
    """
    from reprolith import (
        Assumption,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        presubmission_report,
    )

    qualified_claim = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="Cmax", quantity="peak concentration",
                            source_location="Table 1", verdict=Verdict.REPRODUCED,
                            assumption_qualified=True),
        ],
    )
    awaiting = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="Cmax", quantity="peak concentration",
                            source_location="Table 1", verdict=Verdict.REPRODUCED),
        ],
        assumptions=[
            Assumption(id="a1", description="the elimination route", chosen="renal",
                       basis="convention", attributed_to="reprolith", load_bearing=False,
                       verification_item="verify:ke"),
        ],
    )
    for cert in (qualified_claim, awaiting):
        report = presubmission_report(cert)
        assert not report["ready_to_submit"]
        assert report["fix_list"], "a report that says 'address the fix list' must have one"
