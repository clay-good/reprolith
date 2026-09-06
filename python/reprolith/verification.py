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

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .canonical import content_hash
from .decisions import RecordedDecision

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
    return f"verify:{question_fingerprint(assumption)[:12]}"


def question_fingerprint(assumption: Assumption) -> str:
    """The digest of the four fields that *are* the question an expert answers.

    A derived item id is the first twelve hex of this, so for those the id already carries the
    question and nothing can slip underneath it. An item a certificate *names* has an author's id,
    and its wording, basis and alternatives can all change with the id unchanged — which is
    exactly the case where a stored decision would come to sit under a question its expert never
    read. :mod:`reprolith.decisions` records this with every decision so that drift is detected
    rather than published.
    """
    return content_hash(
        {
            "description": assumption.description,
            "chosen": assumption.chosen,
            "basis": assumption.basis,
            "alternatives": list(assumption.alternatives),
        }
    )


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


def _item_fingerprints(pairs: Sequence[tuple[str, Certificate]]) -> dict[str, str]:
    """Each queued item's current question fingerprint, keyed by item id.

    ``queue_from_certificates`` already refuses a repository where one id carries two different
    questions, so the first assumption reaching an id settles it.
    """
    fingerprints: dict[str, str] = {}
    for _, cert in pairs:
        for assumption in cert.assumptions:
            if not assumption.load_bearing and not assumption.verification_item:
                continue
            fingerprints.setdefault(_item_id(assumption), question_fingerprint(assumption))
    return fingerprints


