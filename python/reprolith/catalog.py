"""The model catalog: entries, their lifecycle, and de-duplication.

This is the bootstrap catalog slice (tasks 1.1–1.3): a candidate paper becomes exactly
one :class:`CatalogEntry` that moves through an explicit lifecycle with every transition
recorded (never inferred), carries a model-class tag, and may hold an independent
ground-truth label. The label is structurally withheld from the verdict path via
:meth:`CatalogEntry.blind`, so self-validation stays honest (spec: ``model-catalog`` —
"Ground-truth labelling for self-validation"; design D4). The :class:`Catalog` container
resolves the same paper arriving under different identifiers to a single entry.

Like the certificate shapes, everything here serializes to plain JSON-able dicts and
splits deterministic content from caller-supplied, non-deterministic transition metadata
(a timestamp, an actor).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import LifecycleState, ModelClass, OverallVerdict


class IllegalTransition(Exception):
    """Raised when a lifecycle transition is not permitted from the current state."""


# The permitted transitions. A move not listed here is an ``IllegalTransition`` — the
# lifecycle is a state machine, not free assignment. ``BLOCKED``/``QUARANTINED`` are
# reachable from every stage that can discover a missing input or bad data, and can be
# released back into the queue; ``CERTIFIED``/``FAILED`` re-open only for re-verification
# (a new engine-version pin).
_ALLOWED: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.QUEUED: frozenset(
        {LifecycleState.INGESTING, LifecycleState.QUARANTINED}
    ),
    LifecycleState.INGESTING: frozenset(
        {LifecycleState.INGESTED, LifecycleState.BLOCKED, LifecycleState.QUARANTINED}
    ),
    LifecycleState.INGESTED: frozenset(
        {LifecycleState.RECONSTRUCTING, LifecycleState.BLOCKED, LifecycleState.QUARANTINED}
    ),
    LifecycleState.RECONSTRUCTING: frozenset(
        {LifecycleState.RECONSTRUCTED, LifecycleState.BLOCKED, LifecycleState.QUARANTINED}
    ),
    LifecycleState.RECONSTRUCTED: frozenset(
        {LifecycleState.VERIFYING, LifecycleState.BLOCKED, LifecycleState.QUARANTINED}
    ),
    LifecycleState.VERIFYING: frozenset(
        {
            LifecycleState.CERTIFIED,
            LifecycleState.FAILED,
            LifecycleState.BLOCKED,
            LifecycleState.QUARANTINED,
        }
    ),
    # Terminal for a given pin; a new pin re-opens for re-verification.
    LifecycleState.CERTIFIED: frozenset(
        {LifecycleState.RECONSTRUCTING, LifecycleState.VERIFYING}
    ),
    LifecycleState.FAILED: frozenset(
        {LifecycleState.RECONSTRUCTING, LifecycleState.VERIFYING, LifecycleState.QUEUED}
    ),
    # A missing input, once supplied, re-opens the entry.
    LifecycleState.BLOCKED: frozenset(
        {LifecycleState.QUEUED, LifecycleState.INGESTING, LifecycleState.RECONSTRUCTING}
    ),
    # Released back to the queue after review.
    LifecycleState.QUARANTINED: frozenset({LifecycleState.QUEUED}),
}


def _normalize(value: str) -> str:
    """Collapse whitespace and case so equivalent identifiers match."""
    return " ".join(value.strip().lower().split())


@dataclass(frozen=True)
class Identifiers:
    """The identifiers a paper may be known by.

    De-duplication resolves any overlap on ``doi``, ``pubmed_id``, ``accession``, or a
    normalized ``title`` to a single entry. All known identifiers are retained on merge.
    """

    title: str
    doi: str | None = None
    pubmed_id: str | None = None
    accession: str | None = None

    def keys(self) -> frozenset[tuple[str, str]]:
        """The ``(kind, normalized-value)`` pairs this paper can be matched on."""
        pairs: set[tuple[str, str]] = {("title", _normalize(self.title))}
        if self.doi:
            pairs.add(("doi", _normalize(self.doi)))
        if self.pubmed_id:
            pairs.add(("pubmed_id", _normalize(self.pubmed_id)))
        if self.accession:
            pairs.add(("accession", _normalize(self.accession)))
        return frozenset(pairs)

    def merged_with(self, other: Identifiers) -> Identifiers:
        """Union of known identifiers, keeping this entry's existing values on conflict."""
        return Identifiers(
            title=self.title,
            doi=self.doi or other.doi,
            pubmed_id=self.pubmed_id or other.pubmed_id,
            accession=self.accession or other.accession,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "doi": self.doi,
            "pubmed_id": self.pubmed_id,
            "accession": self.accession,
        }

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> Identifiers:
        return cls(
            title=record["title"],
            doi=record.get("doi"),
            pubmed_id=record.get("pubmed_id"),
            accession=record.get("accession"),
        )


