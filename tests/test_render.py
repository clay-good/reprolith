"""Machine- and human-readable certificate rendering (bootstrap tasks 5.1, 5.2, 5.4)."""

from __future__ import annotations

from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    RunMetadata,
    Verdict,
    build_certificate,
    claim_counts,
    render_human,
    render_machine,
)

RUN = RunMetadata(created_at="2026-08-03T00:00:00Z", actor="agent-1", tool_version="0.0.1")


def _claim(verdict: Verdict, *, cid: str, qualified: bool = False, **kw: object) -> ClaimAssessment:
    # A non-pass verdict carries a root cause, because the builder now refuses one that does not —
    # the judges have always required it, and a hand-assembled certificate saying "failed" with no
    # reason let `render.gap_items` invent one ("no evaluable output") for a claim that was in fact
    # evaluated and missed.
    cause: dict[str, object] = (
        {} if verdict in (Verdict.REPRODUCED, Verdict.NOT_EVALUABLE) or "root_cause" in kw
        else {"root_cause": "uncategorized"}
    )
    return ClaimAssessment(
        claim_id=cid, quantity="AUC", verdict=verdict, source_location="Fig 2",
        assumption_qualified=qualified, **cause, **kw,
    )


def _cert(assessments, paper=None, **kw):
    return build_certificate(
        paper=paper or PaperIdentity(title="Two-compartment PK model", doi="10.1/x"),
        engine_pin=EnginePin(engine="biosimulators/copasi", version="4.42"),
        assessments=assessments,
        **kw,
    )


# --- 5.1 machine and human forms derive from one source and agree ------------------


def test_both_renderings_report_the_same_facts() -> None:
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.FAILED, cid="b")])
    machine = render_machine(cert, RUN)
    human = render_human(cert, RUN)

    # The overall verdict, every claim count, and the scope statement in the machine
    # view all appear verbatim in the human view — they cannot diverge.
    assert machine["summary"]["overall"] in human
    for verdict, n in machine["summary"]["claim_counts"].items():
        assert f"{verdict}={n}" in human
    assert machine["content"]["scope"]["human"] in human


def test_the_human_form_shows_how_far_off_every_judged_claim_was() -> None:
    """The evidence for the certificate's own headline, which only the machine form carried.

    A reader saw `reproduced` and the budget it was judged against, and could not see whether the
    number came in at a fifth of that budget or at nine tenths of it. For a non-pass the figure
    appeared once, inside the root cause under WHAT WAS MISSING; for a pass there is no root cause,
    so it appeared nowhere at all — in a document whose whole purpose is to be checkable.
    """
    cert = _cert([
        _claim(Verdict.REPRODUCED, cid="a", discrepancy="relative error 0.0107"),
        _claim(Verdict.FAILED, cid="b", discrepancy="relative error 0.7475"),
    ])
    machine = render_machine(cert, RUN)
    human = render_human(cert, RUN)
    stated = [a["discrepancy"] for a in machine["content"]["assessments"] if a["discrepancy"]]
    assert stated, "this fixture judges nothing; the check would pass vacuously"
    for discrepancy in stated:
        assert f"measured: {discrepancy}" in human


def test_human_certificate_is_self_contained() -> None:
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a", method="normalized curve distance",
                         tolerance="10% relative")])
    human = render_human(cert, RUN)
    # A stranger sees paper, claim+verdict, method, tolerance, and scope with no other tools.
    assert "Two-compartment PK model" in human
    assert "AUC" in human and "reproduced" in human
    assert "normalized curve distance" in human and "10% relative" in human
    assert "SCOPE" in human


# --- 5.2 per-verdict claim counts; mixed is never rounded up -----------------------


def test_claim_counts_cover_every_verdict() -> None:
    cert = _cert([
        _claim(Verdict.REPRODUCED, cid="a"),
        _claim(Verdict.REPRODUCED, cid="b"),
        _claim(Verdict.FAILED, cid="c"),
        _claim(Verdict.NOT_EVALUABLE, cid="d"),
    ])
    counts = claim_counts(cert)
    assert counts == {"reproduced": 2, "partial": 0, "failed": 1, "not-evaluable": 1}


