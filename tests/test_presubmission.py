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
    # The fix now phrases the implicated element as an instruction and names the fault direction
    # as a hypothesis; what must not change is that the element itself is still in it.
    assert "dose units (mg vs mg/kg)" in report["fix_list"][1]["fix"]


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
    assert "every claim reproduces" not in report["readiness"]
    assert "re-fitting it from your data" in report["readiness"]
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


def test_an_assumption_the_author_cannot_clear_says_so() -> None:
    """Six of the thirty published certificates carried an instruction no paper could satisfy.

    The spatial engine implements one boundary condition and the stochastic class samples an
    ensemble, so those assumptions are Reprolith's limits rather than the paper's omissions — and
    `presubmission`, the surface whose whole job is to be acted on, told the author to state the
    value anyway. The sibling `gaps` report carried the sentence explaining why; this one dropped it.
    """
    from reprolith import (
        Assumption,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
    )
    from reprolith.presubmission import presubmission_report

    def report(**kw):
        cert = build_certificate(
            paper=PaperIdentity(title="t", doi="10.1/x"),
            engine_pin=EnginePin(engine="e", version="1"),
            assessments=[ClaimAssessment(claim_id="c", quantity="q", verdict=Verdict.REPRODUCED,
                                         source_location="Fig 1", assumption_qualified=True)],
            assumptions=[Assumption(id="a", description="a boundary Reprolith imposes",
                                    chosen="zero-flux (Neumann) boundaries",
                                    basis="this solver has exactly one boundary condition",
                                    load_bearing=True, **kw)],
        )
        items = presubmission_report(cert)["fix_list"]
        # Two kinds of assumption item exist: the per-claim "this claim rests on one" and the
        # certificate-level entry for the assumption itself. This is about the latter.
        return next(
            i for i in items
            if i["kind"] == "assumption" and "zero-flux" in i["issue"]
        )

    closable = report()
    assert "state" in closable["fix"]
    assert closable["why"] == "this solver has exactly one boundary condition"

    engine_limit = report(author_can_close=False)
    assert "nothing in the paper can clear this one" in engine_limit["fix"]
    assert "limit of Reprolith's engine" in engine_limit["fix"]


def _failed_claim(*, fault: str, implicated: str):
    from reprolith import ClaimAssessment, Verdict

    return ClaimAssessment(
        claim_id="c", quantity="Brain Cmax", verdict=Verdict.FAILED,
        source_location="Table 7, Brain row",
        discrepancy="relative error 0.2012",
        root_cause="apparent-manuscript-error",
        implicated=implicated,
        fault_hypothesis=fault,
    )


def test_the_fix_for_a_suspected_manuscript_error_is_an_instruction_and_a_hypothesis() -> None:
    """Read as the author being judged: a noun phrase under "FIX BEFORE YOU SUBMIT" is not a fix.

    The field it used was `implicated`, which is by definition the element implicated — so an
    author was handed the finding restated, with nothing to do about it and no indication that
    Reprolith was accusing their *table* rather than their model, or that a fault is a hypothesis
    they should check. `Fault` says "always a hypothesis, never a proven cause"; this surface
    never passed that on.
    """
    from reprolith.presubmission import _claim_issue_and_fix

    issue, fix = _claim_issue_and_fix(
        _failed_claim(fault="manuscript", implicated="Table 7's Brain Cmax, which equals plasma's")
    )
    assert issue == "relative error 0.2012"
    assert fix.startswith("check Table 7's Brain Cmax")
    assert "hypothesis" in fix
    assert "reported value is wrong rather than the model" in fix
    assert "confirm it against your own run" in fix


def test_the_fix_for_a_reconstruction_shortfall_points_at_the_model_instead() -> None:
    """The other direction has to read differently, or naming the fault buys the author nothing."""
    from reprolith.presubmission import _claim_issue_and_fix

    _, fix = _claim_issue_and_fix(
        _failed_claim(fault="reconstruction", implicated="the four dose events the model carries")
    )
    assert fix.startswith("reconcile the model with what your paper reports")
    assert "the shipped model, not the reported value, is what falls short" in fix


