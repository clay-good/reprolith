"""The verification queue: turning load-bearing uncertainty into an invitation to collaborate.

When the engine is not confident about a value that matters — a shaky extraction, a load-bearing
assumption, a non-default tolerance, a near-margin verdict — it records its best estimate and
queues that item for a human expert to confirm, correct, or reject (spec: ``verification-queue``).
The estimate still flows through the engine, but its unverified status travels downstream, and an
expert can act on a queue item knowing the science but not Reprolith's internals.

This module is the queue itself: self-contained items, impact-ordered so the most consequential
validations come first, and expert decisions recorded with their author and rationale. Competing
judgments are preserved, never silently resolved to one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a runtime import cycle; only needed for type hints
    from .model import Certificate, EnginePin
    from .supersession import CertificateLedger


@dataclass(frozen=True)
class VerificationItem:
    """One low-confidence, load-bearing decision awaiting expert judgment.

    Self-contained: the ``question``, the ``best_estimate`` and its ``basis``, the
    ``alternatives`` considered, and ``depends_on`` (the claims or certificates that hinge on it)
    are everything an outside expert needs to decide. ``margin`` is how close the dependent
    verdict sits to its tolerance (0.0 = right at the margin); smaller is more urgent.
    """

    id: str
    question: str
    best_estimate: str
    basis: str
    depends_on: tuple[str, ...]
    alternatives: tuple[str, ...] = ()
    margin: float | None = None

    def impact(self) -> int:
        """How much depends on this value — the count of dependent claims or certificates."""
        return len(self.depends_on)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "best_estimate": self.best_estimate,
            "basis": self.basis,
            "depends_on": list(self.depends_on),
            "alternatives": list(self.alternatives),
            "margin": self.margin,
            "impact": self.impact(),
        }


@dataclass(frozen=True)
class VerificationDecision:
    """An expert's decision on a queued item: confirm, correct, or reject, with its author."""

    kind: str  # "confirm" | "correct" | "reject"
    expert: str
    rationale: str
    corrected_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "expert": self.expert,
            "rationale": self.rationale,
            "corrected_value": self.corrected_value,
        }


class VerificationQueue:
    """A queue of load-bearing uncertainties, impact-ordered, with expert decisions recorded.

    An item is *pending* until it has a decision. Deciding never discards the estimate or a prior
    decision: competing judgments accumulate so disagreement is preserved, not silently resolved.
    """

    def __init__(self) -> None:
        self._items: dict[str, VerificationItem] = {}
        self._decisions: dict[str, list[VerificationDecision]] = {}

    def __len__(self) -> int:
        return len(self._items)

    def add(self, item: VerificationItem) -> None:
        """Queue a load-bearing uncertainty for review.

        Re-adding an id that already carries a decision is refused. Silently replacing it would
        leave an expert's decision attached to a question they never saw, and since a decided item
        is no longer pending, the changed question would never come back for review. Queue the new
        question under its own id.
        """
        if item.id in self._decisions and self._items.get(item.id) != item:
            raise ValueError(
                f"item {item.id!r} already carries an expert decision; queue a changed question "
                "under a new id rather than replacing the one that was decided"
            )
        self._items[item.id] = item

    def get(self, item_id: str) -> VerificationItem | None:
        return self._items.get(item_id)

    def decisions_for(self, item_id: str) -> tuple[VerificationDecision, ...]:
        """Every decision recorded for an item, in order — competing judgments included."""
        return tuple(self._decisions.get(item_id, ()))

    def decide(self, item_id: str, decision: VerificationDecision) -> None:
        """Record an expert decision; the estimate and any prior decisions remain retrievable."""
        if item_id not in self._items:
            raise KeyError(f"no queued item {item_id!r}")
        if decision.kind not in ("confirm", "correct", "reject"):
            raise ValueError("decision kind must be confirm, correct, or reject")
        if decision.kind == "correct" and decision.corrected_value is None:
            raise ValueError("a correction must supply the corrected value")
        if not decision.rationale.strip():
            raise ValueError("an expert decision must record its rationale")
        self._decisions.setdefault(item_id, []).append(decision)

    def pending(self) -> list[VerificationItem]:
        """Undecided items, most consequential first (impact, then verdict-margin closeness).

        Ranking is explainable: more dependents rank higher, and among equal dependents an item
        whose verdict sits closer to its tolerance margin ranks higher.
        """
        undecided = [item for item in self._items.values() if item.id not in self._decisions]
        undecided.sort(key=lambda item: (-item.impact(), item.margin if item.margin is not None else 1e9))
        return undecided


def reverify_dependents(
    item: VerificationItem,
    ledger: CertificateLedger,
    *,
    queue: VerificationQueue,
    recertify: Callable[[Certificate], Certificate],
) -> list[Certificate]:
    """Re-verify the certificates that depend on a decided queue item (spec: verification-queue).

    ``queue`` is the queue holding the decision, and the item must actually have one: the whole
    point of the qualification is that no expert has ruled yet, so re-issuing its dependents
    while the item is still pending is how an unverified value becomes a clean green certificate
    with nobody having confirmed anything. A rejected item is refused for the same reason — a
    rejection is not a confirmation.

    For each dependent certificate (by digest in ``item.depends_on``) still in the ledger,
    ``recertify`` produces its replacement — the caller decides how, based on the expert's
    decision: re-run with a corrected value, or re-issue with the unverified qualification lifted
    once confirmed. The replacement should link to the one it supersedes (``supersedes``); it is
    issued into the ledger, and the superseded certificate remains retrievable. Returns the
    replacements, so nothing is settled by a stale certificate after the value beneath it changed.
    """
    decisions = queue.decisions_for(item.id)
    if not decisions:
        raise ValueError(
            f"verification item {item.id!r} has no expert decision yet; its dependents cannot be "
            "re-issued while the value they rest on is still awaiting review"
        )
    if decisions[-1].kind == "reject":
        raise ValueError(
            f"verification item {item.id!r} was rejected; a rejection is not a confirmation, so "
            "the value beneath its dependents has to be corrected rather than re-issued"
        )
    replacements: list[Certificate] = []
    for digest in item.depends_on:
        old = ledger.get(digest)
        if old is None:
            continue
        new = recertify(old)
        ledger.issue(new)
        replacements.append(new)
    return replacements


def certificates_needing_review(ledger: CertificateLedger, current_pin: EnginePin) -> list[Certificate]:
    """Certificates pinned to a different engine than ``current_pin`` — flagged for re-review.

    When the pinned engine changes, a value verified under the old pin is no longer settled: its
    numbers could shift, so its certificate is re-opened for re-validation rather than trusted
    because it was once confirmed (spec: verification-queue — "Freshness and re-opening"). Newest
    certificate per paper wins in a real re-run; this returns every stale certificate to flag.
    """
    return [cert for _, cert in ledger.items() if cert.engine_pin != current_pin]


__all__ = [
    "VerificationDecision",
    "VerificationItem",
    "VerificationQueue",
    "certificates_needing_review",
    "reverify_dependents",
]