def test_mixed_result_renders_partially_reproduced_never_reproduced() -> None:
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.FAILED, cid="b")])
    machine = render_machine(cert, RUN)
    assert machine["summary"]["overall"] == OverallVerdict.PARTIALLY_REPRODUCED.value
    human = render_human(cert, RUN)
    assert "OVERALL: partially-reproduced" in human
    assert "OVERALL: reproduced" not in human


def test_assumption_qualified_claim_is_marked_and_downgrades_overall() -> None:
    cert = _cert(
        [_claim(Verdict.REPRODUCED, cid="a", qualified=True)],
        assumptions=[Assumption(id="k1", description="initial condition", chosen="0",
                                basis="steady-state assumed", load_bearing=True)],
    )
    machine = render_machine(cert, RUN)
    # Every claim reproduced, but one rests on a load-bearing assumption: not a clean pass.
    assert machine["summary"]["overall"] == OverallVerdict.PARTIALLY_REPRODUCED.value
    assert machine["summary"]["assumption_qualified_claims"] == ["a"]
    human = render_human(cert, RUN)
    assert "assumption-qualified" in human


# --- 5.4 structured "what was missing" report, tied to claims ----------------------


def test_blocked_entry_lists_missing_inputs_tied_to_claims() -> None:
    cert = _cert([
        _claim(Verdict.NOT_EVALUABLE, cid="a", root_cause="no digitizable reference data in Fig 3"),
        _claim(Verdict.NOT_EVALUABLE, cid="b"),
    ])
    machine = render_machine(cert, RUN)
    assert machine["summary"]["overall"] == OverallVerdict.BLOCKED.value
    gaps = machine["gaps"]
    assert len(gaps) == 2
    by_claim = {g["claim_id"]: g for g in gaps}
    # Each gap ties a specific missing input to the claim it blocks.
    assert by_claim["a"]["needs"] == "no digitizable reference data in Fig 3"
    assert by_claim["a"]["source_location"] == "Fig 2"
    assert by_claim["b"]["needs"]  # a precise fallback statement, never empty


def test_full_reproduction_has_no_gaps() -> None:
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.REPRODUCED, cid="b")])
    assert render_machine(cert, RUN)["gaps"] == []
    assert "WHAT WAS MISSING" not in render_human(cert, RUN)


def test_assumption_driven_downgrade_is_never_a_silent_empty_gap_report() -> None:
    # A claim can reproduce yet still not be a clean pass: it reproduced only under a load-bearing
    # assumption Reprolith supplied, which is why the overall verdict is partially-reproduced. The
    # "what was missing" report must say so — otherwise the one surface whose job is to explain the
    # downgrade asserts nothing was missing.
    cert = _cert(
        [_claim(Verdict.REPRODUCED, cid="a", qualified=True)],
        assumptions=[Assumption(id="dose", description="salt form unstated", chosen="free base",
                                basis="model default", load_bearing=True)],
    )
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    gaps = render_machine(cert, RUN)["gaps"]
    assert gaps, "a sub-full verdict must never yield an empty gap report"
    needs = " ".join(g["needs"] for g in gaps)
    assert "assumption" in needs  # the qualified claim is named as not-a-clean-pass
    assert "salt form unstated" in needs  # the load-bearing assumption names the missing condition
    assert "WHAT WAS MISSING" in render_human(cert, RUN)


def test_assumption_qualified_claim_without_a_recorded_assumption_still_reports_the_gap() -> None:
    # The stochastic class qualifies a claim on its sampling protocol without recording a separate
    # assumption object; the gap report must still flag the qualified claim rather than fall silent.
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a", qualified=True)])
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    gaps = render_machine(cert, RUN)["gaps"]
    assert len(gaps) == 1 and gaps[0]["claim_id"] == "a"


def test_certificate_level_gap_notes_are_included() -> None:
    cert = _cert([_claim(Verdict.PARTIAL, cid="a")], gap_report=("dosing schedule ambiguous",))
    gaps = render_machine(cert, RUN)["gaps"]
    needs = [g["needs"] for g in gaps]
    assert "dosing schedule ambiguous" in needs


def test_unverified_assumption_names_its_queue_item() -> None:
    from reprolith import RunMetadata, render_human
    cert = _cert(
        [_claim(Verdict.REPRODUCED, cid="a", qualified=True)],
        assumptions=[Assumption(id="k1", description="ka", chosen="1.2", basis="typical",
                                load_bearing=True, verification_item="VQ-7")],
    )
    run = RunMetadata(created_at="t", actor="a", tool_version="0.0.1")
    text = render_human(cert, run)
    # The certificate names the pending queue item it rests on (spec: verification-queue).
    assert "unverified" in text and "VQ-7" in text


