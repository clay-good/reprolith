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

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .canonical import content_hash

if TYPE_CHECKING:  # avoid a runtime import cycle; only needed for type hints
    from .model import Assumption, Certificate, EnginePin
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


def _item_id(assumption: Assumption) -> str:
    """The queue id for an assumption: its own if it names one, otherwise derived from the question.

    A certificate may name the item its assumption belongs to — the metformin deposits do, all four
    pointing at ``verify:time-unit-of-the-Zake2021-deposits`` — and that name is honored, so an id
    an author chose is not replaced by a hash. Most load-bearing assumptions name nothing, and
    those get ``verify:`` plus twelve hex of the digest of the four fields that *are* the question:
    what was assumed, what was chosen, on what basis, and against what alternatives.

    Keying on the question and **not** on the assumption's own id is the whole point. The three
    certified spatial profiles each carry a boundary-condition assumption whose id names its own
    claim — ``spatial-boundary-diffusion_D1-profile``, ``_D2-``, ``_Dhalf-`` — under four fields
    that are character-for-character identical, because it is one limitation of one solver. Keyed
    by assumption id those are three items an expert answers three times; keyed by the question
    they are one item with three dependents, which is both the true impact and the true amount of
    expert time it costs. The converse holds too: ``dose-salt-form`` appears on two certificates
    with different doses in it, and those are two questions that must not merge into one that
    misstates both. The id is a function of content alone, so it is stable across runs and
    recomputable from a certificate in hand rather than stored anywhere.
    """
    if assumption.verification_item:
        return assumption.verification_item
    body = content_hash(
        {
            "description": assumption.description,
            "chosen": assumption.chosen,
            "basis": assumption.basis,
            "alternatives": list(assumption.alternatives),
        }
    )
    return f"verify:{body[:12]}"


def _question(assumption: Assumption) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        assumption.description,
        assumption.chosen,
        assumption.basis,
        tuple(assumption.alternatives),
    )


def queue_from_certificates(
    pairs: Sequence[tuple[str, Certificate]],
) -> tuple[VerificationQueue, dict[str, tuple[str, ...]], frozenset[str]]:
    """Open a queue item for every load-bearing assumption on the given certificates.

    This is the escalation step the ``autonomous-build-loop`` spec requires and nothing performed:
    the queue's shapes existed, ``Assumption.verification_item`` existed, and the four metformin
    certificates even cited an item id — but no code built the item behind it, so a reader who
    followed the citation found nothing. Every load-bearing assumption is by definition a value
    the loop committed that plausibly changes an outcome, so every one of them is queued, not only
    the ones that were remembered to be named.

    The queue is *derived*, never stored. An item's ``depends_on`` is the digests of the
    certificates carrying it, merged across them and sorted, so ``impact`` is the real number of
    published results resting on the value, and ``reverify_dependents`` can act on the item
    directly. Deriving it means the queue cannot drift from the certificates the way a second
    file would, and re-deriving it after a certificate is superseded drops that certificate's
    dependency without anything having to remember to.

    Escalation changes no verdict: a load-bearing assumption already withholds a clean pass
    through ``derive_overall``, so opening its item adds a reader's route to the question and
    nothing else. That is deliberate — an escalation that moved a verdict would be a reason not
    to escalate.

    An assumption is queued when it is load-bearing *or* when the certificate names a
    verification item for it — the same pair ``derive_overall`` consults when it withholds a clean
    pass, so nothing that costs a certificate its clean pass is missing from the list of what the
    certificate is resting on.

    ``pairs`` is (digest, certificate); pass the certificates whose results still stand, since a
    superseded certificate's dependency is not a live one. Raises ``ValueError`` when one item id
    carries two different questions, which is a data defect that would publish one of them under
    the other's name.
    """
    questions: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    sources: dict[str, str] = {}
    assumptions: dict[str, Assumption] = {}
    dependents: dict[str, set[str]] = {}
    assumption_ids: dict[str, set[str]] = {}
    answerable: set[str] = set()
    for digest, cert in pairs:
        for assumption in cert.assumptions:
            # `load_bearing` is the usual reason, and an explicit `verification_item` is the other
            # one: `derive_overall` withholds a clean pass for either, and the gap report names
            # either. This loop tested only the first, so an assumption whose certificate says in
            # so many words that it is queued for review was the one thing the queue left out.
            if not assumption.load_bearing and not assumption.verification_item:
                continue
            item_id = _item_id(assumption)
            question = _question(assumption)
            if item_id in questions and questions[item_id] != question:
                raise ValueError(
                    f"verification item {item_id!r} is named by two different questions — "
                    f"certificate {sources[item_id]} and certificate {digest} disagree about what "
                    "it asks; one of them would be queued under the other's name, so give the "
                    "changed question its own id"
                )
            questions[item_id] = question
            sources.setdefault(item_id, digest)
            assumptions.setdefault(item_id, assumption)
            dependents.setdefault(item_id, set()).add(digest)
            assumption_ids.setdefault(item_id, set()).add(assumption.id)
            if assumption.author_can_close:
                answerable.add(item_id)

    queue = VerificationQueue()
    for item_id in sorted(dependents):
        assumption = assumptions[item_id]
        queue.add(
            VerificationItem(
                id=item_id,
                question=assumption.description,
                best_estimate=assumption.chosen,
                basis=assumption.basis,
                depends_on=tuple(sorted(dependents[item_id])),
                alternatives=tuple(assumption.alternatives),
            )
        )
    return (
        queue,
        {k: tuple(sorted(v)) for k, v in assumption_ids.items()},
        frozenset(answerable),
    )


