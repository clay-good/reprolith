"""The discipline loop's written record covers what it claims to (tasks 7.3 and 7.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith.loop_notes import (
    Citation,
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
            note="a written explanation", evidence=(Citation("README.md", ("proof of whether the model reproduces",)),),
        )


def test_a_blank_explanation_is_refused() -> None:
    with pytest.raises(ValueError, match="no written explanation"):
        LoopNote(
            id="n", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
            basis=NoteBasis.SPEC, note="   ", evidence=(Citation("README.md", ("proof of whether the model reproduces",)),),
        )


def test_two_reports_disagreeing_on_one_entry_are_refused() -> None:
    """Entry ids are not unique across classes; a shared id must not borrow another class's note."""
    report = {"per_entry": [{"entry": "BIOMD0000001028", "agree": False}]}
    with pytest.raises(ValueError, match="same entry"):
        disagreement_subjects([*committed_reports(), report])


def test_loop_notes_need_evidence() -> None:
    with pytest.raises(ValueError, match="cites no evidence"):
        LoopNote(
            id="n", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
            basis=NoteBasis.SPEC, note="a written explanation", evidence=(),
        )


def test_load_refuses_duplicate_ids(tmp_path: Path) -> None:
    record = {
        "id": "dup", "kind": "failure-mode", "subjects": ["uncategorized"], "basis": "spec",
        "note": "text", "evidence": [{"path": "README.md", "quotes": ["proof of whether the model reproduces"]}],
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
        basis=NoteBasis.SPEC, note="a written explanation", evidence=(Citation("README.md", ("proof of whether the model reproduces",)),),
    )
    audit = audit_loop_notes([*load_loop_notes(NOTES), orphan], committed_reports(), base_dir=REPO)
    assert audit.orphaned == ("failure-mode:mode-that-was-renamed",)


def test_evidence_must_exist_in_the_repository() -> None:
    """A citation nobody can follow is an assertion, which is what the record replaces."""
    invented = LoopNote(
        id="invented", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
        basis=NoteBasis.SPEC, note="a written explanation", evidence=(Citation("docs/a-file-that-does-not-exist.md", ("a quote nobody can check",)),),
    )
    audit = audit_loop_notes([invented], committed_reports(), base_dir=REPO)
    assert audit.missing_evidence == ("invented:docs/a-file-that-does-not-exist.md (missing)",)


def test_a_citation_must_contain_the_words_it_is_cited_for() -> None:
    """Path existence is not content: a note can otherwise cite the wrong file and pass."""
    misquoted = LoopNote(
        id="misquoted", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
        basis=NoteBasis.SPEC, note="text",
        evidence=(Citation("README.md", ("a sentence the README does not contain",)),),
    )
    audit = audit_loop_notes([misquoted], committed_reports(), base_dir=REPO)
    assert audit.missing_evidence == (
        "misquoted:README.md: 'a sentence the README does not contain'",
    )


def test_a_quote_too_short_to_pin_anything_is_refused() -> None:
    """The empty string is in every file, and one character is in almost every file."""
    for quote in ("", " ", "a", "rev"):
        with pytest.raises(ValueError, match="too short to pin anything"):
            Citation("README.md", (quote,))


def test_a_note_must_cite_something_it_can_be_held_to() -> None:
    with pytest.raises(ValueError, match="cites no evidence it can be held to"):
        LoopNote(
            id="unanchored", kind=NoteKind.FAILURE_MODE, subjects=("uncategorized",),
            basis=NoteBasis.SPEC, note="text", evidence=(Citation("README.md"),),
        )


def test_required_subjects_track_the_catalogue_not_a_restatement() -> None:
    """Adding a failure mode or a default tolerance adds something that must be explained."""
    required = required_subjects(committed_reports())
    assert required[NoteKind.FAILURE_MODE] == frozenset(mode.value for mode in FailureMode)
    assert required[NoteKind.TOLERANCE_DEFAULT] == frozenset(tolerance_default_subjects())


def test_abstentions_are_disagreements_that_still_owe_an_explanation() -> None:
    """A blocked verdict never matches a label, so it needs a note like any other disagreement.

    Counted as "every PK/PD entry that did not match its label", which is what a disagreement is,
    rather than as the literal 31 — the mouse oral-dose entry became the class's first agreement
    and the count moved. The other five classes disagree nowhere.
    """
    import json
    from pathlib import Path

    subjects = disagreement_subjects(committed_reports())
    assert "BIOMD0000001028" in subjects
    report = json.loads(
        (Path(__file__).parent.parent / "datasets/milestone/agreement_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(subjects) == report["total"] - report["agreements"]
    assert report["agreements"] >= 1, "no PK/PD entry agrees; this check would pass vacuously"


def test_a_citation_of_source_must_find_the_words_in_code_that_runs(tmp_path) -> None:
    """A commented-out line satisfied a citation, so a fixed defect could be restored under it.

    Demonstrated: restoring the stochastic root-cause defect while leaving the original line in
    place as a comment kept this gate green, because it matched the raw file. The note's whole job
    is to point at evidence that holds; a line that no longer runs is not that.
    """
    from reprolith.loop_notes import Citation

    source = tmp_path / "python" / "reprolith"
    source.mkdir(parents=True)
    quote = "attribution = undetermined_shortfall(claim.quantity)"
    citation = Citation(path="python/reprolith/mod.py", quotes=(quote,))

    (source / "mod.py").write_text(f"def f():\n    {quote}\n", encoding="utf-8")
    assert citation.unmet(tmp_path) == []

    (source / "mod.py").write_text(f"def f():\n    # {quote}\n    pass\n", encoding="utf-8")
    assert citation.unmet(tmp_path), "a commented-out line must not satisfy a citation"

    # Prose files are matched whole — a markdown line beginning with '#' is a heading.
    (tmp_path / "notes.md").write_text("# A heading worth citing\n", encoding="utf-8")
    heading = Citation(path="notes.md", quotes=("# A heading worth citing",))
    assert heading.unmet(tmp_path) == []


def test_a_source_quote_that_matches_more_than_one_line_is_refused(tmp_path) -> None:
    """A quote is evidence only if it is unique — enforced, not merely written down.

    One tolerance note quoted `0.10, 0.25, ToleranceSource.CLASS_DEFAULT`, which also matches a
    different constant in the same file, so widening the tolerance the note exists to pin left it
    satisfied by a line it does not cite. That was found by hand and the lesson recorded; a lesson
    in a document does not fail a build.
    """
    from reprolith.loop_notes import Citation

    source = tmp_path / "python" / "reprolith"
    source.mkdir(parents=True)
    quote = "0.10, 0.25, ToleranceSource.CLASS_DEFAULT"
    citation = Citation(path="python/reprolith/mod.py", quotes=(quote,))

    (source / "mod.py").write_text(f"A = Tolerance(\n    {quote}\n)\n", encoding="utf-8")
    assert citation.unmet(tmp_path) == []

    (source / "mod.py").write_text(
        f"A = Tolerance(\n    {quote}\n)\nB = Tolerance({quote})\n", encoding="utf-8"
    )
    problems = citation.unmet(tmp_path)
    assert problems and "occurs 2 times" in problems[0], problems

    # Prose is exempt: a phrase recurring in a document is ordinary.
    (tmp_path / "notes.md").write_text("a repeated phrase\nand a repeated phrase\n", encoding="utf-8")
    assert Citation(path="notes.md", quotes=("a repeated phrase",)).unmet(tmp_path) == []
