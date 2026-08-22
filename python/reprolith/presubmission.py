"""The author-facing pre-submission check (spec: ``presubmission-check``; roadmap #10).

The adoption flywheel: the same reproduction engine, re-presented so an author runs it on their
*own* model before publishing. This module introduces no new oracle — it consumes a
:class:`~reprolith.model.Certificate` the engine already produced and re-frames it for the author
as a readiness signal plus a prioritized "fix this before you submit" list.

Two honesty properties are inherited, not re-derived: the per-claim and overall verdicts and the
scope statement come straight from the certificate (:func:`presubmission_report` never recomputes
a verdict), and the ready-to-submit signal is green only for an unqualified full *simulation*
reproduction, so a partial, assumption-qualified, or estimation-level result can never look ready.
"""

from __future__ import annotations

from typing import Any

from .enums import OverallVerdict, Verdict
from .model import Certificate
from .render import estimation_claims

# Impact buckets for the fix list, most urgent first. A claim a reproducer cannot even evaluate
# outranks a wrong one; a wrong one outranks a partial; a load-bearing value the author left for
# the engine to assume outranks a certificate-level note (spec: "Gaps are ordered by impact").
_CLAIM_PRIORITY = {
    Verdict.NOT_EVALUABLE: 1,
    Verdict.FAILED: 2,
    Verdict.PARTIAL: 3,
}
_LEVEL_PRIORITY = 4
_ASSUMPTION_PRIORITY = 5
_NOTE_PRIORITY = 6

_READINESS = {
    OverallVerdict.REPRODUCED: (
        "Ready to submit: every claim reproduces cleanly under the pinned engine."
    ),
    OverallVerdict.PARTIALLY_REPRODUCED: (
        "Not yet ready: some claims are partial or rest on values Reprolith had to assume. "
        "Address the fix list before submitting."
    ),
    OverallVerdict.NOT_REPRODUCED: (
        "Not ready: no claim reproduces as stated. The fix list shows what a reproducer will hit."
    ),
    OverallVerdict.BLOCKED: (
        "Not ready: nothing is evaluable yet — a reproducer cannot check any claim. Supply the "
        "missing inputs in the fix list."
    ),
}

# Every claim reproduced, but something else withholds a clean pass — a recorded gap, or a claim
# reproduced at estimation level rather than by simulation. The verdict alone would read as ready.
_REPRODUCED_BUT_NOT_READY = (
    "Not yet ready: every claim reproduces, but not cleanly — see the fix list for what a "
    "reproducer would still have to supply or re-derive."
)


def _claim_issue_and_fix(assessment: Any) -> tuple[str, str]:
    """Phrase a non-reproducing claim as an author-facing issue and a concrete fix."""
    if assessment.verdict is Verdict.NOT_EVALUABLE:
        issue = "a reproducer cannot evaluate this claim"
        fix = assessment.root_cause or "supply evaluable output or digitizable reference data"
        return issue, fix
    issue = assessment.discrepancy or f"{assessment.verdict.value} reproduction"
    fix = (
        assessment.implicated
        or assessment.root_cause
        or "reconcile the reconstructed output with the reported value within tolerance"
    )
    return issue, fix


