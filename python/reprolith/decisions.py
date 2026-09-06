"""Expert decisions that survive the process that recorded them.

:class:`~reprolith.verification.VerificationQueue` has always been able to hold a decision — a
confirmation, a correction, a rejection, with its author and rationale — and
:func:`~reprolith.reverify_dependents` has always been able to act on one. Neither could ever be
reached from outside a single Python process. The queue is *derived* from the standing
certificates on every call and stored nowhere, which is what keeps it from drifting; the
consequence nobody had drawn is that a decision made against it evaporated with the interpreter.
So `verification-queue` printed the same items as pending for as long as the certificates stood,
and the repository's own contributing guide had to say that an expert's answer "becomes the
record" while nothing in the repository could hold one.

This module is the missing half: a committed file of decisions
(``datasets/verification_decisions.json``), read by the same
:func:`~reprolith.verification.queue_report` every surface answers from, so an answer given once
is an answer every surface shows.

Three things it deliberately refuses to do, because each would publish a stronger claim than the
record supports:

``it does not lift a certificate's qualification``
    A confirmed value is still a value whose certificates were computed while it was unreviewed,
    and those certificates on disk still carry the assumption as load-bearing. Re-issuing them is
    :func:`~reprolith.reverify_dependents`, which is a deliberate act with a new pin and a
    supersession link. A decided item therefore keeps saying that its dependents have not been
    re-issued — and the proof is mechanical rather than asserted: were they re-issued, the
    assumption behind the item would no longer be load-bearing and the item would not be derived
    at all, so an item that is still here is an item whose dependents still stand as they were.

``it does not resolve disagreement``
    Two experts who answer one question differently are two records, both shown, with the item
    marked disputed. The spec requires competing judgments be retained rather than silently
    resolved, and picking the newest would resolve them silently.

``it does not trust an id``
    A derived item id *is* the digest of its question, so a decision recorded against one cannot
    come to sit under a different question. An item the certificates *name* — the metformin
    deposits name ``verify:time-unit-of-the-Zake2021-deposits`` — has an id an author chose, and
    the question under it can be reworded, re-based, or given different alternatives with the id
    unchanged. A decision would then be attributed to an expert for a question they never read.
    So every record carries the fingerprint of the question as it was answered, and a record whose
    fingerprint no longer matches is reported as **stale** and its item goes back to pending.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The decision kinds, matching ``VerificationDecision``: the queue and the file cannot drift
#: apart on what an expert is allowed to say.
KINDS = ("confirm", "correct", "reject")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class RecordedDecision:
    """One expert decision as the repository stores it.

    ``question_fingerprint`` is :func:`~reprolith.verification.question_fingerprint` of the
    assumption at the time of the decision — what makes the record verifiable rather than merely
    filed. ``source`` is where the decision was made (the issue, the pull request, a publication):
    an attributed record whose origin cannot be looked up is a name in a file.
    """

    item_id: str
    question_fingerprint: str
    kind: str
    expert: str
    rationale: str
    decided_on: str
    source: str
    corrected_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "question_fingerprint": self.question_fingerprint,
            "kind": self.kind,
            "expert": self.expert,
            "rationale": self.rationale,
            "decided_on": self.decided_on,
            "source": self.source,
            "corrected_value": self.corrected_value,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> RecordedDecision:
        """Parse one record, refusing anything that would file an unusable decision.

        Every check here is one that, left out, produces a record that reads as an expert's
        judgment while carrying none: a kind nothing acts on, a correction with nothing to correct
        to, an anonymous decision, an unreasoned one, a date no ordering can use.
        """
        if not isinstance(raw, dict):
            raise ValueError(f"a decision must be an object, not {type(raw).__name__}")
        missing = [
            field
            for field in (
                "item_id",
                "question_fingerprint",
                "kind",
                "expert",
                "rationale",
                "decided_on",
                "source",
            )
            if not str(raw.get(field, "")).strip()
        ]
        if missing:
            raise ValueError(
                f"decision for item {raw.get('item_id', '(unnamed)')!r} is missing "
                f"{', '.join(missing)}; every field is what makes the record actionable by "
                "someone who was not there"
            )
        kind = str(raw["kind"])
        if kind not in KINDS:
            raise ValueError(f"decision kind must be one of {', '.join(KINDS)}, not {kind!r}")
        corrected = raw.get("corrected_value")
        if kind == "correct" and not str(corrected or "").strip():
            raise ValueError(
                f"the correction of {raw['item_id']!r} supplies no corrected value; a correction "
                "that does not say what the value should be cannot be acted on"
            )
        if kind != "correct" and str(corrected or "").strip():
            raise ValueError(
                f"the {kind} of {raw['item_id']!r} carries a corrected value; only a correction "
                "replaces the estimate, so this record would be read as changing nothing while "
                "appearing to change something"
            )
        decided_on = str(raw["decided_on"])
        if not _DATE.match(decided_on):
            raise ValueError(
                f"decision for {raw['item_id']!r} is dated {decided_on!r}; use ISO YYYY-MM-DD so "
                "decisions on one item order the way they were made"
            )
        return cls(
            item_id=str(raw["item_id"]),
            question_fingerprint=str(raw["question_fingerprint"]),
            kind=kind,
            expert=str(raw["expert"]),
            rationale=str(raw["rationale"]),
            decided_on=decided_on,
            source=str(raw["source"]),
            corrected_value=str(corrected) if kind == "correct" else None,
        )


def load_decisions(path: Path | str) -> tuple[RecordedDecision, ...]:
    """Read the committed decisions file.

    Raises rather than returning an empty tuple when the file is absent: "no expert has decided
    anything" and "this path is wrong" are different facts, and the surfaces read this on the way
    to a page that says which. Records are returned in file order — a file that lists two
    decisions on one item is preserving a disagreement, and sorting them would hide which came
    first.
    """
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(
            f"no verification decisions file at {file}. It is committed data, so this is a wrong "
            "path or a checkout without datasets — not an empty queue"
        )
    raw = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("decisions"), list):
        raise ValueError(
            f"{file} must be an object with a 'decisions' list; an empty repository records "
            '{"decisions": []}'
        )
    return tuple(RecordedDecision.from_dict(entry) for entry in raw["decisions"])


def decisions_document(decisions: Sequence[RecordedDecision]) -> dict[str, Any]:
    """The file's own shape, so a writer and the reader cannot drift apart on it."""
    return {"decisions": [decision.to_dict() for decision in decisions]}


__all__ = [
    "KINDS",
    "RecordedDecision",
    "decisions_document",
    "load_decisions",
]