# --- status badge (spec: certificate-publication, "No silent green") ----------------


def test_badge_reflects_verdict_and_carries_scope() -> None:
    from reprolith import render_badge
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a")])
    svg = render_badge(cert)
    assert "<svg" in svg and "</svg>" in svg
    assert "reproduced" in svg
    assert "#4c1" in svg  # a clean reproduction is green
    # The scope statement travels in the badge and cannot be emptied.
    assert "reproducible-not-correct-not-clinical" in svg


def test_badge_never_shows_silent_green_for_qualified_results() -> None:
    from reprolith import render_badge
    # A qualified result (partially-reproduced) must not render green.
    qualified = _cert([_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.FAILED, cid="b")])
    svg = render_badge(qualified)
    assert "partially-reproduced" in svg
    assert "#4c1" not in svg  # not green
    assert "#dfb317" in svg  # amber — visibly distinct from a clean pass


def test_badge_colors_for_not_reproduced_and_blocked() -> None:
    from reprolith import render_badge
    assert "#e05d44" in render_badge(_cert([_claim(Verdict.FAILED, cid="a")]))  # not-reproduced red
    assert "#9f9f9f" in render_badge(_cert([_claim(Verdict.NOT_EVALUABLE, cid="a")]))  # blocked grey


def test_human_render_marks_an_estimation_level_verdict() -> None:
    from reprolith import ReproductionLevel

    est = _claim(
        Verdict.REPRODUCED, cid="e", level=ReproductionLevel.ESTIMATION,
        # An estimation verdict states the re-fit behind it before it can be certified at all.
        protocol="maximum likelihood, Nelder-Mead, shipped dataset",
    )
    sim = _claim(Verdict.REPRODUCED, cid="s")  # default simulation level
    text = render_human(_cert([est, sim]), RUN)
    assert "[e] AUC: reproduced [estimation]" in text
    assert "[s] AUC: reproduced (" in text  # simulation level is not tagged


def test_render_registry_is_browsable_and_honest() -> None:
    from reprolith import render_registry

    clean = _cert([_claim(Verdict.REPRODUCED, cid="a")])
    qualified = _cert([_claim(Verdict.REPRODUCED, cid="b", qualified=True)])  # -> partially-reproduced
    failed = _cert([_claim(Verdict.FAILED, cid="c")])
    html = render_registry([
        ("ode-pkpd", clean),
        ("logical", qualified),
        ("constraint-based", failed),
    ])

    # Every certificate is listed and navigable, grouped by class and verdict.
    assert html.count('class="entry"') == 3
    assert 'data-class="logical"' in html and 'data-class="ode-pkpd"' in html
    assert 'data-verdict="partially-reproduced"' in html
    # The scope statement travels and cannot be emptied.
    assert "reproducible" in html.lower() and "clinical" in html.lower()
    # No silent green: the qualified/partial entry is not painted the clean-pass green.
    partial_badge_green = "partially-reproduced" in html and "#4c1" in html.split("partially-reproduced")[0][-400:]
    assert not partial_badge_green
    # A self-contained page.
    assert html.startswith("<!doctype html>") and "</html>" in html


def test_render_registry_handles_no_certificates() -> None:
    from reprolith import render_registry

    html = render_registry([])
    assert "No certificates yet" in html


def test_render_registry_track_record_banner_is_honest() -> None:
    from reprolith import render_registry

    clean = _cert([_claim(Verdict.REPRODUCED, cid="a")])
    # A self-validation summary shaped like ReprolithQuery.self_validation() output: a class of all
    # abstentions plus a clean cross-tool class.
    self_validation = {
        "by_class": {
            "ode-pkpd": {"total": 31, "agreements": 0,
                         "confusion": {"reproduced->blocked": 30, "reproduced->partially-reproduced": 1}},
            "logical": {"total": 9, "agreements": 9, "confusion": {"reproduced->reproduced": 9}},
        },
        "overall": {"agreements": 9, "abstentions": 30, "other_disagreements": 1, "labelled_entries": 40},
    }
    html = render_registry([("ode-pkpd", clean)], self_validation=self_validation)
    assert "Blind self-validation" in html
    # The abstention is named as such, never dressed as agreement or error.
    assert "abstention" in html.lower()
    # The overall row shows the honest split, not a blended rate.
    assert "<td>30</td>" in html  # 30 abstentions surfaced
    assert "%" not in html.split("track-record")[1].split("</section>")[0]  # no blended rate in the banner

    # Backward compatible: with no summary, no banner (existing callers unaffected).
    assert "Blind self-validation" not in render_registry([("ode-pkpd", clean)])
    assert "clinical" in html.lower()  # scope disclaimer still present


