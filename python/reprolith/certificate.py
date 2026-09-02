"""Deriving the overall verdict, and enforcing the honesty invariants.

This is the one place the certificate-level verdict is decided, by an explicit rule
(spec: ``reproduction-certificate`` — "Per-claim, qualified verdicts"). Two invariants
are enforced here so no other code path can bypass them:

* a mixed result is never rounded up to a clean pass, and
* a full reproduction that rests on a load-bearing assumption is downgraded to
  *partially reproduced* — Reprolith never takes unqualified credit for its own guesses.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .canonical import content_hash
from .enums import OverallVerdict, ReproductionLevel, Verdict
from .model import (
    REPROLITH_ATTRIBUTION,
    Assumption,
    Certificate,
    ClaimAssessment,
    ClaimSelection,
    EnginePin,
    PaperIdentity,
)
from .scope import Scope


def derive_overall(
    assessments: Sequence[ClaimAssessment],
    assumptions: Sequence[Assumption] = (),
    selection: ClaimSelection | None = None,
) -> OverallVerdict:
    """Derive the certificate-level verdict from per-claim assessments.

    The rule, stated plainly:

    * nothing evaluable (empty, or every claim ``not-evaluable``) -> ``blocked``;
    * every evaluable claim ``reproduced``, none assumption-qualified, and no load-bearing or
      awaiting-verification assumption on the record -> ``reproduced``;
    * every evaluable claim ``reproduced`` but at least one assumption-qualified, *or* a
      load-bearing assumption present, *or* an assumption still awaiting expert verification, *or*
      a budgeted selection left a claim unattempted -> ``partially-reproduced`` (any of the four
      forbids a clean pass);
    * some but not all evaluable claims ``reproduced`` -> ``partially-reproduced``;
    * no evaluable claim ``reproduced`` -> ``not-reproduced``.

    The load-bearing-assumption downgrade is enforced here, not only through each claim's
    ``assumption_qualified`` flag, so a caller cannot slip a load-bearing guess past the clean
    pass by handing the assumption to ``build_certificate`` while leaving the claim unqualified.

    An assumption carrying a ``verification_item`` is a value queued for an expert to confirm, and
    the verification-queue spec requires a result resting on one to be reported as qualified until
    that decision comes back. Nothing sets the field today, so this changes no existing
    certificate — but the rule belongs with the other two rather than waiting for the first caller
    that would need it.

    The fourth is the budget. A paper's claims are not equally likely to reproduce, so a
    certification that attempted three of a paper's thirty-three and passed all three has
    demonstrated something much weaker than one that attempted all thirty-three — and read as an
    unqualified ``reproduced`` it would be indistinguishable from it, while being the cheapest
    route to the word. So an unattempted claim withholds the clean pass for the same reason a
    load-bearing assumption does: the result is real, and it rests on something the reader has to
    be told about. It cannot *rescue* a verdict — a selection never turns a miss into a pass.
    """
    evaluable = [a for a in assessments if a.verdict is not Verdict.NOT_EVALUABLE]
    if not evaluable:
        return OverallVerdict.BLOCKED

    reproduced = [a for a in evaluable if a.verdict is Verdict.REPRODUCED]

    if len(reproduced) == len(evaluable):
        qualified = any(a.assumption_qualified for a in reproduced)
        load_bearing = any(a.load_bearing for a in assumptions)
        awaiting = any(a.verification_item for a in assumptions)
        unattempted = bool(selection is not None and selection.unattempted)
        if qualified or load_bearing or awaiting or unattempted:
            return OverallVerdict.PARTIALLY_REPRODUCED
        return OverallVerdict.REPRODUCED

    if reproduced:
        return OverallVerdict.PARTIALLY_REPRODUCED

    return OverallVerdict.NOT_REPRODUCED


def require_stated_protocol(
    assessments: Sequence[ClaimAssessment],
) -> None:
    """Refuse a certificate whose supplied-number verdicts do not say how they were produced.

    An estimation verdict and a population-envelope verdict are both judged from numbers handed to
    Reprolith rather than computed by it — the re-fitter and the population simulator are the
    deferred halves — so the protocol behind them is the only evidence on the certificate that a run
    happened at all. Without it, ``recovered == reported`` is a clean pass with nothing behind it,
    and an envelope's verdict cannot be told apart from a subject count chosen until one appeared.

    The claim types refuse a blank protocol where they are built, but that check is escapable: the
    judges and this builder are all public, so a caller can assemble the same certificate from
    assessments directly. The invariant belongs here, with the other two, where no path around it
    exists.
    """
    for assessment in assessments:
        if assessment.verdict is Verdict.NOT_EVALUABLE:
            continue  # nothing was concluded, so there is no judgment resting on a protocol
        sampled = (
            assessment.level is ReproductionLevel.ESTIMATION
            or assessment.method == "distribution-band-distance"
        )
        if sampled and not (assessment.protocol or "").strip():
            raise ValueError(
                f"claim {assessment.claim_id!r} is judged from numbers Reprolith did not produce "
                "itself, so it must record the protocol behind them (the estimation method, or "
                "the population sampling); a verdict nobody can re-derive is not evidence"
            )


def require_distinct_assumption_ids(assumptions: Sequence[Assumption]) -> None:
    """Refuse two assumptions sharing an id: one of them is unreadable on the certificate.

    Ids are how an assumption is referred to — by a gap report, by a verification item, by a reader
    tracing which guess a verdict rests on. Two entries under one id can state contradictory values
    and different load-bearing flags, and nothing downstream can say which one qualified the result.
    """
    seen = set()
    for assumption in assumptions:
        if assumption.id in seen:
            raise ValueError(
                f"assumption id {assumption.id!r} appears twice; an assumption a verdict rests on "
                "has to be identifiable, so give each one its own id"
            )
        seen.add(assumption.id)


def require_distinct_claim_ids(assessments: Sequence[ClaimAssessment]) -> None:
    """Refuse two assessments sharing a claim id: one of them cannot be addressed.

    The same argument as :func:`require_distinct_assumption_ids`, and with a demonstrated
    consequence. A claim id is how a claim is referred to — by the gap report, by an agent
    recording an outcome against it, by a reader tracing a verdict back to a figure. The gap
    report resolves an estimation claim by looking its id up among the assessments, so under two
    claims sharing one id it emitted the first claim's row twice and dropped the second's
    shortfall entirely: a published "what was missing" report missing exactly one of the things
    that was missing.
    """
    seen = set()
    for assessment in assessments:
        if assessment.claim_id in seen:
            raise ValueError(
                f"claim id {assessment.claim_id!r} appears twice; a claim a verdict is published "
                "against has to be identifiable, so give each one its own id"
            )
        seen.add(assessment.claim_id)


def require_readable_gap_notes(gap_report: Sequence[str]) -> tuple[str, ...]:
    """Refuse a "what was missing" note that is not readable text.

    `gap_report` is declared `tuple[str, ...]` and is published verbatim — by the human render, by
    the registry card, by the author-facing fix list. An annotation is not a check: a list of `Gap`
    objects, or a stray `None`, serialized, digested, reloaded and rendered, printing its `repr`
    into a certificate as though it were a sentence about a paper. The sibling rule for
    `attributed_to` is enforced on both the build and the load path; this is the field it skipped.
    """
    notes = tuple(gap_report)
    for note in notes:
        if not isinstance(note, str) or not note.strip():
            raise ValueError(
                f"a gap note must be non-empty text, not {note!r} — it is published verbatim as "
                "the certificate's account of what was missing"
            )
    return notes


def require_reprolith_attribution(assumptions: Sequence[Assumption]) -> None:
    """Refuse an assumption attributed to anyone but Reprolith.

    An assumption is, by definition, a value Reprolith supplied because the paper did not. The
    certificate prints them under "ASSUMPTIONS (supplied by Reprolith, not the paper)" while the
    machine form carries the field verbatim — so a certificate naming the paper as the source of
    its own guess states two contradictory things about one number, and an agent reading the
    machine form gets only the false half. The field was free text with a default, which is to say
    the invariant was carried by a docstring; every committed assumption honours it, and this is
    what keeps a contributed or hand-edited certificate honouring it too.
    """
    for assumption in assumptions:
        if assumption.attributed_to != REPROLITH_ATTRIBUTION:
            raise ValueError(
                f"assumption {assumption.id!r} is attributed to {assumption.attributed_to!r}, but "
                "an assumption is a value Reprolith supplied because the paper did not — it can "
                f"only be attributed to {REPROLITH_ATTRIBUTION!r}"
            )


def require_stated_cause(assessments: Iterable[ClaimAssessment]) -> None:
    """Refuse a non-pass verdict that names no reason for it.

    The judges enforce this at the moment they decide — a partial or failed verdict must carry a
    root cause — but the builder and the load path did not, so a hand-edited or contributed
    certificate could say `failed` with `root_cause`, `implicated`, and `fault_hypothesis` all
    null. The reader is then told, by `render.gap_items`, that the claim had no evaluable output —
    a reason invented for a claim the certificate says *was* evaluated and missed. The public
    registry reads certificates off disk and never rebuilds them, which is the same door
    :func:`require_stated_protocol` and :func:`require_distinct_assumption_ids` were hoisted to.
    """
    for assessment in assessments:
        if assessment.verdict not in (Verdict.PARTIAL, Verdict.FAILED):
            continue
        # The disjunction has to match what a reader is shown. `render.gap_items` prints the root
        # cause or falls back to "no evaluable output" — so accepting an `implicated`-only
        # assessment left exactly the invented sentence this guard promises to remove. Whitespace
        # is not a cause either: a root cause of "   " printed as "   ".
        if not (assessment.root_cause or "").strip():
            raise ValueError(
                f"claim {assessment.claim_id!r} is published as {assessment.verdict.value!r} "
                "with no root cause; a miss this certificate asserts has to say what missed, and "
                "an implicated element or a fault hypothesis alone is not what the gap report "
                "prints"
            )


def require_selection_is_disjoint(
    assessments: Sequence[ClaimAssessment], selection: ClaimSelection | None
) -> None:
    """Refuse a certificate that both judges a claim and says it never attempted it.

    The two lists answer the same question — did Reprolith look at this claim — and a claim in
    both makes the certificate say yes and no at once. Which half a surface believes then depends
    on which one it walks: the verdict counters would count the assessment, the human render would
    print the claim under NOT ATTEMPTED, and a reader comparing the two would be told the
    certificate is inconsistent by a page that is supposed to be the evidence.

    Cheap to trip by accident, too, and in the direction that flatters: the budgeted path hands
    ``certify_model`` the selected claims and the record of the rest, so passing the *whole* claim
    set alongside the record produces a certificate that judged everything while advertising that
    it did not — a full result wearing a budget's excuse.
    """
    if selection is None:
        return
    judged = {a.claim_id for a in assessments}
    for claim in selection.unattempted:
        if claim.claim_id in judged:
            raise ValueError(
                f"claim {claim.claim_id!r} is recorded as unattempted and also carries a verdict; "
                "a certificate cannot both judge a claim and say it never ran it"
            )


def build_certificate(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    assessments: Iterable[ClaimAssessment],
    assumptions: Iterable[Assumption] = (),
    gap_report: Sequence[str] = (),
    scope: Scope | None = None,
    selection: ClaimSelection | None = None,
    supersedes: Certificate | None = None,
) -> Certificate:
    """Construct a certificate with its overall verdict derived and scope attached.

    The overall verdict is always computed here, never passed in, so the honesty
    invariants cannot be sidestepped by a caller. Both the per-claim ``assumption_qualified``
    flags and the load-bearing flags on ``assumptions`` feed the downgrade, so handing a
    load-bearing assumption to this builder forces *partially reproduced* even when every claim
    is otherwise a clean pass, and so does a ``selection`` that left a claim unattempted. The
    scope statement is always present. When ``supersedes`` is given, the new certificate links to
    that prior one by its content digest; the prior certificate is not modified and remains a
    distinct, retrievable record.
    """
    frozen_assessments = tuple(assessments)
    frozen_assumptions = tuple(assumptions)
    require_stated_protocol(frozen_assessments)
    require_stated_cause(frozen_assessments)
    require_distinct_claim_ids(frozen_assessments)
    require_distinct_assumption_ids(frozen_assumptions)
    require_reprolith_attribution(frozen_assumptions)
    require_selection_is_disjoint(frozen_assessments, selection)
    frozen_gaps = require_readable_gap_notes(gap_report)
    # …including the pin/protocol agreement the load path checks, so the builder cannot mint a
    # certificate that its own loader refuses. The check lives in `persistence` beside the other
    # load-path invariants; imported here rather than duplicated, so the two cannot drift.
    from .persistence import require_pin_agrees_with_protocol

    require_pin_agrees_with_protocol(frozen_assessments, engine_pin.algorithm)
    return Certificate(
        paper=paper,
        engine_pin=engine_pin,
        overall=derive_overall(frozen_assessments, frozen_assumptions, selection),
        scope=scope if scope is not None else Scope(),
        selection=selection,
        assessments=frozen_assessments,
        assumptions=frozen_assumptions,
        gap_report=frozen_gaps,
        supersedes=content_hash(supersedes.content()) if supersedes is not None else None,
    )
