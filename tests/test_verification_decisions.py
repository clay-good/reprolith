"""An expert's answer has to survive the process that recorded it.

`VerificationQueue.decide` and `reverify_dependents` were both built, and neither could be reached
from outside one Python process: the queue is derived from the standing certificates on every call
and stored nowhere, so a decision made against it evaporated with the interpreter. The consequence
was visible on the repository's own surfaces — `verification-queue` printed the same items as
pending for as long as the certificates stood, under a hard-coded sentence saying no decision was
stored — while CONTRIBUTING.md told experts their decision "becomes the record".

These tests hold the committed record to the three things that make it worth trusting: it refuses
a record nobody could act on, it detects a decision that has come to sit under a reworded question,
and it never lets an answer read as a re-certification.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    RecordedDecision,
    Verdict,
    build_certificate,
    decisions_document,
    load_decisions,
    question_fingerprint,
    queue_report,
)
from reprolith.determinism import certificate_digest
from reprolith.mcp_server import repository_data_root, repository_decisions

PIN = EnginePin(engine="copasi", version="4.46")


def _assumption(**kw):
    base = dict(
        id="a",
        description="what time unit does the deposit mean",
        chosen="hours",
        basis="the dynamics settle it",
        load_bearing=True,
        alternatives=("the declared 100 hours",),
    )
    base.update(kw)
    return Assumption(**base)


def _cert(*assumptions, title="t"):
    return build_certificate(
        paper=PaperIdentity(title=title),
        engine_pin=PIN,
        assessments=[
            ClaimAssessment(
                claim_id="c1",
                quantity="AUC",
                verdict=Verdict.REPRODUCED,
                source_location="T1",
                assumption_qualified=bool(assumptions),
            )
        ],
        assumptions=list(assumptions),
    )


def _pairs(*certs):
    return [(certificate_digest(c), c) for c in certs]


def _decision(item_id, assumption, **kw):
    base = dict(
        item_id=item_id,
        question_fingerprint=question_fingerprint(assumption),
        kind="confirm",
        expert="A. Curator",
        rationale="the deposited unit contradicts the paper's own tables",
        decided_on="2026-09-06",
        source="https://example.invalid/issues/1",
    )
    base.update(kw)
    return RecordedDecision(**base)


# --- what a record must carry to be actionable ---------------------------------------------


@pytest.mark.parametrize(
    "missing", ["item_id", "question_fingerprint", "kind", "expert", "rationale", "decided_on", "source"]
)
def test_a_record_missing_any_field_is_refused(missing: str) -> None:
    raw = _decision("verify:x", _assumption()).to_dict()
    raw[missing] = "  "
    with pytest.raises(ValueError, match=missing):
        RecordedDecision.from_dict(raw)


def test_a_correction_with_nothing_to_correct_to_is_refused() -> None:
    raw = _decision("verify:x", _assumption(), kind="correct").to_dict()
    with pytest.raises(ValueError, match="supplies no corrected value"):
        RecordedDecision.from_dict(raw)


def test_a_confirmation_carrying_a_corrected_value_is_refused() -> None:
    """It would read as changing the value while changing nothing: only a correction replaces
    the estimate, so a confirmation with one in it is a record whose two halves disagree."""
    raw = _decision("verify:x", _assumption()).to_dict()
    raw["corrected_value"] = "100 hours"
    with pytest.raises(ValueError, match="carries a corrected value"):
        RecordedDecision.from_dict(raw)


def test_an_unorderable_date_is_refused() -> None:
    raw = _decision("verify:x", _assumption(), decided_on="6 Sept 2026").to_dict()
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        RecordedDecision.from_dict(raw)


def test_a_kind_nothing_acts_on_is_refused() -> None:
    raw = _decision("verify:x", _assumption(), kind="noted").to_dict()
    with pytest.raises(ValueError, match="decision kind"):
        RecordedDecision.from_dict(raw)


def test_a_record_round_trips_through_the_file(tmp_path: Path) -> None:
    decision = _decision("verify:x", _assumption())
    file = tmp_path / "d.json"
    file.write_text(json.dumps(decisions_document([decision])), encoding="utf-8")
    assert load_decisions(file) == (decision,)


def test_a_missing_file_is_not_an_empty_queue(tmp_path: Path) -> None:
    # "nobody has decided anything" and "this path is wrong" are different facts, and the surfaces
    # read this on the way to a page that says which.
    with pytest.raises(FileNotFoundError, match="wrong path"):
        load_decisions(tmp_path / "absent.json")


def test_the_committed_file_parses_and_the_repository_reads_it() -> None:
    file = repository_data_root() / "verification_decisions.json"
    assert file.is_file(), "the decisions file is committed data; the surfaces read it by path"
    assert load_decisions(file) == repository_decisions()


# --- how a decision reaches the queue --------------------------------------------------------


def test_a_decided_item_leaves_pending() -> None:
    assumption = _assumption(verification_item="verify:named")
    cert = _cert(assumption)
    report = queue_report(_pairs(cert), [_decision("verify:named", assumption)])
    assert report["pending"] == []
    assert [item["id"] for item in report["decided"]] == ["verify:named"]
    assert report["decided"][0]["decisions"][0]["expert"] == "A. Curator"


def test_an_undecided_item_is_untouched_by_a_decision_on_another() -> None:
    one = _assumption(id="one", verification_item="verify:one")
    two = _assumption(id="two", description="another question", verification_item="verify:two")
    report = queue_report(_pairs(_cert(one, two)), [_decision("verify:one", one)])
    assert [item["id"] for item in report["pending"]] == ["verify:two"]
    assert [item["id"] for item in report["decided"]] == ["verify:one"]


def test_a_decision_does_not_lift_the_certificate_qualification() -> None:
    """The misreading this section can cause, held shut. A confirmed value is still a value whose
    certificates were computed while it was unreviewed; lifting that means re-issuing them.
    """
    assumption = _assumption(verification_item="verify:named")
    cert = _cert(assumption)
    report = queue_report(_pairs(cert), [_decision("verify:named", assumption)])
    item = report["decided"][0]
    assert item["dependents_reissued"] is False
    assert "withhold a clean pass" in item["qualification"]
    # And the certificate itself is unchanged: the assumption is still load-bearing, so the
    # claim it qualifies is still qualified.
    assert cert.assessments[0].assumption_qualified is True


def test_a_rejection_says_the_dependents_cannot_be_re_issued() -> None:
    assumption = _assumption(verification_item="verify:named")
    report = queue_report(
        _pairs(_cert(assumption)), [_decision("verify:named", assumption, kind="reject")]
    )
    assert "has to be corrected" in report["decided"][0]["action_required"]


def test_disagreement_is_kept_as_disagreement() -> None:
    assumption = _assumption(verification_item="verify:named")
    report = queue_report(
        _pairs(_cert(assumption)),
        [
            _decision("verify:named", assumption, expert="One"),
            _decision(
                "verify:named",
                assumption,
                kind="correct",
                corrected_value="100 hours",
                expert="Two",
            ),
        ],
    )
    item = report["decided"][0]
    assert item["disputed"] is True
    assert [d["expert"] for d in item["decisions"]] == ["One", "Two"]


# --- what stops a decision from being trusted ------------------------------------------------


def test_a_decision_on_a_reworded_question_goes_stale_and_its_item_is_pending_again() -> None:
    """The failure mode a stored decision has and an in-memory one never did.

    A *derived* id is the digest of its own question, so nothing can slip underneath it. An id the
    certificate **names** is an author's string, and the wording, the basis and the alternatives
    under it can all change with the id unchanged — attributing an answer to an expert for a
    question they never read.
    """
    answered = _assumption(verification_item="verify:named")
    reworded = _assumption(
        verification_item="verify:named", basis="a different reason entirely"
    )
    report = queue_report(_pairs(_cert(reworded)), [_decision("verify:named", answered)])
    assert [item["id"] for item in report["pending"]] == ["verify:named"]
    assert report["decided"] == []
    stale = report["stale_decisions"]
    assert len(stale) == 1
    assert stale[0]["current_question_fingerprint"] == question_fingerprint(reworded)
    # And it is shown on the item, so the next expert does not silently repeat the work.
    assert report["pending"][0]["stale_decisions"] == stale


def test_a_decision_naming_nothing_standing_is_reported_not_dropped() -> None:
    assumption = _assumption(verification_item="verify:named")
    report = queue_report(_pairs(_cert(assumption)), [_decision("verify:gone", assumption)])
    assert [item["id"] for item in report["pending"]] == ["verify:named"]
    assert [d["item_id"] for d in report["orphaned_decisions"]] == ["verify:gone"]


def test_a_derived_id_cannot_carry_a_decision_from_a_different_question() -> None:
    """The other half of the fingerprint check, and the reason it is cheap: for an unnamed item
    the id already *is* the question, so a reworded assumption produces a different id and the old
    decision is orphaned rather than misapplied."""
    original = _assumption()
    reworded = _assumption(chosen="the declared 100 hours")
    derived = queue_report(_pairs(_cert(original)))["pending"][0]["id"]
    report = queue_report(_pairs(_cert(reworded)), [_decision(derived, original)])
    assert report["decided"] == []
    assert [d["item_id"] for d in report["orphaned_decisions"]] == [derived]


# --- the note the surfaces print -------------------------------------------------------------


def test_the_decisions_note_is_derived_from_the_record_not_asserted() -> None:
    """It used to be a constant reading "nothing on disk carries one yet" — true of the
    repository, false of the software the moment a decision was recorded."""
    assumption = _assumption(verification_item="verify:named")
    empty = queue_report(_pairs(_cert(assumption)))
    assert "no expert decision is recorded" in empty["decisions_note"]
    decided = queue_report(_pairs(_cert(assumption)), [_decision("verify:named", assumption)])
    assert "1 expert decision(s) recorded" in decided["decisions_note"]
    assert "still carry the value as unreviewed" in decided["decisions_note"]


def test_the_queue_is_still_order_independent_with_decisions() -> None:
    assumption = _assumption(verification_item="verify:named")
    pairs = _pairs(_cert(assumption, title="one"), _cert(assumption, title="two"))
    decisions = [_decision("verify:named", assumption)]
    assert queue_report(pairs, decisions) == queue_report(list(reversed(pairs)), decisions)


# --- the surfaces a person actually reads ----------------------------------------------------


def _write_repo(tmp_path: Path, assumption: Assumption) -> Path:
    from reprolith import Catalog, GroundTruth, Identifiers, ModelClass, OverallVerdict

    catalog = Catalog()
    catalog.add(
        Identifiers(title="t", doi="10.1/x", accession="ACC1"),
        ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="curation"),
    )
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    cert = _cert(assumption)
    certs = tmp_path / "certificates"
    certs.mkdir()
    (certs / f"{certificate_digest(cert)}.json").write_text(
        json.dumps(cert.content(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return tmp_path


def test_the_terminal_shows_a_decided_item_and_says_it_is_still_qualified(
    tmp_path, capsys, monkeypatch
) -> None:
    """The whole point of recording a decision is that somebody reads it back. Held on the
    terminal because that is the surface CONTRIBUTING.md points an expert at."""
    from reprolith import mcp_server
    from reprolith.cli import run

    assumption = _assumption(verification_item="verify:named")
    repo = _write_repo(tmp_path, assumption)
    monkeypatch.setattr(
        mcp_server, "repository_decisions", lambda: (_decision("verify:named", assumption),)
    )
    assert run(["--data-dir", str(repo), "verification-queue"]) == 0
    out = capsys.readouterr().out
    assert "DECIDED" in out
    assert "confirmed by A. Curator on 2026-09-06" in out
    assert "https://example.invalid/issues/1" in out
    assert "withhold a clean pass" in out
    # And it is no longer listed as waiting for the expert who just answered it.
    assert "AWAITING EXPERT REVIEW" not in out


def test_the_registry_page_publishes_the_answer_with_its_qualification() -> None:
    from reprolith import render_registry

    assumption = _assumption(verification_item="verify:named")
    page = render_registry(
        [("ode-pkpd", _cert(assumption))], decisions=[_decision("verify:named", assumption)]
    )
    assert "Answered by an expert" in page
    assert "A. Curator" in page
    assert "not a re-certification" in page
    assert "Awaiting expert review" not in page


def test_a_hand_edited_decisions_file_that_no_longer_parses_is_a_message(
    tmp_path, capsys, monkeypatch
) -> None:
    """CONTRIBUTING.md asks an expert to write a record by hand in a pull request, which makes a
    typo in it an ordinary mistake rather than a bug. A traceback is not an answer to one."""
    from reprolith import mcp_server
    from reprolith.cli import run

    repo = _write_repo(tmp_path, _assumption())
    bad = tmp_path / "verification_decisions.json"
    bad.write_text('{"decisions": [{"kind": "confirm"}]}', encoding="utf-8")
    monkeypatch.setattr(mcp_server, "repository_decisions", lambda: load_decisions(bad))
    assert run(["--data-dir", str(repo), "verification-queue"]) == 1
    assert "is missing" in capsys.readouterr().err


def test_the_queue_publishes_the_fingerprint_a_decision_has_to_quote() -> None:
    """CONTRIBUTING.md tells an expert to copy it into the record they merge, so a queue that
    derives it and does not show it leaves that record's one non-obvious field unobtainable."""
    assumption = _assumption(verification_item="verify:named")
    report = queue_report(_pairs(_cert(assumption)))
    assert report["pending"][0]["question_fingerprint"] == question_fingerprint(assumption)