def queue_report(pairs: Sequence[tuple[str, Certificate]]) -> dict[str, Any]:
    """The queue as a read, split by whether anybody can actually answer the item.

    The first version of this report put every load-bearing assumption under one heading and
    ranked them together, and on the committed repository that read badly: six of the eight are
    Reprolith's *own* limits rather than anything a paper left out. The spatial solver implements
    one boundary condition; the stochastic class judges an ensemble it drew itself. No expert
    confirming anything changes either, so listing them as awaiting expert review invited a reader
    to think five of the seven questions were waiting on a person when they are waiting on this
    engine. ``Assumption.author_can_close`` already carried the distinction — it was written for
    the author-facing fix list, which had the same problem first — and it carries it here.

    So ``pending`` is what an expert can decide, and ``engine_limits`` is what only this engine's
    development can close. An item merged from several assumptions counts as answerable if *any*
    of them is: one closable dependent makes the question a live one.

    ``margin`` is ``None`` on every item and stays that way. The queue ranks equal-impact items by
    how close the dependent verdict sits to its tolerance, and the only numbers on a certificate
    that could supply it — ``discrepancy`` and ``tolerance`` — are free text a judge wrote for a
    person to read (``"relative error 0.0221"``, and a label). Parsing them back into a margin
    would be a guess dressed as a measurement, and this is the surface where a fabricated number
    would be least visible. So the ranking is by impact, and the field says so rather than
    carrying a number nobody measured.

    ``linked`` says whether the certificates naming this item did so themselves or whether the id
    was derived from the question — the difference between a citation a reader can search for and
    one this function computed. ``depends_on_papers`` is the same dependents as ``depends_on``,
    named rather than digested, so an expert can tell whether they know the paper before deciding
    whether they can answer — a 64-character hash is the right identifier for
    :func:`reverify_dependents` and the wrong one for a person.
    """
    queue, assumption_ids, answerable = queue_from_certificates(pairs)
    # A dependent is a 64-character digest, which is the right identifier for
    # `reverify_dependents` and the wrong one for a person deciding whether they know enough
    # to answer. The papers behind those digests are what an expert recognizes, and the whole
    # point of an item is that an outside reader can act on it without knowing Reprolith.
    papers = {
        digest: {"title": cert.paper.title, "doi": cert.paper.doi}
        for digest, cert in pairs
    }
    linked = {
        assumption.verification_item
        for _, cert in pairs
        for assumption in cert.assumptions
        if assumption.verification_item
    }
    pending: list[dict[str, Any]] = []
    engine_limits: list[dict[str, Any]] = []
    for item in queue.pending():
        view = item.to_dict()
        view["linked"] = item.id in linked
        # A derived id appears in no certificate, so it is not what a reader greps for. The
        # assumption ids are, and there is more than one wherever a question spans claims.
        view["assumption_ids"] = list(assumption_ids[item.id])
        seen: list[dict[str, Any]] = []
        for digest in item.depends_on:
            paper = papers.get(digest)
            # De-duplicated on the whole identity, because a re-issued certificate for the same
            # deposit is one paper to the reader. It does not collapse by DOI: the four metformin
            # certificates share one DOI and name four different model deposits, and an expert
            # deciding the time unit needs to see that it is four deposits and not one.
            if paper is not None and paper not in seen:
                seen.append(paper)
        view["depends_on_papers"] = seen
        (pending if item.id in answerable else engine_limits).append(view)
    return {
        "pending": pending,
        "pending_count": len(pending),
        # How much of the corpus each half actually reaches. Reported because the count alone was
        # being read against the size of the repository: "3 values that 33 standing certificates
        # rest on" is how the registry page put it, and only 4 of those 33 carry one. A sentence
        # that makes an unreviewed value sound like a property of the whole published set is the
        # same overstatement as ranking the engine's own limits as questions for an expert.
        "certificates_affected": len({d for i in pending for d in i["depends_on"]}),
        "engine_limits": engine_limits,
        "engine_limits_count": len(engine_limits),
        "engine_limits_certificates_affected": len(
            {d for i in engine_limits for d in i["depends_on"]}
        ),
        "engine_limits_note": (
            "they rest on a choice this engine had to make rather than on anything the paper "
            "left unsaid — the spatial solver's single boundary condition, the ensemble the "
            "stochastic class drew — so no expert decision closes one. They withhold a clean pass "
            "exactly as the others do; what they wait on is this engine, not a person"
        ),
        "ranked_by": (
            "impact — the number of standing certificates resting on the value. Margin is not "
            "ranked on: a certificate states its discrepancy and tolerance as prose, and a "
            "number parsed back out of prose is a guess, not a measurement"
        ),
        "decisions": [],
        "decisions_note": (
            "no expert decision is stored in this repository, so every item here is pending. A "
            "decision is recorded against a live queue (VerificationQueue.decide) and acted on "
            "through reverify_dependents; nothing on disk carries one yet"
        ),
    }


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
    "queue_from_certificates",
    "queue_report",
    "reverify_dependents",
]