def _join_decisions(
    fingerprints: dict[str, str],
    decisions: Sequence[RecordedDecision],
) -> tuple[dict[str, list[RecordedDecision]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split recorded decisions into the live ones, the stale ones, and the orphaned ones.

    *Live* is a decision whose item is still derived from a standing certificate **and** whose
    recorded question fingerprint still matches the question being asked. *Stale* is the second
    condition failing: the id survived a rewording, so the decision is filed against a question
    its expert never read, and its item goes back to pending rather than reading as answered.
    *Orphaned* is the first failing: nothing standing rests on that question any more — the usual
    cause is the certificate having been superseded, which is the decision doing its job rather
    than a defect, so it is reported and not raised.
    """
    live: dict[str, list[RecordedDecision]] = {}
    stale: list[dict[str, Any]] = []
    orphaned: list[dict[str, Any]] = []
    for decision in decisions:
        current = fingerprints.get(decision.item_id)
        if current is None:
            orphaned.append(
                {
                    **decision.to_dict(),
                    "detail": (
                        "no standing certificate rests on this item; it was superseded or the "
                        "assumption behind it is no longer load-bearing, so the decision settles "
                        "nothing that is still published"
                    ),
                }
            )
        elif current != decision.question_fingerprint:
            stale.append(
                {
                    **decision.to_dict(),
                    "current_question_fingerprint": current,
                    "detail": (
                        "the question under this id has changed since the decision was recorded, "
                        "so the decision answers wording this expert never read; the item is "
                        "pending again until it is decided as it now reads"
                    ),
                }
            )
        else:
            live.setdefault(decision.item_id, []).append(decision)
    return live, stale, orphaned


def queue_report(
    pairs: Sequence[tuple[str, Certificate]],
    decisions: Sequence[RecordedDecision] = (),
) -> dict[str, Any]:
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

    ``decisions`` are the expert answers this repository has recorded
    (:func:`reprolith.decisions.load_decisions`). An item carrying a live one moves out of
    ``pending`` into ``decided`` — it is no longer awaiting anybody — while keeping every
    qualification it had, because a decision is an answer and not a re-certification. A decision
    whose question has been reworded under the same id is *stale* and leaves its item pending; one
    naming an item nothing standing rests on is *orphaned*. Both are reported rather than dropped:
    an answer that quietly stopped counting is worse than one that says why.

    ``linked`` says whether the certificates naming this item did so themselves or whether the id
    was derived from the question — the difference between a citation a reader can search for and
    one this function computed. ``depends_on_papers`` is the same dependents as ``depends_on``,
    named rather than digested, so an expert can tell whether they know the paper before deciding
    whether they can answer — a 64-character hash is the right identifier for
    :func:`reverify_dependents` and the wrong one for a person.
    """
    queue, assumption_ids, answerable = queue_from_certificates(pairs)
    fingerprints = _item_fingerprints(pairs)
    live, stale, orphaned = _join_decisions(fingerprints, decisions)
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
    decided: list[dict[str, Any]] = []
    stale_by_item: dict[str, list[dict[str, Any]]] = {}
    for record in stale:
        stale_by_item.setdefault(str(record["item_id"]), []).append(record)
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
        # Published because it is what a decision has to quote to be verifiable, and
        # CONTRIBUTING.md tells an expert to copy it into the record they merge. Deriving it and
        # then not showing it would leave the one field of that record un-obtainable.
        view["question_fingerprint"] = fingerprints[item.id]
        # Which half this item belongs to, on the item rather than only in which list it landed
        # in. An item handed around on its own — to the issue generator, to an agent — could not
        # otherwise tell a question for an expert from a limit of this engine, which is the one
        # distinction this report exists to make.
        view["author_can_close"] = item.id in answerable
        answers = live.get(item.id, ())
        # A stale record is shown on the item it was filed against, because an expert looking at
        # a question that reads as untouched should see that somebody answered an earlier wording
        # of it — otherwise the work is silently repeated.
        view["stale_decisions"] = stale_by_item.get(item.id, [])
        if item.id not in answerable:
            # An engine limit never leaves its own heading, decided or not. This report says in so
            # many words that no expert decision closes one, and `issue_for_item` refuses to file
            # one as a question — so letting a recorded decision move it under "decided" would
            # publish an expert as having settled exactly what the two other surfaces say they
            # cannot. The decision is shown on the item instead of being either honored or hidden.
            if answers:
                view["decisions"] = [decision.to_dict() for decision in answers]
                view["decisions_do_not_close"] = (
                    "a decision is recorded against this item, and it does not close it: what "
                    "this value waits on is this engine, not a person"
                )
            engine_limits.append(view)
            continue
        if not answers:
            pending.append(view)
            continue
        view["decisions"] = [decision.to_dict() for decision in answers]
        # Retained, never resolved: two experts who disagree are two records and a flag, because
        # picking one would be resolving the disagreement silently (spec: verification-queue,
        # "Disagreement is preserved, not overwritten").
        view["disputed"] = len({decision.kind for decision in answers}) > 1
        # Mechanical, not asserted. Were the dependents re-issued against this decision, the
        # assumption behind the item would no longer be load-bearing and no item would be derived
        # here at all — so an item appearing in this report is one whose certificates still stand
        # exactly as they were computed, qualification included.
        view["dependents_reissued"] = False
        view["qualification"] = (
            "the certificates resting on this value still carry it as an unreviewed load-bearing "
            "assumption and still withhold a clean pass; a decision does not re-issue them, "
            "reverify_dependents does"
        )
        kinds = {decision.kind for decision in answers}
        if kinds == {"reject"}:
            view["action_required"] = (
                "the estimate was rejected and a rejection supplies no replacement, so the "
                "dependents cannot be re-issued — the value has to be corrected first"
            )
        decided.append(view)
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
            "left unsaid — the wall the spatial solver ran under, the ensemble the stochastic "
            "class drew — so no expert decision closes one. They withhold a clean pass exactly as "
            "the others do; what they wait on is this engine, not a person"
        ),
        "ranked_by": (
            "impact — the number of standing certificates resting on the value. Margin is not "
            "ranked on: a certificate states its discrepancy and tolerance as prose, and a "
            "number parsed back out of prose is a guess, not a measurement"
        ),
        "decided": decided,
        "decided_count": len(decided),
        "stale_decisions": stale,
        "orphaned_decisions": orphaned,
        "decisions": [decision.to_dict() for decision in decisions],
        "decisions_note": _decisions_note(
            decided,
            decisions,
            stale,
            orphaned,
            sum(len(item.get("decisions", ())) for item in engine_limits),
        ),
    }