@dataclass(frozen=True)
class GroundTruth:
    """An independently established reproducibility label for an entry.

    Held on the entry but structurally excluded from the blind view handed to the
    verdict path (see :meth:`CatalogEntry.blind`); its only legitimate use is
    post-verdict agreement scoring.
    """

    expected: OverallVerdict
    source: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"expected": self.expected.value, "source": self.source, "note": self.note}

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> GroundTruth:
        return cls(
            expected=OverallVerdict(record["expected"]),
            source=record["source"],
            note=record.get("note"),
        )


@dataclass(frozen=True)
class Transition:
    """One recorded lifecycle move: who, when, why — appended, never inferred."""

    from_state: LifecycleState
    to_state: LifecycleState
    at: str
    actor: str
    reason: str
    missing_inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "at": self.at,
            "actor": self.actor,
            "reason": self.reason,
            "missing_inputs": list(self.missing_inputs),
        }

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> Transition:
        return cls(
            from_state=LifecycleState(record["from_state"]),
            to_state=LifecycleState(record["to_state"]),
            at=record["at"],
            actor=record["actor"],
            reason=record["reason"],
            missing_inputs=tuple(record.get("missing_inputs", ())),
        )


@dataclass(frozen=True)
class BlindEntry:
    """The view of an entry the verdict path is allowed to see.

    It carries no ground-truth label — not a redacted one, but no field for it at all —
    so no ingestion, reconstruction, or oracle code can read the answer it is being
    measured against (design D4).
    """

    identifiers: Identifiers
    model_class: ModelClass
    state: LifecycleState
    difficulty: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifiers": self.identifiers.to_dict(),
            "model_class": self.model_class.value,
            "state": self.state.value,
            "difficulty": self.difficulty,
        }


class CatalogEntry:
    """A single candidate paper tracked through the reproduction lifecycle.

    Construct through :meth:`Catalog.add` so de-duplication and indexing are honored.
    State is never assigned directly; it advances only through :meth:`transition`, which
    validates the move and records it.
    """

    def __init__(
        self,
        identifiers: Identifiers,
        model_class: ModelClass = ModelClass.UNASSIGNED,
        *,
        difficulty: str | None = None,
        ground_truth: GroundTruth | None = None,
    ) -> None:
        self.identifiers = identifiers
        self.model_class = model_class
        self.difficulty = difficulty
        self.ground_truth = ground_truth
        self._state = LifecycleState.QUEUED
        self._history: list[Transition] = []

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def history(self) -> tuple[Transition, ...]:
        return tuple(self._history)

    def transition(
        self,
        to: LifecycleState,
        *,
        at: str,
        actor: str,
        reason: str,
        missing_inputs: tuple[str, ...] = (),
    ) -> Transition:
        """Advance to ``to``, recording the move; raise if the move is not permitted.

        ``BLOCKED`` requires a non-empty ``missing_inputs`` list (what is missing is the
        whole point of the state); every other target forbids it — a ``FAILED`` attempt
        ran to completion and has no missing input to report.
        """
        if to not in _ALLOWED[self._state]:
            raise IllegalTransition(f"{self._state.value} -> {to.value} is not permitted")
        if to is LifecycleState.BLOCKED and not missing_inputs:
            raise ValueError("a blocked transition must list the missing inputs")
        if to is not LifecycleState.BLOCKED and missing_inputs:
            raise ValueError("missing_inputs is only meaningful for a blocked transition")

        move = Transition(
            from_state=self._state,
            to_state=to,
            at=at,
            actor=actor,
            reason=reason,
            missing_inputs=tuple(missing_inputs),
        )
        self._history.append(move)
        self._state = to
        return move

    def blind(self) -> BlindEntry:
        """The label-free view safe to hand to a verdict-producing stage."""
        return BlindEntry(
            identifiers=self.identifiers,
            model_class=self.model_class,
            state=self._state,
            difficulty=self.difficulty,
        )

    def agreement(self, verdict: OverallVerdict) -> bool | None:
        """Whether a produced ``verdict`` agrees with the ground-truth label.

        ``None`` when the entry carries no label. This is the label's only legitimate
        reader, and it runs only after a verdict already exists.
        """
        if self.ground_truth is None:
            return None
        return verdict is self.ground_truth.expected

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifiers": self.identifiers.to_dict(),
            "model_class": self.model_class.value,
            "difficulty": self.difficulty,
            "state": self._state.value,
            "history": [t.to_dict() for t in self._history],
            "ground_truth": self.ground_truth.to_dict() if self.ground_truth else None,
        }

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> CatalogEntry:
        """Reconstruct an entry from its stored dict, restoring its state and history exactly.

        Loading a recorded lifecycle is not a fresh traversal, so the state and history are
        restored directly rather than replayed through :meth:`transition`.
        """
        ground_truth = record.get("ground_truth")
        entry = cls(
            Identifiers.from_dict(record["identifiers"]),
            ModelClass(record["model_class"]),
            difficulty=record.get("difficulty"),
            ground_truth=GroundTruth.from_dict(ground_truth) if ground_truth else None,
        )
        entry._state = LifecycleState(record["state"])
        entry._history = [Transition.from_dict(t) for t in record.get("history", [])]
        return entry