def test_a_shortfall_with_no_stated_fault_still_says_something_usable() -> None:
    """`undetermined_shortfall` names no fault, and that path must not lose the implicated element."""
    from reprolith.presubmission import _claim_issue_and_fix

    _, fix = _claim_issue_and_fix(_failed_claim(fault="", implicated="the peak concentration"))
    assert fix == "the peak concentration"


def test_a_claim_judged_from_a_figure_reading_is_reported_and_does_not_gate() -> None:
    """The author-facing consequence of a figure reading, and the reason it is not a fix.

    A claim whose reference was read off the author's own picture reproduced in a band twice as
    wide as a printed number's — against a curator's measurement rather than against anything the
    paper printed. The report had no notion of that at all, while the human certificate marked the
    same claim `[figure-reading]`.

    It is *reported* and does not gate readiness, which is the call the archive check already
    makes about `curves_without_values` one surface over: publishing results as figures is what
    papers do, and NOT READY for it tells almost every honest author their work is broken. An
    estimation-level pass gates because re-fitting answers a different question; a figure reading
    answers the same one in a wider band.
    """
    from reprolith import ReferenceKind, judge_curve

    read = judge_curve(
        claim_id="fig2-plasma", quantity="plasma concentration",
        source_location="Figure 2, plasma (digitized from the figure with WebPlotDigitizer 4.7)",
        reference=(1.0, 2.0, 3.0, 2.0, 1.0), predicted=(1.0, 2.01, 3.0, 2.0, 1.0),
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    report = presubmission_report(_cert([read, _reproduced("printed")]))

    assert report["ready_to_submit"] is True and report["fix_list"] == []
    item, = report["judged_from_figure_readings"]
    assert item["claim_id"] == "fig2-plasma"
    assert "in a band 2x as wide as a printed number's" in item["consequence"]
    # The step they can remove, and the reason it is worth telling them: measured on this test set
    # seven of ten open-access papers state their results only in figures, and a figure is the one
    # form a reproducer cannot read without re-measuring the picture.
    assert "publish this curve's values" in item["you_can_remove_it"]

    # A claim printed as a number is not in it, and neither list has grown for anybody else.
    assert all(i["claim_id"] != "printed" for i in report["judged_from_figure_readings"])


def test_nothing_read_off_a_figure_reports_nothing() -> None:
    """The list is empty rather than absent, so a reader can tell "none" from "not checked" — and
    so no certificate published before this renders differently."""
    assert presubmission_report(_cert([_reproduced()]))["judged_from_figure_readings"] == []


def test_the_human_report_prints_a_figure_reading_above_a_ready_verdict() -> None:
    """Both are true at once, and the second is the one the author can act on cheaply. A fact that
    lives only in the JSON is a fact the author reading the plain-text report does not have."""
    from reprolith import ReferenceKind, judge_curve

    read = judge_curve(
        claim_id="fig2-plasma", quantity="plasma concentration", source_location="Figure 2",
        reference=(1.0, 2.0, 3.0, 2.0, 1.0), predicted=(1.0, 2.01, 3.0, 2.0, 1.0),
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    rendered = render_presubmission_human(_cert([read]))
    assert "READY TO SUBMIT" in rendered
    assert "JUDGED FROM A READING OF YOUR FIGURE (not a fix — a consequence)" in rendered
    assert "publish this curve's values" in rendered

    # And a certificate with no reading prints no such section, rather than an empty heading.
    assert "JUDGED FROM A READING" not in render_presubmission_human(_cert([_reproduced()]))


def test_the_widening_told_to_an_author_is_their_claim_s_own_and_not_a_curve_s() -> None:
    """"A band twice as wide" is true of a curve and wrong about the other two.

    A figure-read *scalar* is judged at 0.15 against a printed number's 0.05 — three times, not
    twice — and a distribution band at 0.25 against 0.15, which is 1.67. This is an author-facing
    sentence about the number their own claim was held to, so it says that number.
    """
    from dataclasses import replace

    from reprolith import (
        PercentileBand,
        ReferenceKind,
        judge_distribution,
        judge_scalar,
    )

    scalar = judge_scalar(
        claim_id="cmax", quantity="Cmax", source_location="Figure 1",
        reported=100.0, predicted=101.0, reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    band = (PercentileBand(5.0, (1.0, 2.0)), PercentileBand(95.0, (3.0, 4.0)))
    # An envelope must record the sampling behind it before a certificate will carry it — a
    # verdict nobody can re-derive is not evidence — so this one does.
    envelope = replace(
        judge_distribution(
            claim_id="env", quantity="envelope", source_location="Figure 3",
            reference=band, predicted=band, reference_kind=ReferenceKind.DIGITIZED_FIGURE,
        ),
        protocol="virtual population: 500 subjects, seed 1",
    )
    told = {
        i["claim_id"]: i["consequence"]
        for i in presubmission_report(_cert([scalar, envelope]))["judged_from_figure_readings"]
    }
    assert "band 3x as wide" in told["cmax"]
    assert "band 1.67x as wide" in told["env"]


def test_a_comparison_with_no_widened_default_is_described_without_a_ratio() -> None:
    """An exact comparison — an attractor signature, a FROG fingerprint — has no band to widen, so
    there is nothing to divide and no number to state. Said in words rather than as 1x or nan."""
    from reprolith.presubmission import _figure_reading_consequence

    assert "wider band a reading is judged in" in _figure_reading_consequence("exact-match")
    assert "wider band a reading is judged in" in _figure_reading_consequence(None)


def test_one_assumption_across_many_claims_is_one_fix_and_not_one_per_claim() -> None:
    """Read as the author being judged: the fix list is a list of *fixes*, not of claims.

    An assumption is a value, and one value can withhold the clean pass from every claim on a
    certificate. Emitted per claim it produced — on the shipped metformin certificate — twenty-three
    rows carrying the identical sentence "state the value this claim rests on", naming no value, at
    the same priority as the single row that names it. The one fix the author can act on was the
    twenty-fourth of twenty-four items.

    Which claim rests on which assumption is not recorded per claim, so the rows could not have
    named it even one at a time. The claims are carried on the one row instead, where they read at
    once.
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

    cert = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id=f"c{i}", quantity=f"q{i}", source_location="Table 1",
                            verdict=Verdict.REPRODUCED, assumption_qualified=True)
            for i in range(23)
        ],
        assumptions=[
            Assumption(id="salt", description="the dose is the hydrochloride salt",
                       chosen="each dose x 129.16/165.62", basis="the paper's own methods",
                       attributed_to="reprolith", load_bearing=True),
        ],
    )
    fixes = presubmission_report(cert)["fix_list"]
    assumption_rows = [item for item in fixes if item["kind"] == "assumption"]
    assert len(assumption_rows) == 2, [item["issue"] for item in assumption_rows]

    names_the_value, rolls_up = assumption_rows
    # The row an author can act on is read first, at the same priority, by insertion order.
    assert "each dose x 129.16/165.62" in names_the_value["issue"]
    assert rolls_up["claims"] == [f"c{i}" for i in range(23)]
    assert "23 claim(s)" in rolls_up["quantity"]
    assert "listed above" in rolls_up["fix"]

    # The claims-dataset path carries no Assumption object at all, and then this row is the whole
    # signal rather than a roll-up of one — so it says what to do rather than pointing upwards.
    alone = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="c0", quantity="q0", source_location="Table 1",
                            verdict=Verdict.REPRODUCED, assumption_qualified=True),
        ],
    )
    (only,) = presubmission_report(alone)["fix_list"]
    assert only["kind"] == "assumption" and only["claims"] == ["c0"]
    assert "listed above" not in only["fix"]


def test_no_fix_is_the_finding_restated() -> None:
    """A list headed FIX BEFORE YOU SUBMIT owes an instruction, not the finding a second time.

    `_claim_issue_and_fix` was corrected for exactly this once — an author handed the discrepancy
    back as the thing to do about it — and the certificate-level note row was still doing it, with
    `"fix": note` beside `"issue": note`. Every gap-report entry is something the artifact or the
    paper does not state, so one instruction is true of all of them.

    Written as an invariant over the whole list rather than over the row that was wrong, since the
    next one added is where it would come back.
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

    cert = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="c0", quantity="q0", source_location="Table 1",
                            verdict=Verdict.REPRODUCED, assumption_qualified=True),
            ClaimAssessment(claim_id="c1", quantity="q1", source_location="Table 1",
                            verdict=Verdict.PARTIAL, discrepancy="off by 22%",
                            root_cause="unstated volume", implicated="V_central",
                            fault_hypothesis="reconstruction"),
        ],
        assumptions=[
            Assumption(id="salt", description="the dose is the hydrochloride salt",
                       chosen="each dose x 129.16/165.62", basis="the paper's own methods",
                       attributed_to="reprolith", load_bearing=True),
        ],
        gap_report=["unit not stated by the artifact: units — 13 of 37 values state none"],
    )
    for item in presubmission_report(cert)["fix_list"]:
        assert item["fix"] != item["issue"], item
        assert item["fix"].strip(), item
    note = next(i for i in presubmission_report(cert)["fix_list"] if i["kind"] == "note")
    assert note["fix"] == (
        "state it in your paper or your model file, so a reproducer need not infer it"
    )