def test_registry_escapes_a_scope_statement_carried_in_from_a_stored_certificate() -> None:
    """A contributed certificate must not be able to inject markup into the public registry."""
    import pytest
    from reprolith import Scope, certificate_from_content, render_badge, render_registry

    payload = '</title><script>alert(1)</script>'
    # There is no longer any way to attach such a scope to a certificate: the text is fixed at the
    # type, so a reworded scope cannot be minted in memory any more than it can be loaded from a
    # file. Both refusals are asserted, because they close different doors.
    with pytest.raises(ValueError, match="fixed text and cannot be reworded"):
        Scope(machine=payload, human="h")
    stored = _cert([_claim(Verdict.REPRODUCED, cid="a")]).content()
    stored["scope"] = {"machine": payload, "human": "h"}
    with pytest.raises(ValueError, match="scope statement that is not Reprolith's"):
        certificate_from_content(stored)
    # The remaining caller-controlled strings still cannot inject markup into the public page.
    cert = _cert([_claim(Verdict.REPRODUCED, cid="a")], paper=PaperIdentity(title=payload))
    for html in (render_badge(cert), render_registry([("ode-pkpd", cert)])):
        assert "<script>alert" not in html
    page = render_registry([("ode-pkpd", cert)])
    assert "no claim about biological correctness" in page  # Reprolith's wording, not the file's


def test_the_gap_report_names_a_cause_the_certificate_actually_carries() -> None:
    """It fell straight through to "no evaluable output" for a claim that *was* evaluated.

    `implicated` and `fault_hypothesis` are causes; reading only `root_cause` invented an
    abstention's reason for a miss. Whitespace is not a cause either, and this renders verdicts
    `require_stated_cause` does not police, so the stripping has to happen here too.
    """
    from reprolith.render import gap_items

    # A failed claim cannot reach here without a root cause any more — the builder refuses it —
    # so the fallback is exercised on the verdicts `require_stated_cause` does not police.
    implicated_only = _cert([_claim(Verdict.NOT_EVALUABLE, cid="a", implicated="elimination rate")])
    assert gap_items(implicated_only)[0]["needs"] == "elimination rate"

    blank = _cert([_claim(Verdict.NOT_EVALUABLE, cid="b", root_cause="   ",
                          discrepancy="off by 40%")])
    assert gap_items(blank)[0]["needs"] == "off by 40%"

    nothing = _cert([_claim(Verdict.NOT_EVALUABLE, cid="c")])
    assert gap_items(nothing)[0]["needs"] == "evaluable output or reference data for this claim"