def presubmission_report(cert: Certificate) -> dict[str, Any]:
    """An author-facing pre-submission report derived from a certificate.

    Returns the readiness signal, the certificate's own per-claim and overall verdicts, a
    prioritized fix list (impact order: not-evaluable, failed, partial claims, then load-bearing
    assumptions the author should state, then certificate-level notes), and the inescapable scope
    statement. A fully reproduced certificate yields an empty fix list.
    """
    # A gap report is a record of something the artifact did not state, so a certificate carrying
    # one is not ready however clean its verdicts read — otherwise the report says READY TO SUBMIT
    # above a list of things to fix first, which is the promise in this docstring broken out loud.
    # An estimation-level claim is the same kind of overstatement: re-fitting a parameter from data
    # is a weaker result than running the described model, so "every claim reproduces cleanly under
    # the pinned engine" is not something this report may say about it.
    # And a claim nobody could evaluate is the fix list's own priority 1, so a report that ranks it
    # first while announcing "every claim reproduces cleanly" contradicts itself in two lines. The
    # overall rule drops abstentions before deciding, by design, so `reproduced` does not imply
    # every claim was judged — this report has to look for itself.
    estimation = estimation_claims(cert)
    ready = (
        cert.overall is OverallVerdict.REPRODUCED
        and not any(a.assumption_qualified for a in cert.assessments)
        and not any(a.verdict is Verdict.NOT_EVALUABLE for a in cert.assessments)
        and not cert.gap_report
        and not estimation
    )

    actions: list[dict[str, Any]] = []
    for a in cert.assessments:
        if a.verdict is Verdict.REPRODUCED:
            if not a.assumption_qualified:
                continue
            # A claim that reproduced *only* under a value Reprolith supplied is the reason the
            # clean pass was withheld, so the list of what to fix has to name it. It fell through
            # every branch when no Assumption object carried it — which the claims-dataset path
            # produces — and the report said "not yet ready" over an empty fix list.
            actions.append(
                {
                    "priority": _ASSUMPTION_PRIORITY,
                    "kind": "assumption",
                    "claim_id": a.claim_id,
                    "quantity": a.quantity,
                    "source_location": a.source_location,
                    "issue": "this claim reproduced only under an assumption Reprolith supplied, "
                             "not as a clean pass",
                    "fix": "state the value this claim rests on so it need not be assumed",
                }
            )
            continue
        issue, fix = _claim_issue_and_fix(a)
        actions.append(
            {
                "priority": _CLAIM_PRIORITY[a.verdict],
                "kind": "claim",
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "source_location": a.source_location,
                "issue": issue,
                "fix": fix,
            }
        )
    for claim_id in estimation:
        a = next(x for x in cert.assessments if x.claim_id == claim_id)
        if a.verdict is not Verdict.REPRODUCED:
            continue  # already in the fix list with its own shortfall
        actions.append(
            {
                "priority": _LEVEL_PRIORITY,
                "kind": "level",
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "source_location": a.source_location,
                "issue": "this claim was reproduced by re-fitting parameters, not by running the "
                         "described model",
                "fix": "state the parameter values and conditions needed to simulate this claim "
                       "directly, so a reproducer need not re-fit it",
            }
        )
    for asm in cert.assumptions:
        # An assumption awaiting expert confirmation withholds the clean pass exactly as a
        # load-bearing one does (derive_overall consults both), so it belongs on the fix list too.
        # The sibling gap report already listed it; this one skipped it.
        if not asm.load_bearing and not asm.verification_item:
            continue
        issue = (
            f"Reprolith had to assume a load-bearing value: {asm.chosen}"
            if asm.load_bearing
            else f"this assumption is awaiting expert confirmation ({asm.verification_item}): "
                 f"{asm.chosen}"
        )
        actions.append(
            {
                "priority": _ASSUMPTION_PRIORITY,
                "kind": "assumption",
                "claim_id": None,
                "quantity": asm.description,
                "source_location": None,
                "issue": issue,
                # `basis` is why Reprolith had to assume it — and for some assumptions it is also
                # the reason the author cannot discharge the item at all: the spatial engine
                # implements one boundary condition and the stochastic class samples an ensemble,
                # so six of the thirty published certificates carried an instruction no wording in
                # any paper could satisfy. The sibling `gaps` report prints the basis; this one,
                # the surface that exists to be acted on, dropped it. An item the author cannot
                # close now says so instead of asking them to try.
                "why": asm.basis,
                "fix": (
                    f"state {asm.description} explicitly so it need not be assumed"
                    if asm.author_can_close
                    else (
                        "nothing in the paper can clear this one — it is a limit of Reprolith's "
                        f"engine, not an omission in the paper: {asm.basis}. If that does not "
                        "describe the model, this result is not evidence about it"
                    )
                ),
            }
        )
    for note in cert.gap_report:
        actions.append(
            {
                "priority": _NOTE_PRIORITY,
                "kind": "note",
                "claim_id": None,
                "quantity": None,
                "source_location": None,
                "issue": note,
                "fix": note,
            }
        )
    # Stable, deterministic order: impact bucket first, insertion order (the certificate's claim
    # order) preserved within a bucket by the stable sort.
    actions.sort(key=lambda item: item["priority"])

    return {
        "overall": cert.overall.value,
        "ready_to_submit": ready,
        "readiness": _READINESS[cert.overall] if ready or cert.overall is not OverallVerdict.REPRODUCED
        else _REPRODUCED_BUT_NOT_READY,
        "per_claim": [a.to_dict() for a in cert.assessments],
        "fix_list": actions,
        "scope": cert.scope.to_dict(),
    }


def render_presubmission_human(cert: Certificate) -> str:
    """A plain-text pre-submission report an author can act on directly."""
    report = presubmission_report(cert)
    paper = cert.paper
    lines: list[str] = []

    lines.append(f"PRE-SUBMISSION REPRODUCIBILITY CHECK — {paper.title}")
    lines.append("")
    verdict = "READY TO SUBMIT" if report["ready_to_submit"] else "NOT YET READY"
    lines.append(f"{verdict}  (overall: {report['overall']})")
    lines.append(f"  {report['readiness']}")
    lines.append("")

    lines.append("FIX BEFORE YOU SUBMIT (most impactful first)")
    if not report["fix_list"]:
        lines.append("  (nothing — every claim reproduces cleanly)")
    for item in report["fix_list"]:
        where = f"[{item['claim_id']}] {item['quantity']}: " if item["claim_id"] else ""
        if not where and item["quantity"]:
            where = f"{item['quantity']}: "
        source = f" (source {item['source_location']})" if item["source_location"] else ""
        lines.append(f"  - {where}{item['issue']}{source}")
        lines.append(f"      fix: {item['fix']}")
    lines.append("")

    lines.append("SCOPE")
    lines.append(f"  {cert.scope.human}")
    return "\n".join(lines)


__all__ = ["presubmission_report", "render_presubmission_human"]
