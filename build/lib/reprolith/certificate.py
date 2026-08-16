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
from .enums import OverallVerdict, Verdict
from .model import (
    Assumption,
    Certificate,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
)
from .scope import Scope


def derive_overall(
    assessments: Sequence[ClaimAssessment],
    assumptions: Sequence[Assumption] = (),
) -> OverallVerdict:
    """Derive the certificate-level verdict from per-claim assessments.

    The rule, stated plainly:

    * nothing evaluable (empty, or every claim ``not-evaluable``) -> ``blocked``;
    * every evaluable claim ``reproduced``, none assumption-qualified, and no load-bearing
      assumption on the record -> ``reproduced``;
    * every evaluable claim ``reproduced`` but at least one assumption-qualified, *or* a
      load-bearing assumption present -> ``partially-reproduced`` (either forbids a clean pass);
    * some but not all evaluable claims ``reproduced`` -> ``partially-reproduced``;
    * no evaluable claim ``reproduced`` -> ``not-reproduced``.

    The load-bearing-assumption downgrade is enforced here, not only through each claim's
    ``assumption_qualified`` flag, so a caller cannot slip a load-bearing guess past the clean
    pass by handing the assumption to ``build_certificate`` while leaving the claim unqualified.
    """
    evaluable = [a for a in assessments if a.verdict is not Verdict.NOT_EVALUABLE]
    if not evaluable:
        return OverallVerdict.BLOCKED

    reproduced = [a for a in evaluable if a.verdict is Verdict.REPRODUCED]

    if len(reproduced) == len(evaluable):
        qualified = any(a.assumption_qualified for a in reproduced)
        load_bearing = any(a.load_bearing for a in assumptions)
        if qualified or load_bearing:
            return OverallVerdict.PARTIALLY_REPRODUCED
        return OverallVerdict.REPRODUCED

    if reproduced:
        return OverallVerdict.PARTIALLY_REPRODUCED

    return OverallVerdict.NOT_REPRODUCED


def build_certificate(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    assessments: Iterable[ClaimAssessment],
    assumptions: Iterable[Assumption] = (),
    gap_report: Iterable[str] = (),
    scope: Scope | None = None,
    supersedes: Certificate | None = None,
) -> Certificate:
    """Construct a certificate with its overall verdict derived and scope attached.

    The overall verdict is always computed here, never passed in, so the honesty
    invariants cannot be sidestepped by a caller. Both the per-claim ``assumption_qualified``
    flags and the load-bearing flags on ``assumptions`` feed the downgrade, so handing a
    load-bearing assumption to this builder forces *partially reproduced* even when every claim
    is otherwise a clean pass. The scope statement is always present. When ``supersedes`` is
    given, the new certificate links to that prior one by its content digest; the prior
    certificate is not modified and remains a distinct, retrievable record.
    """
    frozen_assessments = tuple(assessments)
    frozen_assumptions = tuple(assumptions)
    return Certificate(
        paper=paper,
        engine_pin=engine_pin,
        overall=derive_overall(frozen_assessments, frozen_assumptions),
        scope=scope if scope is not None else Scope(),
        assessments=frozen_assessments,
        assumptions=frozen_assumptions,
        gap_report=tuple(gap_report),
        supersedes=content_hash(supersedes.content()) if supersedes is not None else None,
    )