def test_a_gap_that_never_became_a_claim_still_reaches_the_badge_and_the_verdict_summary() -> None:
    """`derive_overall` reads the claims alone, so a missing result nobody evaluated cannot lower it.

    The human certificate prints such a note under WHAT WAS MISSING and pre-submission refuses
    ready-to-submit, but the badge — one word and one colour, the most compressed rendering there
    is and the one a reader meets first — went green, and the verdict summary read as a clean pass.
    The same structural hole `estimation_claims` was added to close, one field over.
    """
    from reprolith import (
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        render_badge,
    )
    from reprolith.catalog import Catalog
    from reprolith.query import ReprolithQuery
    from reprolith.supersession import CertificateLedger

    cert = build_certificate(
        paper=PaperIdentity(title="A paper with an undigitized figure", doi="10.1/g"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
        gap_report=["Figure 3 could not be digitized, so its claim was never evaluated"],
    )
    assert cert.overall.value == "reproduced"  # the claims alone still say so

    badge = render_badge(cert)
    assert "(gaps)" in badge
    assert "#4c1" not in badge, "a certificate naming something missing must not render green"

    ledger = CertificateLedger()
    digest = ledger.issue(cert)
    view = ReprolithQuery(Catalog(), ledger).verdict(digest)
    assert view["gap_notes"] == [
        "Figure 3 could not be digitized, so its claim was never evaluated"
    ]


def test_a_gap_report_downgrades_a_badge_and_never_upgrades_one() -> None:
    """Setting the amber unconditionally *raised* the two verdicts below it.

    `run.blocked_certificate` always carries a gap report, so every abstention the pipeline
    produces — 30 of the 31 PK/PD entries — turned from grey to amber, a not-reproduced result with
    a gap turned from red to amber, and grey became unreachable.
    """
    from reprolith import (
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        render_badge,
    )
    from reprolith.oracle import FailureMode, Fault

    gaps = ["Figure 3 could not be digitized"]
    pin = EnginePin(engine="copasi", version="4.46")
    paper = PaperIdentity(title="t", doi="10.1/g")

    passing = build_certificate(
        paper=paper, engine_pin=pin, gap_report=gaps,
        assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="T1")],
    )
    assert "(gaps)" in render_badge(passing) and "#4c1" not in render_badge(passing)

    failing = build_certificate(
        paper=paper, engine_pin=pin, gap_report=gaps,
        assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.FAILED,
                                     source_location="T1",
                                     root_cause=FailureMode.UNCATEGORIZED.value,
                                     implicated="AUC",
                                     fault_hypothesis=Fault.RECONSTRUCTION.value)],
    )
    assert "#e05d44" in render_badge(failing), "a not-reproduced badge must not be upgraded to amber"

    abstained = build_certificate(paper=paper, engine_pin=pin, gap_report=gaps, assessments=[])
    assert "#9f9f9f" in render_badge(abstained), "an abstention must not be upgraded to amber"


def test_a_failed_claim_publishes_every_part_of_its_cause() -> None:
    """The most serious thing this engine says must not be its least explained line.

    The gap report took the *first* of (root cause, implicated, fault hypothesis, discrepancy) and
    dropped the rest. That was invisible while every shortfall was `uncategorized` against the
    claim's own quantity, and became the worst line in the document the moment a real cause
    existed: the twice-daily metformin entry's brain claims rendered as the bare token
    `apparent-manuscript-error` — this engine asserting that a named paper's table is wrong,
    printed beside that paper's DOI, with none of the evidence and no sign that a fault is, in
    `Fault`'s own words, "always a hypothesis, never a proven cause".
    """
    from reprolith import (
        Attribution,
        ClaimAssessment,
        FailureMode,
        Fault,
        PaperIdentity,
        Verdict,
        build_certificate,
    )
    from reprolith.render import render_human

    assessment = ClaimAssessment(
        claim_id="Cmax-brain",
        quantity="Brain Cmax",
        verdict=Verdict.FAILED,
        source_location="Table 7, Brain row",
        discrepancy="relative error 0.2012",
        root_cause=FailureMode.MANUSCRIPT_ERROR.value,
        implicated="Table 7's Brain Cmax, which equals plasma's while its AUC24 is 0.80 of it",
        fault_hypothesis=Fault.MANUSCRIPT.value,
    )
    certificate = build_certificate(
        paper=PaperIdentity(title="a paper", doi="10.0/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[assessment],
    )
    missing = [
        line for line in render_human(certificate, RUN).splitlines()
        if "Cmax-brain" in line and "Brain Cmax" in line
    ]
    (line,) = [line for line in missing if "relative error" in line]
    assert "relative error 0.2012" in line          # what was measured
    assert "apparent-manuscript-error" in line       # the category
    assert "AUC24 is 0.80 of it" in line             # the evidence for it
    assert "fault hypothesis: manuscript" in line    # and that it is a hypothesis
    assert Attribution  # the shape these three fields come from


def test_an_unevaluable_claim_still_falls_back_to_a_sentence() -> None:
    """The fallback the join must not swallow: a claim with nothing to say about a cause."""
    from reprolith import ClaimAssessment, PaperIdentity, Verdict, build_certificate
    from reprolith.render import render_human

    certificate = build_certificate(
        paper=PaperIdentity(title="a paper", doi="10.0/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(
            claim_id="c", quantity="q", verdict=Verdict.NOT_EVALUABLE, source_location="Figure 1",
        )],
    )
    text = render_human(certificate, RUN)
    assert "evaluable output or reference data for this claim" in text