def test_a_decision_on_an_engine_limit_does_not_move_it_out_of_its_own_heading() -> None:
    """Caught re-auditing the diff that added decisions, and it is the shape this repository
    keeps finding: two halves of one feature disagreeing. The report says in so many words that
    no expert decision closes an engine limit, and `issue_for_item` refuses to file one as a
    question — while a recorded decision silently moved it under "decided", publishing an expert
    as having settled exactly what the other two surfaces say they cannot.
    """
    assumption = _assumption(verification_item="verify:limit", author_can_close=False)
    report = queue_report(_pairs(_cert(assumption)), [_decision("verify:limit", assumption)])
    assert [item["id"] for item in report["decided"]] == []
    assert [item["id"] for item in report["engine_limits"]] == ["verify:limit"]
    limit = report["engine_limits"][0]
    # Not hidden either: the decision is a real record and is shown where it was made.
    assert [d["expert"] for d in limit["decisions"]] == ["A. Curator"]
    assert "does not close it" in limit["decisions_do_not_close"]
    assert "no decision closes" in report["decisions_note"]


def test_the_terminal_shows_such_a_decision_under_the_engine_limit(tmp_path, capsys, monkeypatch) -> None:
    from reprolith import mcp_server
    from reprolith.cli import run

    assumption = _assumption(verification_item="verify:limit", author_can_close=False)
    repo = _write_repo(tmp_path, assumption)
    monkeypatch.setattr(
        mcp_server, "repository_decisions", lambda: (_decision("verify:limit", assumption),)
    )
    assert run(["--data-dir", str(repo), "verification-queue"]) == 0
    out = capsys.readouterr().out
    assert "NOT WAITING ON ANYONE" in out
    assert "DECIDED" not in out
    assert "does not close it" in out
    assert "confirmed by A. Curator" in out
