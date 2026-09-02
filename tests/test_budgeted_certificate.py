"""A certificate produced under a budget, and what it is forbidden to leave unsaid.

Pure policy, no engine: the point is what the certificate *records*, not what a run produced. The
spec is ``reproduction-certificate`` — "A certificate records the claims it did not attempt" — and
its three scenarios are the first three tests here. The rest guard the two ways the field could be
made to lie: a claim that appears as both judged and unattempted, and a selection made over some
other paper's claims.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    Claim,
    ClaimAssessment,
    ClaimSelection,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    RunMetadata,
    Selection,
    UnattemptedClaim,
    Verdict,
    build_certificate,
    certificate_from_content,
    plan_under_budget,
    render_human,
    render_machine,
)

_PAPER = PaperIdentity(title="A paper with more claims than budget")
_PIN = EnginePin(engine="test-engine", version="1.0")
_RUN = RunMetadata(created_at="2026-09-02T00:00:00Z", actor="tests", tool_version="0")


def _judged(cid: str, verdict: Verdict = Verdict.REPRODUCED) -> ClaimAssessment:
    return ClaimAssessment(
        claim_id=cid,
        quantity=f"{cid} concentration",
        verdict=verdict,
        source_location="Table 2",
        root_cause="uncategorized" if verdict in (Verdict.PARTIAL, Verdict.FAILED) else None,
    )


def _unattempted(*ids: str) -> tuple[UnattemptedClaim, ...]:
    return tuple(
        UnattemptedClaim(claim_id=cid, quantity=f"{cid} concentration", source_location="Table 2")
        for cid in ids
    )


def _selection(*ids: str, budget: float = 3.0) -> ClaimSelection:
    return ClaimSelection(budget=budget, objective="test objective", unattempted=_unattempted(*ids))


def _certificate(judged: list[str], unattempted: list[str], **kwargs: object) -> object:
    return build_certificate(
        paper=_PAPER,
        engine_pin=_PIN,
        assessments=[_judged(cid) for cid in judged],
        selection=_selection(*unattempted) if unattempted else None,
        **kwargs,  # type: ignore[arg-type]
    )


# --- the spec's three scenarios ------------------------------------------------------


def test_an_unattempted_claim_is_present_and_carries_no_verdict() -> None:
    cert = _certificate(["a", "b", "c"], ["d", "e"])
    machine = render_machine(cert, _RUN)

    listed = [claim["claim_id"] for claim in machine["summary"]["unattempted_claims"]]
    assert listed == ["d", "e"]
    # The budget and the objective that excluded them travel with them: a reader cannot contest a
    # choice whose criterion is unstated.
    assert machine["content"]["selection"]["budget"] == 3.0
    assert machine["content"]["selection"]["objective"] == "test objective"

    # No verdict counter counts them, and no surface reports them as anything.
    counts = machine["summary"]["claim_counts"]
    assert sum(counts.values()) == 3
    assert counts["not-evaluable"] == 0
    assert {claim["claim_id"] for claim in machine["content"]["assessments"]} == {"a", "b", "c"}
    for item in machine["gaps"]:
        assert item["claim_id"] not in {"d", "e"}

    # …and the count a reader compares them against is the paper's, not the attempt's.
    assert machine["summary"]["claims_in_paper"] == 5


def test_a_clean_sweep_of_the_attempted_claims_is_not_an_unqualified_reproduction() -> None:
    budgeted = _certificate(["a", "b", "c"], ["d", "e"])
    assert budgeted.overall is OverallVerdict.PARTIALLY_REPRODUCED

    # The same three claims with nothing left over is the clean pass — so what withheld the word
    # is the selection, not anything about the claims that were run.
    assert _certificate(["a", "b", "c"], []).overall is OverallVerdict.REPRODUCED


def test_an_unbudgeted_certificate_is_unchanged_and_every_published_digest_regenerates() -> None:
    cert = _certificate(["a", "b", "c"], [])
    assert cert.selection is None
    assert "selection" not in cert.content()
    assert "unattempted_claims" not in render_machine(cert, _RUN)["summary"]

    # The published corpus, read back and re-serialized through the field's own load path. Any
    # difference here is a changed digest for a certificate that is already public.
    stored = sorted((Path(__file__).resolve().parent.parent / "datasets").glob(
        "*/certificates/*.json"
    ))
    assert stored, "expected the published certificates to be committed"
    for path in stored:
        content = json.loads(path.read_text(encoding="utf-8"))
        assert certificate_from_content(content).content() == content


# --- the two ways the record could be made to lie -------------------------------------


def test_a_claim_cannot_be_both_judged_and_unattempted() -> None:
    with pytest.raises(ValueError, match="both judge a claim and say it never ran it"):
        build_certificate(
            paper=_PAPER,
            engine_pin=_PIN,
            assessments=[_judged("a")],
            selection=_selection("a"),
        )


def test_the_load_path_refuses_the_contradiction_the_builder_refuses() -> None:
    cert = _certificate(["a"], ["b"])
    content = cert.content()
    # A hand-edited file claiming it did not attempt the one claim it published a verdict for.
    content["selection"]["unattempted"][0]["claim_id"] = "a"
    with pytest.raises(ValueError, match="both judge a claim and say it never ran it"):
        certificate_from_content(content)


def test_a_selection_never_rescues_a_miss() -> None:
    # Every honesty rule here runs in one direction: a budget can only withhold the clean pass.
    cert = build_certificate(
        paper=_PAPER,
        engine_pin=_PIN,
        assessments=[_judged("a", Verdict.FAILED), _judged("b", Verdict.FAILED)],
        selection=_selection("c"),
    )
    assert cert.overall is OverallVerdict.NOT_REPRODUCED


def test_a_selection_states_its_budget_and_its_objective() -> None:
    with pytest.raises(ValueError, match="objective"):
        ClaimSelection(budget=3.0, objective="   ", unattempted=_unattempted("a"))
    with pytest.raises(ValueError, match="budget must be positive"):
        ClaimSelection(budget=0.0, objective="test objective")


def test_the_stored_verdict_is_rechecked_against_the_stored_selection() -> None:
    # A file whose selection was deleted to promote its own verdict: the attempted claims all
    # reproduced, so without the record the qualified verdict no longer follows from the evidence.
    content = _certificate(["a", "b"], ["c"]).content()
    del content["selection"]
    with pytest.raises(ValueError, match="does not follow from its own"):
        certificate_from_content(content)


def test_a_selection_round_trips_through_storage() -> None:
    cert = _certificate(["a"], ["b", "c"])
    reloaded = certificate_from_content(json.loads(json.dumps(cert.content())))
    assert reloaded.content() == cert.content()
    assert reloaded.selection is not None
    assert [claim.claim_id for claim in reloaded.selection.unattempted] == ["b", "c"]


def test_the_author_report_says_what_was_never_checked() -> None:
    """The author-facing surface has the same silence problem and the same answer.

    An author reading a clean fix list under a budgeted certificate is reading "nothing to fix"
    about three of their fourteen claims. It is not a fix — nothing here is theirs to fix — so it
    is stated as what it is, and it gates nothing that was not already gated.
    """
    from reprolith.presubmission import presubmission_report, render_presubmission_human

    cert = _certificate(["a", "b", "c"], ["d", "e"])
    report = presubmission_report(cert)
    assert report["ready_to_submit"] is False  # a budgeted certificate is never an unqualified pass
    assert [claim["claim_id"] for claim in report["not_attempted"]] == ["d", "e"]
    assert report["claims_in_paper"] == 5

    text = render_presubmission_human(cert)
    assert "NOT CHECKED (a budget chose against these — not a fix, and not your doing)" in text
    assert "2 of your paper's 5 claims" in text
    # And an unbudgeted report is exactly what it was.
    assert "NOT CHECKED" not in render_presubmission_human(_certificate(["a"], []))
    assert "not_attempted" not in presubmission_report(_certificate(["a"], []))


def test_the_public_registry_card_counts_the_paper_not_the_attempt() -> None:
    """The registry is the one surface a reader cannot ask a follow-up question of.

    Its card prints the verdict counts, which are counts of what was attempted — so under a budget
    it would publish `reproduced=3` beside an amber badge and nothing to say what the three were
    three of.
    """
    from reprolith.render import render_registry

    page = render_registry([("ode-pkpd", _certificate(["a", "b", "c"], ["d", "e"]))])
    assert "reproduced=3 (of 5 claims in the paper; 2 not attempted under a budget)" in page
    # And a card for a certificate with no budget is what it always was.
    assert "not attempted under a budget" not in render_registry(
        [("ode-pkpd", _certificate(["a"], []))]
    )


# --- the join between choosing and certifying ------------------------------------------


def _claims(*ids: str) -> list[Claim]:
    return [
        Claim(
            claim_id=cid,
            quantity=f"{cid} concentration",
            species="plasma",
            reported=1.0,
            source_location="Table 2",
        )
        for cid in ids
    ]


def _chosen(*ids: str) -> Selection:
    return Selection(
        chosen=tuple(ids),
        score=1.0,
        gross_value=1.0,
        overlap_penalty=0.0,
        cost=float(len(ids)),
        budget=float(len(ids)),
        method="exhaustive",
    )


def test_planning_under_a_budget_partitions_the_paper_exactly() -> None:
    chosen, record = plan_under_budget(_claims("a", "b", "c", "d"), _chosen("a", "c"))
    assert [claim.claim_id for claim in chosen] == ["a", "c"]
    assert [claim.claim_id for claim in record.unattempted] == ["b", "d"]
    assert record.budget == 2.0
    # The objective the certificate records names the search that produced the set, because a
    # local search's answer is not proven optimal and a reader weighing what was skipped should
    # not have to guess which one they are reading.
    assert "exhaustive" in record.objective


def test_a_selection_made_over_other_claims_is_refused() -> None:
    with pytest.raises(ValueError, match="different set of claims"):
        plan_under_budget(_claims("a", "b"), _chosen("a", "z"))


# --- what a reader is shown --------------------------------------------------------


def test_the_human_certificate_says_what_it_did_not_look_at() -> None:
    text = render_human(_certificate(["a", "b", "c"], ["d", "e"]), _RUN)
    assert "claims: 5 in the paper, 3 attempted, 2 left unattempted under a budget" in text
    assert "NOT ATTEMPTED (chosen against by a budget, not judged)" in text
    assert "[d] d concentration" in text
    assert "neither reproduced nor unreproduced" in text
    # And an unbudgeted certificate renders exactly as it always has.
    assert "NOT ATTEMPTED" not in render_human(_certificate(["a"], []), _RUN)
