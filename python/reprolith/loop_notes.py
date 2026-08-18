"""The discipline loop's written record (tasks 7.3 and 7.4).

The loop is: run blind, compare to ground truth, and for every disagreement write a note saying
which stage was responsible and whether it was fixed or explained (spec: ``model-catalog`` — "the
disagreement carries a written defect note and either a fix that was re-run or a recorded
explanation"). The same notes are what make the failure-mode catalogue and the tolerance defaults
*evidence-driven rather than guessed up front* (design: "The discipline loop") — each category and
each default names what put it there.

Prose in a README cannot enforce that. This module makes the record machine-checkable: it loads
the committed notes and audits them against what actually needs explaining — every disagreeing
entry in every committed agreement report, every :class:`~reprolith.oracle.FailureMode`, and every
default tolerance. A new disagreement with no note, or a new failure mode nobody justified, is a
gate failure rather than a quiet omission; and a note whose subject no longer exists is flagged
too, so the record cannot drift away from the thing it explains.

The honesty rule the notes themselves carry is :class:`NoteBasis`. A category the loop actually
produced is ``observed``; a threshold a deliberate measurement set is ``measured``; a category a
class spec requires but no run has yet emitted is ``spec`` — never dressed up as loop experience
it does not have.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .oracle import FailureMode, default_tolerance_table

# Tolerance defaults that are not keyed by (method, reference kind): the estimation level's wider
# default (oracle: ``estimation_default_tolerance``) and the zero-slack tolerance an exact
# comparison declares (an attractor set, a FROG fingerprint).
ESTIMATION_LEVEL = "estimation-level"
EXACT_MATCH = "exact-match"


class NoteKind(str, Enum):
    """What a note explains."""

    DISAGREEMENT = "disagreement"
    FAILURE_MODE = "failure-mode"
    TOLERANCE_DEFAULT = "tolerance-default"


class NoteBasis(str, Enum):
    """What the note rests on — the difference between experience and a requirement.

    ``OBSERVED`` a blind run produced it; ``MEASURED`` a deliberate measurement set the number;
    ``SPEC`` a class spec requires the category and no run has emitted it yet. Keeping ``SPEC``
    distinct is the point: a catalogue entry nobody has seen fire must not read as loop evidence.
    """

    OBSERVED = "observed"
    MEASURED = "measured"
    SPEC = "spec"


class LoopStage(str, Enum):
    """The pipeline stage a disagreement was traced to."""

    INGEST = "ingest"
    RECONSTRUCT = "reconstruct"
    ORACLE = "oracle"
    TOLERANCE = "tolerance"
    LABEL = "label"


class Resolution(str, Enum):
    """How a disagreement was closed: a fix that was re-run, or a recorded explanation."""

    FIXED = "fixed"
    EXPLAINED = "explained"


@dataclass(frozen=True)
class LoopNote:
    """One written note: what it explains, what it rests on, and where to check it."""

    id: str
    kind: NoteKind
    subjects: tuple[str, ...]
    basis: NoteBasis
    note: str
    evidence: tuple[str, ...]
    stage: LoopStage | None = None
    resolution: Resolution | None = None

    def __post_init__(self) -> None:
        if not self.subjects:
            raise ValueError(f"loop note {self.id!r} explains nothing: no subjects")
        if not self.evidence:
            # A note with nowhere to check it is an assertion, which is what this record exists
            # to replace.
            raise ValueError(f"loop note {self.id!r} cites no evidence")
        if not self.note.strip():
            # The written explanation is the whole artifact. A blank one covers its subjects and
            # passes the audit while explaining nothing, which is the failure this record exists
            # to make impossible.
            raise ValueError(f"loop note {self.id!r} has no written explanation")
        if self.kind is NoteKind.DISAGREEMENT and (self.stage is None or self.resolution is None):
            raise ValueError(
                f"loop note {self.id!r} explains a disagreement, so it must name the responsible "
                "stage and whether it was fixed or explained"
            )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> LoopNote:
        stage = record.get("stage")
        resolution = record.get("resolution")
        return cls(
            id=str(record["id"]),
            kind=NoteKind(record["kind"]),
            subjects=tuple(str(s) for s in record["subjects"]),
            basis=NoteBasis(record["basis"]),
            note=str(record["note"]),
            evidence=tuple(str(e) for e in record["evidence"]),
            stage=LoopStage(stage) if stage else None,
            resolution=Resolution(resolution) if resolution else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "subjects": list(self.subjects),
            "basis": self.basis.value,
            "note": self.note,
            "evidence": list(self.evidence),
            "stage": self.stage.value if self.stage else None,
            "resolution": self.resolution.value if self.resolution else None,
        }


def load_loop_notes(path: Path | str) -> tuple[LoopNote, ...]:
    """Load the committed loop notes, refusing duplicate ids."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    notes = tuple(LoopNote.from_record(record) for record in data["notes"])
    seen: set[str] = set()
    for note in notes:
        if note.id in seen:
            raise ValueError(f"duplicate loop note id {note.id!r}")
        seen.add(note.id)
    return notes


