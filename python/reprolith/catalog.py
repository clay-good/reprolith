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

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .enums import LifecycleState, ModelClass, OverallVerdict


class IllegalTransition(Exception):
    """Raised when a lifecycle transition is not permitted from the current state."""


class AmbiguousMerge(Exception):
    """Raised when a candidate bridges two existing entries that can't be auto-merged.

    De-duplication resolves a paper arriving under different identifiers to a single entry,
    even when a later record is the first to connect two previously-separate entries. That
    merge is safe while at most one of the bridged entries carries recorded work. When both
    have lifecycle history, or they hold conflicting ground-truth labels, folding one away
    would silently discard recorded state — so the catalog refuses and asks for human
    reconciliation instead of corrupting the ledger.
    """


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


_DIFFICULTY_RANK = {"low": 0, "medium": 1, "high": 2}


def _difficulty_rank(difficulty: str | None) -> int:
    """Queue-ordering rank for a difficulty: lower is readier (surfaces earlier); unassessed is neutral.

    Normalized like every other free-text label here, so ``"Low"`` ranks as low rather than falling
    through to unassessed and losing its place in the queue.
    """
    return _DIFFICULTY_RANK.get((difficulty or "").strip().lower(), 1)


def _record_source(entry: CatalogEntry, source: str | None) -> None:
    """Add ``source`` to the entry's provenance if new (provenance survives de-duplication)."""
    if source and source not in entry.sources:
        entry.sources.append(source)


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
        """The ``(kind, normalized-value)`` pairs this paper can be matched on.

        A blank title yields no title key, so two genuinely different papers submitted with an
        empty title do not collapse onto the shared ``("title", "")`` key.
        """
        pairs: set[tuple[str, str]] = set()
        if _normalize(self.title):
            pairs.add(("title", _normalize(self.title)))
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
        self.leased_to: str | None = None
        self.lease_expires: float | None = None
        self.sources: list[str] = []

    @property
    def state(self) -> LifecycleState:
        return self._state

    def is_claimable(self, at: float) -> bool:
        """Whether this entry can be claimed as work at time ``at`` (a numeric timestamp).

        Claimable means queued and not held by a live lease — a lease that has expired (or was
        never set) frees the entry again.
        """
        return self._state is LifecycleState.QUEUED and (
            self.lease_expires is None or at >= self.lease_expires
        )

    def lease(self, requester: str, *, at: float, seconds: float) -> None:
        """Lease this entry to ``requester`` until ``at + seconds``."""
        self.leased_to = requester
        self.lease_expires = at + seconds

    def release_lease(self) -> None:
        """Release any lease, returning the entry to the claimable pool."""
        self.leased_to = None
        self.lease_expires = None

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
            "leased_to": self.leased_to,
            "lease_expires": self.lease_expires,
            "sources": list(self.sources),
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
        entry.leased_to = record.get("leased_to")
        entry.lease_expires = record.get("lease_expires")
        entry.sources = list(record.get("sources", []))
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
        than re-added through :meth:`add`. That assumption is checked on the way in: a file that
        carries the same identifier twice — what a mangled merge of ``catalog.json`` produces —
        would otherwise load as two entries sharing one index key, silently inflating every
        published backlog count and handing the same work item out twice.
        """
        catalog = cls()
        for record in data["entries"]:
            entry = CatalogEntry.from_dict(record)
            for key in entry.identifiers.keys():
                if key in catalog._index:
                    field, value = key
                    raise ValueError(
                        f"the saved catalog holds two entries for {field}={value!r}; a paper "
                        "resolves to a single entry, so this file is corrupt"
                    )
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
        source: str | None = None,
    ) -> CatalogEntry:
        """Add a candidate, or resolve it to the existing entry it duplicates.

        Returns the entry the candidate now belongs to. On a match, the existing entry's
        identifiers absorb any new ones; class, difficulty, and label are filled in only
        where the existing entry left them unset, so a re-seed never overwrites known data.
        A ``source`` is recorded as provenance and survives de-duplication: a paper seeded from
        more than one source keeps every source that contributed it (spec: catalog-seeding).

        When the candidate matches more than one existing entry — the first record to bridge two
        entries seeded separately under different identifiers — all of them collapse into one, so
        the "same paper resolves to a single entry" invariant holds even across the bridge. That
        collapse raises :class:`AmbiguousMerge` if it would discard recorded work (see
        :meth:`_absorb`). Raises ``ValueError`` if the candidate carries no usable identifier.

        An entry carrying a ground-truth label has a **frozen identity**: a candidate may resolve
        to it, but may not add identifiers it does not already carry, and nothing folds into it.
        Identifiers are an unverified assertion — anyone who can submit a paper can claim one — and
        the agreement report keys each labelled entry by the identifiers it carries. Without this,
        a submission naming a labelled accession alongside an unrelated DOI republished that
        entry's blind result under an identifier of the submitter's choosing, and a bridging
        submission could transplant the label onto a different paper entirely. Correcting a
        labelled entry's identity is a curation decision, made against the dataset it came from.
        """
        if not identifiers.keys():
            raise ValueError(
                "a catalog entry needs at least one identifier "
                "(a non-empty title, DOI, PubMed ID, or accession)"
            )
        matches = self._match_all(identifiers)
        if matches:
            # The richest match (most lifecycle history, then a label) is kept; the others fold
            # into it. On ties this is the earliest-inserted, preserving the prior single-match
            # behavior exactly.
            canonical = max(matches, key=lambda e: (len(e.history), e.ground_truth is not None))
            # Check every fold, and the frozen-identity rule, BEFORE folding any of them. These
            # refusals exist to protect recorded state; a refusal raised halfway through the loop
            # would have already destroyed the entries it folded in the iterations before it.
            losers = [other for other in matches if other is not canonical]
            for other in losers:
                self._refuse_unsafe_absorb(canonical, other)
            if canonical.ground_truth is not None:
                new_keys = set(identifiers.keys()) - set(canonical.identifiers.keys())
                if new_keys:
                    # Names neither the entry nor why its identity is fixed: the refusal itself
                    # is returned to whoever submitted, and a message saying "that accession is
                    # ground-truth-labelled, it is paper X" answers a question the submitter is
                    # not entitled to ask by guessing accessions.
                    raise AmbiguousMerge(
                        f"candidate would add {sorted(new_keys)} to an existing entry whose "
                        "identity is fixed by the dataset it came from; correcting it is a "
                        "curation decision, not a submission"
                    )
            for other in losers:
                self._absorb(canonical, other)
            canonical.identifiers = canonical.identifiers.merged_with(identifiers)
            if canonical.model_class is ModelClass.UNASSIGNED:
                canonical.model_class = model_class
            if canonical.difficulty is None:
                canonical.difficulty = difficulty
            if canonical.ground_truth is None:
                canonical.ground_truth = ground_truth
            _record_source(canonical, source)
            self._reindex(canonical)
            return canonical

        entry = CatalogEntry(
            identifiers,
            model_class,
            difficulty=difficulty,
            ground_truth=ground_truth,
        )
        _record_source(entry, source)
        self._entries.append(entry)
        self._reindex(entry)
        return entry

    def find(self, identifiers: Identifiers) -> CatalogEntry | None:
        """Return the entry this paper resolves to, or ``None`` — a read-only lookup."""
        return self._match(identifiers)

    def claimable(self, at: float, *, model_class: ModelClass | None = None) -> list[CatalogEntry]:
        """The entries claimable as work at time ``at``, in priority order.

        Ranking is explainable and stable: by readiness — a lower-difficulty entry, which ships a
        runnable model with no gaps to close, yields a certificate at lower cost, so it surfaces
        earlier (spec: catalog-seeding — "Readiness boosts tractable wins") — then insertion order.
        Filtered to ``model_class`` when given.

        Ground truth is deliberately **not** a ranking key. Ordering labelled work first told the
        agent about to reproduce a paper that this one is in the graded set, since the partition
        is recoverable from the order alone — the same blindness leak the read surfaces are
        careful to avoid. Every other surface hands out a blind view; the moment work is handed
        out is the one that matters most.
        """
        pool = [
            entry
            for entry in self._entries
            if entry.is_claimable(at) and (model_class is None or entry.model_class is model_class)
        ]
        # Stable sort: low difficulty (high readiness) first; ties keep insertion order.
        pool.sort(key=lambda entry: _difficulty_rank(entry.difficulty))
        return pool

    def backlog_health(self, at: float = 0.0) -> dict[str, Any]:
        """Report the state of the backlog so the never-runs-out guarantee is observable.

        Counts entries by lifecycle state, model class, and difficulty, and the labelled-versus-
        unlabelled mix — the signals a seeder watches to decide when to bring a new source online
        (spec: catalog-seeding — "Backlog health is reportable").

        ``claimable`` is reported alongside ``total`` because they answer different questions and
        the shipped catalog makes the difference stark: 31 entries, of which 0 can be handed to a
        requester (30 are blocked on a missing manuscript claim, 1 is certified). A "backlog" of
        31 reads as work available when there is none, so the number a seeder actually needs is
        published next to it. ``at`` is the time leases are judged against.
        """
        labelled = sum(1 for e in self._entries if e.ground_truth is not None)
        return {
            "total": len(self._entries),
            "claimable": len(self.claimable(at)),
            "by_state": dict(Counter(e.state.value for e in self._entries)),
            "by_class": dict(Counter(e.model_class.value for e in self._entries)),
            "by_difficulty": dict(Counter(e.difficulty or "unassessed" for e in self._entries)),
            "labelled": labelled,
            "unlabelled": len(self._entries) - labelled,
        }

    def priority_signals(self, entry: CatalogEntry) -> dict[str, Any]:
        """The signals that place an entry in the queue — so its rank is never a black box.

        Ranking is by readiness (lower difficulty first, which :meth:`claimable` acts on), then
        submission order (spec: model-catalog / catalog-seeding — "Prioritization is
        explainable"). Whether the entry carries a ground-truth label is **not** among the
        signals: it does not affect rank, and telling a claimant that the paper it is about to
        reproduce is one it will be graded on is exactly what blind self-validation must not do.
        """
        return {
            "difficulty": entry.difficulty,
            "model_class": entry.model_class.value,
            "ranking": "readiness (lower difficulty) first, then submission order",
        }

    def claim_next(
        self,
        requester: str,
        *,
        at: float,
        seconds: float,
        model_class: ModelClass | None = None,
    ) -> CatalogEntry | None:
        """Lease the highest-priority claimable entry to ``requester``, or ``None`` if none.

        The lease holds until ``at + seconds``; requesters sharing this catalog object do not
        collide, because a claimed entry stops being claimable until its lease expires (spec:
        model-catalog — "Never-empty prioritized queue").

        The lease lives in memory, so that guarantee is **per process**. Two agents running their
        own MCP servers over the same ``catalog.json`` each load it once at startup and rewrite the
        whole file on every mutation: both can be handed the same entry, and the later write wins
        over the earlier one's lease and history. Serializing agents across processes needs a lock
        around a re-read of the file, which this catalog does not attempt — run one server per
        catalog, or coordinate outside it.
        """
        pool = self.claimable(at, model_class=model_class)
        if not pool:
            return None
        entry = pool[0]
        entry.lease(requester, at=at, seconds=seconds)
        return entry

    def _match(self, identifiers: Identifiers) -> CatalogEntry | None:
        for key in identifiers.keys():
            hit = self._index.get(key)
            if hit is not None:
                return hit
        return None

    def _match_all(self, identifiers: Identifiers) -> list[CatalogEntry]:
        """Every distinct existing entry the candidate matches, in insertion order.

        Usually one, but a record carrying identifiers from two separately-seeded entries
        matches both — the case ``_match`` (first hit only) silently dropped.
        """
        seen: list[CatalogEntry] = []
        for key in identifiers.keys():
            hit = self._index.get(key)
            if hit is not None and hit not in seen:
                seen.append(hit)
        seen.sort(key=self._entries.index)  # deterministic: frozenset key order is not stable
        return seen

    def _refuse_unsafe_absorb(self, winner: CatalogEntry, loser: CatalogEntry) -> None:
        """Raise :class:`AmbiguousMerge` if folding ``loser`` into ``winner`` would lose state.

        Separate from :meth:`_absorb` so a multi-way merge can be validated in full before any
        of it is applied.
        """
        if winner.ground_truth is not None:
            raise AmbiguousMerge(
                f"candidate bridges {loser.identifiers.title!r} into the ground-truth-labelled "
                f"entry {winner.identifiers.title!r}; folding an unlabelled paper into a labelled "
                "one would transplant the label, so reconcile by hand"
            )
        if loser.history:
            raise AmbiguousMerge(
                f"candidate bridges a worked entry ({loser.identifiers.title!r}) into "
                f"{winner.identifiers.title!r}; reconcile by hand rather than discarding its history"
            )
        if (
            loser.ground_truth is not None
            and winner.ground_truth is not None
            and loser.ground_truth.expected is not winner.ground_truth.expected
        ):
            raise AmbiguousMerge(
                f"bridged entries carry conflicting ground-truth labels "
                f"({winner.ground_truth.expected.value} vs {loser.ground_truth.expected.value})"
            )
        if loser.ground_truth is not None and winner.ground_truth is None:
            # The transplant the frozen-identity rule above blocks in the other direction: the
            # winner is chosen by how much history it carries, so an unlabelled entry with more
            # history absorbs the labelled one and inherits its label — scoring an unrelated
            # paper against a dataset's ground truth.
            raise AmbiguousMerge(
                f"candidate bridges the ground-truth-labelled entry "
                f"{loser.identifiers.title!r} into the unlabelled {winner.identifiers.title!r}; "
                "folding it would move the label onto another paper, so reconcile by hand"
            )

    def _absorb(self, winner: CatalogEntry, loser: CatalogEntry) -> None:
        """Fold ``loser`` into ``winner`` — they turned out to be one paper.

        The loser's identifiers, sources, and any fields the winner left unset move over, and
        the loser is removed — including its own index keys, so nothing points at a dropped
        entry. Call :meth:`_refuse_unsafe_absorb` first: this method does not re-check.
        """
        winner.identifiers = winner.identifiers.merged_with(loser.identifiers)
        if winner.model_class is ModelClass.UNASSIGNED:
            winner.model_class = loser.model_class
        if winner.difficulty is None:
            winner.difficulty = loser.difficulty
        if winner.ground_truth is None:
            winner.ground_truth = loser.ground_truth
        for src in loser.sources:
            _record_source(winner, src)
        for key in loser.identifiers.keys():
            if self._index.get(key) is loser:
                del self._index[key]
        self._entries.remove(loser)

    def _reindex(self, entry: CatalogEntry) -> None:
        for key in entry.identifiers.keys():
            self._index[key] = entry


__all__ = [
    "AmbiguousMerge",
    "BlindEntry",
    "Catalog",
    "CatalogEntry",
    "GroundTruth",
    "IllegalTransition",
    "Identifiers",
    "Transition",
]