class Catalog:
    """A collection of entries with de-duplication across identifiers.

    Adding a candidate that shares any identifier with an existing entry merges into that
    entry (retaining all known identifiers) rather than creating a duplicate.
    """

    def __init__(self) -> None:
        self._entries: list[CatalogEntry] = []
        self._index: dict[tuple[str, str], CatalogEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[CatalogEntry, ...]:
        return tuple(self._entries)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the whole catalog — a durable, re-loadable registry (spec: model-catalog)."""
        return {"entries": [entry.to_dict() for entry in self._entries]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Catalog:
        """Reload a catalog saved with :meth:`to_dict`, restoring each entry and the index.

        The saved catalog is already de-duplicated, so entries are restored directly rather
        than re-added through :meth:`add`.
        """
        catalog = cls()
        for record in data["entries"]:
            entry = CatalogEntry.from_dict(record)
            catalog._entries.append(entry)
            catalog._reindex(entry)
        return catalog

    def add(
        self,
        identifiers: Identifiers,
        model_class: ModelClass = ModelClass.UNASSIGNED,
        *,
        difficulty: str | None = None,
        ground_truth: GroundTruth | None = None,
    ) -> CatalogEntry:
        """Add a candidate, or resolve it to the existing entry it duplicates.

        Returns the entry the candidate now belongs to. On a match, the existing entry's
        identifiers absorb any new ones; class, difficulty, and label are filled in only
        where the existing entry left them unset, so a re-seed never overwrites known data.
        """
        existing = self._match(identifiers)
        if existing is not None:
            existing.identifiers = existing.identifiers.merged_with(identifiers)
            if existing.model_class is ModelClass.UNASSIGNED:
                existing.model_class = model_class
            if existing.difficulty is None:
                existing.difficulty = difficulty
            if existing.ground_truth is None:
                existing.ground_truth = ground_truth
            self._reindex(existing)
            return existing

        entry = CatalogEntry(
            identifiers,
            model_class,
            difficulty=difficulty,
            ground_truth=ground_truth,
        )
        self._entries.append(entry)
        self._reindex(entry)
        return entry

    def find(self, identifiers: Identifiers) -> CatalogEntry | None:
        """Return the entry this paper resolves to, or ``None`` — a read-only lookup."""
        return self._match(identifiers)

    def _match(self, identifiers: Identifiers) -> CatalogEntry | None:
        for key in identifiers.keys():
            hit = self._index.get(key)
            if hit is not None:
                return hit
        return None

    def _reindex(self, entry: CatalogEntry) -> None:
        for key in entry.identifiers.keys():
            self._index[key] = entry


__all__ = [
    "BlindEntry",
    "Catalog",
    "CatalogEntry",
    "GroundTruth",
    "IllegalTransition",
    "Identifiers",
    "Transition",
]