def tolerance_default_subjects() -> tuple[str, ...]:
    """Every default tolerance that has to trace to a note, named as a subject."""
    keyed = tuple(
        f"{method.value}/{reference_kind.value}"
        for method, reference_kind in default_tolerance_table()
    )
    return tuple(sorted(keyed)) + (ESTIMATION_LEVEL, EXACT_MATCH)


def disagreement_subjects(reports: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Every entry whose blind verdict differed from its label, across the given reports.

    An abstention is a disagreement (``run.py``'s blocked path), so it needs a note like any
    other: "we abstained, and here is why" is exactly the explanation the loop owes.
    """
    subjects: list[str] = []
    for report in reports:
        for row in report.get("per_entry", []):
            if row.get("agree", False):
                continue
            entry = str(row["entry"])
            if entry in subjects:
                # Entry ids are not globally unique across classes — PK/PD and kinetic both draw
                # from the BioModels id space. Two reports disagreeing on the same id would be
                # covered by whichever note named it first, so one class's disagreement could be
                # "explained" by a note about another class entirely. Refuse instead.
                raise ValueError(
                    f"two agreement reports disagree on the same entry {entry!r}; a note naming "
                    "it cannot say which class it explains"
                )
            subjects.append(entry)
    return tuple(sorted(subjects))


def required_subjects(reports: Iterable[Mapping[str, Any]]) -> dict[NoteKind, frozenset[str]]:
    """What the record must explain, derived from the artifacts rather than restated by hand."""
    return {
        NoteKind.DISAGREEMENT: frozenset(disagreement_subjects(reports)),
        NoteKind.FAILURE_MODE: frozenset(mode.value for mode in FailureMode),
        NoteKind.TOLERANCE_DEFAULT: frozenset(tolerance_default_subjects()),
    }


@dataclass(frozen=True)
class LoopNoteAudit:
    """Whether the written record covers what needs explaining, and nothing that does not."""

    uncovered: tuple[str, ...]
    orphaned: tuple[str, ...]
    missing_evidence: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not (self.uncovered or self.orphaned or self.missing_evidence)

    def summary(self) -> str:
        if self.complete:
            return "the discipline-loop record is complete"
        parts = []
        if self.uncovered:
            parts.append(f"{len(self.uncovered)} unexplained: {', '.join(self.uncovered)}")
        if self.orphaned:
            parts.append(f"{len(self.orphaned)} explaining nothing: {', '.join(self.orphaned)}")
        if self.missing_evidence:
            parts.append(f"{len(self.missing_evidence)} citing missing evidence: "
                         f"{', '.join(self.missing_evidence)}")
        return "; ".join(parts)


def audit_loop_notes(
    notes: Sequence[LoopNote],
    reports: Iterable[Mapping[str, Any]],
    *,
    base_dir: Path | str,
) -> LoopNoteAudit:
    """Audit the committed notes against what the artifacts say needs explaining.

    Three ways the record can be wrong, all of them silent without this: something that needs a
    note has none; a note explains a subject that no longer exists (a renamed failure mode, an
    entry that left the set); a note cites evidence that is not in the repository.
    """
    required = required_subjects(reports)
    covered: dict[NoteKind, set[str]] = {kind: set() for kind in NoteKind}
    for note in notes:
        covered[note.kind].update(note.subjects)

    uncovered = sorted(
        f"{kind.value}:{subject}"
        for kind, subjects in required.items()
        for subject in subjects - covered[kind]
    )
    orphaned = sorted(
        f"{kind.value}:{subject}"
        for kind, subjects in covered.items()
        for subject in subjects - required[kind]
    )
    root = Path(base_dir)
    missing_evidence = sorted(
        f"{note.id}:{path}"
        for note in notes
        for path in note.evidence
        if not (root / path).exists()
    )
    return LoopNoteAudit(
        uncovered=tuple(uncovered),
        orphaned=tuple(orphaned),
        missing_evidence=tuple(missing_evidence),
    )


__all__ = [
    "ESTIMATION_LEVEL",
    "EXACT_MATCH",
    "LoopNote",
    "LoopNoteAudit",
    "LoopStage",
    "NoteBasis",
    "NoteKind",
    "Resolution",
    "audit_loop_notes",
    "disagreement_subjects",
    "load_loop_notes",
    "required_subjects",
    "tolerance_default_subjects",
]