def test_a_value_read_off_a_figure_says_so_on_its_own_claim_line() -> None:
    """The widened band is visible in the human form; the reason for it was not.

    A figure reading is judged in a band twice a printed number's. The machine form has always
    carried `reference_kind`, and the human form showed only the number — a reader saw `<=0.2` and
    could not see that it is `<=0.2` *because* the reference is a measurement of a picture.
    """
    read = _claim(Verdict.REPRODUCED, cid="fig3a", reference_kind="digitized-figure")
    printed = _claim(Verdict.REPRODUCED, cid="table2", reference_kind="numeric")
    rendered = render_human(_cert([read, printed]), RUN)

    assert "[fig3a] AUC: reproduced [figure-reading]" in rendered
    # And only where it applies, so no certificate already published renders differently.
    assert "[table2] AUC: reproduced (" in rendered


def test_one_predicate_decides_what_a_figure_reading_is() -> None:
    """Two surfaces answered this from two shapes, and one of them from a bare string literal.

    The human render walks `render_machine`'s dicts by design, so the human and machine forms
    cannot disagree; `figure_read_claims` walks the certificate's own assessments. Both spelled the
    comparison out, and a rename of the enum member would have left the render silently marking
    nothing while the summary went on listing claims.
    """
    from reprolith import (
        EnginePin,
        PaperIdentity,
        ReferenceKind,
        RunMetadata,
        build_certificate,
        judge_curve,
        render_human,
        render_machine,
    )
    from reprolith.render import figure_read_claims, is_figure_read

    assert is_figure_read(ReferenceKind.DIGITIZED_FIGURE.value)
    assert not is_figure_read(ReferenceKind.NUMERIC.value)
    assert not is_figure_read(None)  # an assessment carrying no kind at all is not a reading

    read = judge_curve(
        claim_id="fig2", quantity="plasma", source_location="Figure 2",
        reference=(1.0, 2.0, 3.0), predicted=(1.0, 2.0, 3.0),
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    printed = judge_curve(
        claim_id="tab1", quantity="plasma", source_location="Table 1",
        reference=(1.0, 2.0, 3.0), predicted=(1.0, 2.0, 3.0),
    )
    cert = build_certificate(
        paper=PaperIdentity(title="one of each", doi="10.1/r"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[read, printed],
    )
    run = RunMetadata(created_at="t", actor="a", tool_version="0.0.1")

    # The three surfaces agree, because they now consult one thing.
    assert figure_read_claims(cert) == ["fig2"]
    assert render_machine(cert, run)["summary"]["figure_read_claims"] == ["fig2"]
    rendered = render_human(cert, run)
    assert "[fig2] plasma: reproduced [figure-reading]" in rendered
    assert "[tab1] plasma: reproduced (source" in rendered  # unmarked, as before


def test_the_machine_summary_says_none_rather_than_omitting_the_field() -> None:
    """So a consumer can tell "nothing was read off a picture" from "this predates the field"."""
    from reprolith import RunMetadata, render_machine

    summary = render_machine(
        _cert([_claim(Verdict.REPRODUCED, cid="c")]),
        RunMetadata(created_at="t", actor="a", tool_version="0.0.1"),
    )["summary"]
    assert summary["figure_read_claims"] == []


def test_the_registry_names_the_classes_no_second_engine_ever_checked() -> None:
    """Cross-engine corroboration reached no reader, and the half that matters is the absence.

    It was computed, committed to each milestone directory, and described in that directory's
    README. The public page publishing the verdicts said nothing either way. Listing only the
    corroborated classes would be worse than saying nothing: a reader would infer the others had
    been checked and passed, which is a clean report standing in for a check nobody made.
    """
    from reprolith.render import _corroboration_banner

    banner = _corroboration_banner(
        {
            "ode-pkpd": {
                "BIOMD1:Cmax": {"engines": ["copasi", "roadrunner"],
                                "engine_independent": True, "distance_at_most": 1e-06},
                "BIOMD1:AUC": {"engines": ["copasi", "roadrunner"],
                               "engine_independent": True, "distance_at_most": 1e-07},
            },
        },
        ["logical", "ode-pkpd", "spatial"],
    )
    assert "ode-pkpd: 2 claim(s) re-run on copasi, roadrunner" in banner
    assert "all engine-independent to 1e-06" in banner  # the weakest bound, not the best
    assert "logical, spatial: no second engine is registered" in banner
    assert "an absence, not a pass" in banner


def test_the_registry_counts_models_as_models_and_claims_as_claims() -> None:
    """The two classes with a second engine corroborate different things, and the record says so.

    PK/PD re-runs each claim at the dose it was certified at, keyed `accession:claim_id`; the
    kinetic class re-runs each model's curve once, keyed by bare accession. Calling six models
    "six claims" publishes a number four times what was checked, so the unit is read off the key.
    """
    from reprolith.render import _corroboration_banner

    banner = _corroboration_banner(
        {"kinetic": {
            "BIOMD5": {"engines": ["copasi", "roadrunner"], "engine_independent": True,
                       "distance_at_most": 1e-04},
        }},
        ["kinetic"],
    )
    assert "kinetic: 1 model(s) re-run" in banner


def test_a_corroboration_that_did_not_hold_is_not_reported_as_holding() -> None:
    """An engine-sensitive claim is the finding this check exists to produce."""
    from reprolith.render import _corroboration_banner

    banner = _corroboration_banner(
        {"ode-pkpd": {
            "BIOMD1:Cmax": {"engines": ["copasi", "roadrunner"], "engine_independent": True,
                            "distance_at_most": 1e-06},
            "BIOMD1:AUC": {"engines": ["copasi", "roadrunner"], "engine_independent": False,
                           "distance_at_most": 0.4},
        }},
        ["ode-pkpd"],
    )
    assert "1 of 2 engine-independent" in banner
    assert "all engine-independent" not in banner


def test_the_dossier_page_counts_a_stated_unit_and_never_the_word_unstated() -> None:
    """A count that says the opposite of the truth is worse than no count.

    `unit` is the string "unstated" when the artifact names none, and a string is truthy — so the
    first version of this line read thirteen values with no unit as thirteen that had one, on the
    very entry whose own gap report says "13 of 37 extracted values state no unit".
    """
    from reprolith.render import render_dossier_human

    page = render_dossier_human({
        "entry": "ACC1",
        "artifacts": [{"filename": "m.xml", "detected_format": "sbml", "validates": True}],
        "parameters": [
            {"name": "k", "value": 1.0, "unit": "unstated", "normalized_unit": None},
            {"name": "V", "value": 2.0, "unit": "unit_0", "normalized_unit": "10^-3 litre"},
        ],
        "state_variables": ["x"],
        "gaps": [
            {"element": "events", "detail": "one event", "load_bearing": True,
             "carried_by_artifact": True},
            {"element": "units", "detail": "no unit", "load_bearing": True,
             "carried_by_artifact": False},
        ],
    })
    assert "parameters: 2 (1 of 2 with a stated unit)" in page
    # The two kinds of gap are not the same finding, and the fix differs: one asks an author to
    # state something, the other says the dossier cannot hold what they already stated.
    assert "the artifact states it; the dossier cannot carry it" in page
    assert "not stated by the artifact" in page


def test_the_bundle_page_leads_with_the_origin_and_the_assumptions() -> None:
    """Its two load-bearing facts, published only inside a dump of every run in the recipe."""
    from reprolith.render import render_bundle_human

    page = render_bundle_human({
        "entry": "ACC1",
        "origin": "author-supplied",
        "model": {"filename": "m.xml", "detected_format": "sbml"},
        "engine_pin": {"engine": "copasi", "version": "4.46", "algorithm": "lsoda"},
        "recipe": [{"time_span": "0-24.0"}, {"time_span": "0-24.0"}],
        "assumptions": [{
            "description": "the doses are the salt", "chosen": "x 129.16/165.62",
            "basis": "the model's default equals 500 mg as free base", "load_bearing": True,
            "alternatives": ["take the dose as stated"],
        }],
        "non_reconstructable": ["one event"],
    })
    assert "origin: author-supplied" in page
    assert "runs: 2 over 0-24.0" in page
    assert "the doses are the salt [load-bearing]" in page
    assert "alternatives: take the dose as stated" in page
    assert "NOT RECONSTRUCTABLE" in page