def _decisions_note(
    decided: Sequence[dict[str, Any]],
    decisions: Sequence[RecordedDecision],
    stale: Sequence[dict[str, Any]],
    orphaned: Sequence[dict[str, Any]],
    on_limits: int = 0,
) -> str:
    """What the committed decision record actually says, derived rather than asserted.

    This sentence used to be a constant reading "nothing on disk carries one yet", which was true
    of the repository and false of the software the moment a decision was recorded — the shape of
    claim this project keeps finding in its own output. It is computed from the file now, so it
    cannot outlive the state it describes.
    """
    if not decisions:
        return (
            "no expert decision is recorded in this repository, so every item here is pending. A "
            "decision lands as a record in datasets/verification_decisions.json and is acted on "
            "through reverify_dependents"
        )
    parts = [
        f"{len(decisions)} expert decision(s) recorded; {len(decided)} item(s) decided",
    ]
    if on_limits:
        parts.append(
            f"{on_limits} name(s) a limit of this engine, which no decision closes — the item "
            "stays under its own heading"
        )
    if stale:
        parts.append(
            f"{len(stale)} answer(s) a question that has since been reworded and are shown "
            "beside the item, which is pending again"
        )
    if orphaned:
        parts.append(
            f"{len(orphaned)} name(s) an item no standing certificate rests on any more"
        )
    parts.append(
        "no decision re-issues a certificate: the dependents of a decided item still carry the "
        "value as unreviewed until reverify_dependents replaces them"
    )
    return "; ".join(parts)


#: The label every verification issue carries, so the whole set is one search.
ISSUE_LABEL = "verification"


def issue_for_item(item: dict[str, Any], *, model_classes: Sequence[str] = ()) -> dict[str, Any]:
    """The GitHub issue for one queue item: title, labels, and a filled body.

    The ``github-collaboration`` spec asks that an escalated item surface as a structured issue
    carrying the question, the source context, Reprolith's estimate and reasoning, and what
    depends on it — "labelled with its model class, its impact rank, and a pending-verification
    status". Nothing filed one, and nothing filled one either: the template's own description says
    it is opened by hand, and every field had to be transcribed out of a certificate by eye. The
    queue put the values in one place; this puts them in the shape the template asks for, so
    opening an issue is ``gh issue create --title ... --body-file -`` rather than a transcription.
    Nothing here touches the network — it prints, and a person or a command files it.

    ``item`` is a view from :func:`queue_report`'s ``pending`` list. An **engine-limit** item is
    refused by name: no expert decision closes one, so filing it asks a stranger for a judgment
    that cannot help, which is the overstatement the queue's two headings exist to prevent.

    ``model_classes`` labels the issue by pathway. It is a property of the entry rather than of
    the certificate, so it is passed in (:meth:`ReprolithQuery.model_class_of`) rather than read
    off the item; an item spanning classes gets a label for each, and an unknown one gets none
    rather than a guess.

    **Source context** is where this stops short, deliberately. The template asks for the section,
    equation, table or figure the value comes from, and Reprolith does not carry one *for an
    assumption* — a claim records its ``source_location``, an assumption records its basis, which
    is a reason and not a location. The body says that in so many words and gives what does exist:
    the basis, and the assumption ids to grep the certificates for. Filling it with a plausible
    location would be the field's worst possible failure.
    """
    if not item.get("author_can_close", True):
        raise ValueError(
            f"verification item {item['id']!r} is a limit of this engine, not a question a paper "
            "could answer — no expert decision closes it, so filing it as an issue asks a "
            "stranger for a judgment that cannot help. It is listed under the queue's second "
            "heading for exactly this reason"
        )
    labels = [ISSUE_LABEL, f"impact:{item['impact']}", "status:pending-verification"]
    labels += [f"class:{name}" for name in sorted(set(model_classes))]
    papers = item.get("depends_on_papers", [])
    rests = "\n".join(
        f"- {paper['title']}" + (f" ({paper['doi']})" if paper.get("doi") else "")
        for paper in papers
    ) or "- (no paper named on the dependent certificates)"
    alternatives = "\n".join(f"- {alt}" for alt in item["alternatives"]) or "- (none recorded)"
    dependents = "certificate" if item["impact"] == 1 else "certificates"
    cited = (
        "The certificates name this item as `" + item["id"] + "`."
        if item.get("linked")
        else (
            "No certificate names this id — it is derived from the question itself. Grep the "
            "assumption id instead: " + ", ".join(item.get("assumption_ids", ()))
        )
    )
    body = f"""### The specific question

{item['question']}

### Reprolith's best estimate and reasoning

**{item['best_estimate']}**

{item['basis']}

Alternatives considered:

{alternatives}

### Source context

Reprolith records no section, equation, table or figure for an assumption: a *claim* carries a
source location, an assumption carries the basis above, which is a reason rather than a place.
{cited}

### What depends on this

{item['impact']} standing {dependents}:

{rests}

### How to answer

Confirm, correct (with the right value and a source), or reject (with why) in a comment. To make
your decision the record, add it to `datasets/verification_decisions.json` in a pull request that
references this issue, with this fingerprint so it stays attached to the question as you read it:

```
{item['question_fingerprint']}
```

Answering does not re-issue anything: the certificates above keep resting on the value as
unreviewed until they are re-run and superseded.
"""
    return {
        "title": f"[verify] {item['question']}",
        "labels": labels,
        "body": body,
        "item_id": item["id"],
    }


