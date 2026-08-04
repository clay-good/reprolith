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
    return ClaimAssessment(
        claim_id=cid, quantity="AUC", verdict=verdict, source_location="Fig 2",
        assumption_qualified=qualified, **kw,
    )


def _cert(assessments, **kw):
    return build_certificate(
        paper=PaperIdentity(title="Two-compartment PK model", doi="10.1/x"),
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