def test_the_readiness_line_names_every_reason_the_clean_pass_was_withheld() -> None:
    """One sentence covered four causes, and pointed at the wrong one in every case but its own.

    "Every claim reproduces, but not cleanly" is *false* where a claim could not be evaluated —
    the overall rule drops abstentions before deciding, so `reproduced` does not mean every claim
    was judged — and it points at the results where the only finding is a gap in the artifact. On
    the shipped mouse certificate all fourteen claims reproduce, the worst by 0.27%, and what is
    missing is a unit in the model file; that author was told their results were not clean.
    """
    from reprolith import (
        ClaimAssessment,
        EnginePin,
        OverallVerdict,
        PaperIdentity,
        ReproductionLevel,
        Verdict,
        build_certificate,
        presubmission_report,
    )

    def cert(**kwargs: object):
        return build_certificate(
            paper=PaperIdentity(title="p", doi="10.0/p"),
            engine_pin=EnginePin(engine="e", version="1"),
            **kwargs,  # type: ignore[arg-type]
        )

    clean = ClaimAssessment(claim_id="c1", quantity="peak", source_location="Table 1",
                            verdict=Verdict.REPRODUCED)
    cases = {
        "could not be evaluated": cert(assessments=[
            clean,
            ClaimAssessment(claim_id="c2", quantity="exposure", source_location="Table 1",
                            verdict=Verdict.NOT_EVALUABLE, root_cause="no reference value"),
        ]),
        "re-fitting it from your data": cert(assessments=[
            ClaimAssessment(claim_id="c1", quantity="clearance", source_location="Table 2",
                            verdict=Verdict.REPRODUCED, level=ReproductionLevel.ESTIMATION,
                            protocol="least squares, Nelder-Mead"),
        ]),
        "leaves something a reproducer needs unstated": cert(
            assessments=[clean],
            gap_report=["unit not stated by the artifact: units — 11 of 34 values state no unit"],
        ),
    }
    for expected, built in cases.items():
        assert built.overall is OverallVerdict.REPRODUCED, expected
        readiness = presubmission_report(built)["readiness"]
        assert expected in readiness, (expected, readiness)
        # And nothing it did not find: naming one cause tells the author the others are fine.
        for other in cases:
            if other != expected:
                assert other not in readiness, (expected, other, readiness)

    # Several at once are all named, in the order the fix list ranks them.
    both = cert(
        assessments=[
            clean,
            ClaimAssessment(claim_id="c2", quantity="exposure", source_location="Table 1",
                            verdict=Verdict.NOT_EVALUABLE, root_cause="no reference value"),
        ],
        gap_report=["unit not stated by the artifact: units"],
    )
    readiness = presubmission_report(both)["readiness"]
    assert readiness.index("could not be evaluated") < readiness.index("leaves something")

    # The fourth reason the readiness flag tests never reaches this sentence, and the reason it
    # does not is worth failing on if it changes: `derive_overall` downgrades an
    # assumption-qualified claim, so that certificate is never an overall `reproduced` at all and
    # is answered by the `partially-reproduced` line instead.
    qualified = cert(assessments=[
        ClaimAssessment(claim_id="c1", quantity="peak", source_location="Table 1",
                        verdict=Verdict.REPRODUCED, assumption_qualified=True),
    ])
    assert qualified.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert presubmission_report(qualified)["ready_to_submit"] is False
