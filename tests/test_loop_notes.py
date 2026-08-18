"""The discipline loop's written record covers what it claims to (tasks 7.3 and 7.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith.loop_notes import (
    LoopNote,
    NoteBasis,
    NoteKind,
    audit_loop_notes,
    disagreement_subjects,
    load_loop_notes,
    required_subjects,
    tolerance_default_subjects,
)
from reprolith.oracle import FailureMode

REPO = Path(__file__).resolve().parents[1]
NOTES = REPO / "datasets" / "loop_notes.json"


def committed_reports() -> list[dict]:
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((REPO / "datasets").rglob("agreement_report.json"))
    ]
    assert reports, "the committed agreement reports are what the record is audited against"
    return reports


def test_committed_record_is_complete() -> None:
    """Every disagreement, failure mode, and default tolerance traces to a committed note."""
    audit = audit_loop_notes(load_loop_notes(NOTES), committed_reports(), base_dir=REPO)
    assert audit.complete, audit.summary()


def test_every_disagreement_names_a_stage_and_a_resolution() -> None:
    """Task 7.3: an unresolved disagreement may not sit in the record without an explanation."""
    for note in load_loop_notes(NOTES):
        if note.kind is NoteKind.DISAGREEMENT:
            assert note.stage is not None
            assert note.resolution is not None


def test_loop_notes_disagreement_needs_a_stage() -> None:
    with pytest.raises(ValueError, match="responsible stage"):
        LoopNote(
            id="n", kind=NoteKind.DISAGREEMENT, subjects=("E1",), basis=NoteBasis.OBSERVED,
            note="", evidence=("README.md",),
        )


def test_loop_notes_need_evidence() -> None:
    with pytest.raises(ValueError, match="cites no evidence"):
        LoopNote(
            id="n", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
            basis=NoteBasis.SPEC, note="", evidence=(),
        )


def test_load_refuses_duplicate_ids(tmp_path: Path) -> None:
    record = {
        "id": "dup", "kind": "failure-mode", "subjects": ["uncategorized"], "basis": "spec",
        "note": "", "evidence": ["README.md"],
    }
    path = tmp_path / "notes.json"
    path.write_text(json.dumps({"notes": [record, record]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate loop note id"):
        load_loop_notes(path)


def test_an_unexplained_disagreement_is_a_failure(tmp_path: Path) -> None:
    """The gate's whole point: a new disagreement with no note fails rather than passing quietly."""
    report = {"per_entry": [{"entry": "NEW0000001", "agree": False}]}
    audit = audit_loop_notes(load_loop_notes(NOTES), [*committed_reports(), report], base_dir=REPO)
    assert not audit.complete
    assert audit.uncovered == ("disagreement:NEW0000001",)


def test_a_note_explaining_nothing_is_a_failure() -> None:
    """A subject that no longer exists — a renamed mode, a departed entry — is flagged too."""
    orphan = LoopNote(
        id="orphan", kind=NoteKind.FAILURE_MODE, subjects=("mode-that-was-renamed",),
        basis=NoteBasis.SPEC, note="", evidence=("README.md",),
    )
    audit = audit_loop_notes([*load_loop_notes(NOTES), orphan], committed_reports(), base_dir=REPO)
    assert audit.orphaned == ("failure-mode:mode-that-was-renamed",)


def test_evidence_must_exist_in_the_repository() -> None:
    """A citation nobody can follow is an assertion, which is what the record replaces."""
    invented = LoopNote(
        id="invented", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
        basis=NoteBasis.SPEC, note="", evidence=("docs/a-file-that-does-not-exist.md",),
    )
    audit = audit_loop_notes([invented], committed_reports(), base_dir=REPO)
    assert audit.missing_evidence == ("invented:docs/a-file-that-does-not-exist.md",)


def test_required_subjects_track_the_catalogue_not_a_restatement() -> None:
    """Adding a failure mode or a default tolerance adds something that must be explained."""
    required = required_subjects(committed_reports())
    assert required[NoteKind.FAILURE_MODE] == frozenset(mode.value for mode in FailureMode)
    assert required[NoteKind.TOLERANCE_DEFAULT] == frozenset(tolerance_default_subjects())


def test_abstentions_are_disagreements_that_still_owe_an_explanation() -> None:
    """A blocked verdict never matches a label, so it needs a note like any other disagreement."""
    subjects = disagreement_subjects(committed_reports())
    assert "BIOMD0000001028" in subjects
    assert len(subjects) == 31  # the PK/PD run; the other five classes disagree nowhere