#: A question fingerprint as :func:`issue_for_item` writes it into the issue body: the only
#: identifier on a filed issue that cannot come to sit under a different question, since it *is*
#: the digest of the question. A title can be edited and an item id can be an author's name for it.
_FINGERPRINT = re.compile(r"\b[0-9a-f]{64}\b")


def reconcile_issues(
    report: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
    *,
    expected_labels: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Where the filed issues and the derived queue disagree (spec: github-collaboration).

    The ``github-collaboration`` spec asks that "the queue state and the issue state are
    reconciled so neither silently diverges from the other", and its own carrier section said
    plainly that nothing did it. The two sides drift in both directions and neither can see it:
    the queue is derived from the standing certificates on every call, so an item vanishes the
    moment its certificates are superseded and its issue keeps asking; and an issue can be closed,
    relabelled, or never opened at all without anything in the repository noticing.

    ``report`` is :func:`queue_report`'s output. ``issues`` are the issues as ``gh issue list
    --json number,title,state,labels,body`` emits them — this touches no network, so the fetch is
    a command a person or a workflow runs and this is the comparison. ``expected_labels`` maps a
    pending item's id to the labels :func:`issue_for_item` would file it under; an item missing
    from it has its labels left uncompared rather than guessed at.

    **It reconciles and does not resolve.** Nothing here closes an issue, reopens one, or edits
    the queue: both sides are somebody's record — a maintainer's on GitHub, the certificates' here
    — and a divergence is a question about which one is wrong, not a fact about which one loses.

    Issues are matched by the question fingerprint the body carries, not by title or item id.
    Reprolith's own decision record is joined that way for the same reason: a question that has
    been reworded is a different question, and an issue still asking the old one has diverged
    rather than stayed attached.
    """
    groups = {
        name: {
            str(item["question_fingerprint"]): item
            for item in report.get(name, ())
            if item.get("question_fingerprint")
        }
        for name in ("pending", "engine_limits", "decided")
    }
    known = {
        fingerprint: (name, item)
        for name, items in groups.items()
        for fingerprint, item in items.items()
    }
    records: list[dict[str, Any]] = []
    ignored = 0
    filed: set[str] = set()
    for raw in issues:
        number, state, labels, body = _issue_fields(raw)
        # Every 64-hex token in the body, not the first one: a certificate digest is the same
        # shape and an issue that quotes one — in a comment, in a maintainer's edit — would
        # otherwise be matched on it and read as asking a question nothing rests on. The first
        # token that *is* a live question wins; with none, the first token is reported as the
        # unmatched one rather than the issue reading as having no fingerprint at all.
        candidates = _FINGERPRINT.findall(body)
        fingerprint = next(
            (candidate for candidate in candidates if candidate in known),
            candidates[0] if candidates else None,
        )
        # An issue is this queue's if it carries the label *or* asks one of its questions. Keying
        # on the label alone would let a relabelled issue — exactly the drift this reports —
        # disappear from the report by having drifted.
        if ISSUE_LABEL not in labels and fingerprint not in known:
            ignored += 1
            continue
        if fingerprint is not None:
            filed.add(fingerprint)
        matched = known.get(fingerprint) if fingerprint else None
        record: dict[str, Any] = {
            "number": number,
            "title": str(raw.get("title", "")),
            "state": state,
            "labels": labels,
            "item_id": matched[1]["id"] if matched else None,
            "group": matched[0] if matched else None,
            "divergences": [],
        }
        if matched is None:
            record["status"] = "unrecognized" if fingerprint is None else "no-longer-asked"
            if state == "OPEN":
                record["divergences"].append(
                    "asks a question no standing certificate rests on any more, and is open: "
                    "either its certificates were superseded or the question was reworded, and "
                    "in both cases the issue is asking for work that no longer lands"
                    if fingerprint is not None
                    else "carries the verification label and no question fingerprint, so nothing "
                    "can attach it to an item; it was not written by `reprolith "
                    "verification-issue`"
                )
            records.append(record)
            continue
        group, item = matched
        if group == "engine_limits":
            record["status"] = "engine-limit"
            if state == "OPEN":
                record["divergences"].append(
                    "asks about a limit of this engine, which no expert decision closes — "
                    "`verification-issue` refuses to write one, so this was filed by hand or "
                    "before the item became one"
                )
        elif group == "decided":
            record["status"] = "decided"
            if state == "OPEN":
                record["divergences"].append(
                    f"{len(item.get('decisions', ()))} expert decision(s) are recorded against "
                    "this item and the issue is still open. Closing it does not lift the "
                    "dependent certificates' qualification — that is a re-issue, not an answer"
                )
        else:
            record["status"] = "pending"
            if state != "OPEN":
                record["divergences"].append(
                    "is closed while its question is still pending: the certificates resting on "
                    "the value are standing and unreviewed, so the queue still asks it"
                )
            expected = list(expected_labels.get(str(item["id"]), ()))
            if expected:
                record["expected_labels"] = expected
                missing = [label for label in expected if label not in labels]
                if missing:
                    record["divergences"].append(
                        "is missing the label(s) the item carries today: " + ", ".join(missing)
                    )
        records.append(record)
    # Two open issues asking one question is drift in its own right: an expert answers one of
    # them, the other keeps asking, and the decision record attaches to a question rather than to
    # an issue — so nothing downstream would notice which one was answered. Only open issues
    # count; a closed duplicate is the normal shape of a question that was filed twice and tidied.
    open_by_item: dict[str, list[Any]] = {}
    for record in records:
        if record["item_id"] and record["state"] == "OPEN":
            open_by_item.setdefault(str(record["item_id"]), []).append(record["number"])
    for record in records:
        numbers = open_by_item.get(str(record["item_id"]), ())
        if len(numbers) > 1 and record["state"] == "OPEN":
            others = [number for number in numbers if number != record["number"]]
            record["divergences"].append(
                "asks the same question as #" + ", #".join(str(n) for n in others)
                + ": an expert answering one of them leaves the other still asking, and a "
                "decision is recorded against the question rather than against an issue"
            )
    unfiled = [
        {
            "id": item["id"],
            "question": item["question"],
            "impact": item["impact"],
            "question_fingerprint": fingerprint,
        }
        for fingerprint, item in groups["pending"].items()
        if fingerprint not in filed
    ]
    divergent = [record for record in records if record["divergences"]]
    return {
        "issues": records,
        "divergent": divergent,
        "divergent_count": len(divergent),
        "in_sync": len(records) - len(divergent),
        "unfiled": unfiled,
        "unfiled_count": len(unfiled),
        "ignored_issues": ignored,
        "note": _reconciliation_note(records, divergent, unfiled, ignored),
    }


def _issue_fields(raw: Mapping[str, Any]) -> tuple[Any, str, list[str], str]:
    """One issue's four fields, refusing a shape that would reconcile against nothing.

    A missing body is the dangerous one: it carries the fingerprint, so an issue read without it
    matches no item and is reported as unrecognized — a fetch that forgot `--json body` would
    otherwise read as every issue having drifted.
    """
    if not isinstance(raw, Mapping):
        raise ValueError(f"an issue must be an object, not {type(raw).__name__}")
    for field in ("number", "state", "body"):
        if field not in raw:
            raise ValueError(
                f"issue {raw.get('number', '(unnumbered)')} has no {field!r}; fetch with "
                "`gh issue list --json number,title,state,labels,body` — a field left out reads "
                "as a divergence rather than as a missing field"
            )
    labels: list[str] = []
    for label in raw.get("labels", ()):
        if isinstance(label, Mapping):
            labels.append(str(label.get("name", "")))
        else:
            labels.append(str(label))
    return raw["number"], str(raw["state"]).upper(), labels, str(raw["body"])


def _reconciliation_note(
    records: Sequence[Mapping[str, Any]],
    divergent: Sequence[Mapping[str, Any]],
    unfiled: Sequence[Mapping[str, Any]],
    ignored: int,
) -> str:
    """What the comparison found, derived from it rather than asserted."""
    if not records and not unfiled:
        return (
            "no verification issue was given and the queue has nothing pending, so there is "
            "nothing to reconcile"
        )
    parts = [f"{len(records)} verification issue(s) read"]
    if ignored:
        parts.append(f"{ignored} unrelated issue(s) ignored")
    parts.append(
        f"{len(divergent)} diverge from the queue" if divergent else "none diverge from the queue"
    )
    if unfiled:
        parts.append(f"{len(unfiled)} pending item(s) have no issue at all")
    parts.append(
        "nothing here closes, reopens or relabels anything: a divergence is a question about "
        "which side is wrong"
    )
    return "; ".join(parts)


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
    decision. The replacement should link to the one it supersedes (``supersedes``); it is issued
    into the ledger, and the superseded certificate remains retrievable. Returns the replacements,
    so nothing is settled by a stale certificate after the value beneath it changed.

    **A confirmation does not lift the verdict's qualification, and this line used to say it
    did.** :func:`~reprolith.certificate.derive_overall` withholds a clean pass whenever any
    assumption is ``load_bearing``, and confirming one does not stop it being load-bearing: the
    paper still did not state the value, Reprolith still chose it, and it still plausibly changes
    the outcome. That is the honesty rule working, not a gap — an expert agreeing with a guess does
    not turn the guess into something the paper said. All twelve queued assumptions on this
    repository's certificates are load-bearing, so on today's corpus no confirmation could lift any
    verdict at all, and the sentence promised an outcome the surrounding code refuses to produce.

    What a confirmation *does* change is that the value is no longer unreviewed, which is reported
    by the queue and by the certificate's own assumption line (``render_human`` prints
    ``[unverified — pending review: <id>]``) rather than by the overall verdict. A **correction**
    is the case that moves numbers, and there ``recertify`` genuinely re-runs.
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
    "ISSUE_LABEL",
    "VerificationDecision",
    "VerificationItem",
    "VerificationQueue",
    "certificates_needing_review",
    "issue_for_item",
    "question_fingerprint",
    "queue_from_certificates",
    "queue_report",
    "reconcile_issues",
    "reverify_dependents",
]
