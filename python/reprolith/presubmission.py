"""The author-facing pre-submission check (spec: ``presubmission-check``; roadmap #10).

The adoption flywheel: the same reproduction engine, re-presented so an author runs it on their
*own* model before publishing. This module introduces no new oracle — it consumes a
:class:`~reprolith.model.Certificate` the engine already produced and re-frames it for the author
as a readiness signal plus a prioritized "fix this before you submit" list.

Two honesty properties are inherited, not re-derived: the per-claim and overall verdicts and the
scope statement come straight from the certificate (:func:`presubmission_report` never recomputes
a verdict), and the ready-to-submit signal is green only for an unqualified full reproduction, so
a partial or assumption-qualified result can never look ready.
"""

from __future__ import annotations

from typing import Any

from .enums import OverallVerdict, Verdict
from .model import Certificate

# Impact buckets for the fix list, most urgent first. A claim a reproducer cannot even evaluate
# outranks a wrong one; a wrong one outranks a partial; a load-bearing value the author left for
# the engine to assume outranks a certificate-level note (spec: "Gaps are ordered by impact").
_CLAIM_PRIORITY = {
    Verdict.NOT_EVALUABLE: 1,
    Verdict.FAILED: 2,
    Verdict.PARTIAL: 3,
}
_ASSUMPTION_PRIORITY = 4
_NOTE_PRIORITY = 5

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
    ready = cert.overall is OverallVerdict.REPRODUCED and not any(
        a.assumption_qualified for a in cert.assessments
    )

    actions: list[dict[str, Any]] = []
    for a in cert.assessments:
        if a.verdict is Verdict.REPRODUCED:
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
    for asm in cert.assumptions:
        if not asm.load_bearing:
            continue
        actions.append(
            {
                "priority": _ASSUMPTION_PRIORITY,
                "kind": "assumption",
                "claim_id": None,
                "quantity": asm.description,
                "source_location": None,
                "issue": f"Reprolith had to assume a load-bearing value: {asm.chosen}",
                "fix": f"state {asm.description} explicitly so it need not be assumed",
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
        "readiness": _READINESS[cert.overall],
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
