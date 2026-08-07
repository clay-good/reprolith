"""Emitting a certificate in machine- and human-readable form (bootstrap tasks 5.1, 5.2, 5.4).

A certificate must be legible to an outside reader with no access to Reprolith internals
(spec: ``reproduction-certificate`` — "MVP certificate is the walkable artifact"). Both the
machine form and the human form are derived here from *one* source — :func:`render_machine`
builds the structured view, and :func:`render_human` writes prose from that same view — so
the two can never disagree.

Two derived facts the certificate content does not store are computed here so both renderings
show them identically: the per-verdict claim counts (so ``partially-reproduced`` is never read
as full reproduction) and the structured "what was missing" gap report tying each shortfall to
the claim it blocks.
"""

from __future__ import annotations

from typing import Any

from .enums import Verdict
from .model import Certificate, RunMetadata


def claim_counts(cert: Certificate) -> dict[str, int]:
    """The number of claims at each verdict, every verdict present (zero if unused)."""
    counts = {v.value: 0 for v in Verdict}
    for a in cert.assessments:
        counts[a.verdict.value] += 1
    return counts


def gap_items(cert: Certificate) -> list[dict[str, Any]]:
    """The structured "what was missing" report for anything short of full reproduction.

    One item per claim that did not cleanly reproduce, each tying the shortfall to the
    claim it blocks — its identifier, quantity, verdict, source location, and the specific
    thing needed to close it (the implicated root cause, else the observed discrepancy, else
    a plain statement that evaluable output or reference data is required). Certificate-level
    gap notes follow, not tied to a single claim.
    """
    items: list[dict[str, Any]] = []
    for a in cert.assessments:
        if a.verdict is Verdict.REPRODUCED:
            continue
        needs = a.root_cause or a.discrepancy or "evaluable output or reference data for this claim"
        items.append(
            {
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "verdict": a.verdict.value,
                "source_location": a.source_location,
                "needs": needs,
            }
        )
    for note in cert.gap_report:
        items.append({"claim_id": None, "quantity": None, "verdict": None, "source_location": None, "needs": note})
    return items


def render_machine(cert: Certificate, run: RunMetadata) -> dict[str, Any]:
    """The machine-readable certificate: full content plus the derived summary and gaps.

    The content and run blocks are exactly the stored certificate; ``summary`` and ``gaps``
    are derived so no consumer has to recompute them (and so the human form can render from
    this one view).
    """
    return {
        **cert.to_dict(run),
        "summary": {
            "overall": cert.overall.value,
            "claim_counts": claim_counts(cert),
            "assumption_qualified_claims": [
                a.claim_id for a in cert.assessments if a.assumption_qualified
            ],
        },
        "gaps": gap_items(cert),
    }


# Badge colors. Only a clean reproduction is green: a qualified or partial result must look
# visibly distinct, because a silent green would overstate reproducibility (spec:
# certificate-publication — "No silent green").
_BADGE_COLOR = {
    "reproduced": "#4c1",  # green — reserved for an unqualified full reproduction
    "partially-reproduced": "#dfb317",  # amber — never green
    "not-reproduced": "#e05d44",  # red
    "blocked": "#9f9f9f",  # grey
}


def render_badge(cert: Certificate) -> str:
    """A self-contained SVG status badge for a certificate (spec: certificate-publication).

    The colour reflects the overall verdict and reserves green for an unqualified reproduction,
    so a qualified or partial result can never render as a clean success. The scope statement
    travels in the badge's title and cannot be emptied.
    """
    verdict = cert.overall.value
    color = _BADGE_COLOR[verdict]
    label = "reprolith"
    label_w = len(label) * 7 + 10
    value_w = len(verdict) * 7 + 10
    total = label_w + value_w
    scope = cert.scope.machine
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" '
        f'aria-label="{label}: {verdict}">'
        f"<title>{label}: {verdict} ({scope})</title>"
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>'
        f'<g fill="#fff" font-family="Verdana,Geneva,sans-serif" font-size="11" text-anchor="middle">'
        f'<text x="{label_w / 2:.0f}" y="14">{label}</text>'
        f'<text x="{label_w + value_w / 2:.0f}" y="14">{verdict}</text>'
        f"</g></svg>"
    )


def render_human(cert: Certificate, run: RunMetadata) -> str:
    """A self-contained, plain-text certificate a stranger can follow.

    Built from :func:`render_machine`'s output, never from the certificate directly, so the
    human and machine forms are guaranteed to report the same verdict, counts, scope, and gaps.
    """
    m = render_machine(cert, run)
    content = m["content"]
    paper = content["paper"]
    pin = content["engine_pin"]
    summary = m["summary"]
    lines: list[str] = []

    lines.append(f"REPRODUCTION CERTIFICATE — {paper['title']}")
    ids = ", ".join(f"{k}={paper[k]}" for k in ("doi", "pubmed_id") if paper.get(k))
    if ids:
        lines.append(f"  {ids}")
    algo = f" / {pin['algorithm']}" if pin.get("algorithm") else ""
    lines.append(f"Engine pin: {pin['engine']} {pin['version']}{algo}")
    lines.append("")

    lines.append(f"OVERALL: {summary['overall']}")
    counts = summary["claim_counts"]
    lines.append("  claims by verdict: " + ", ".join(f"{k}={counts[k]}" for k in counts))
    if summary["assumption_qualified_claims"]:
        joined = ", ".join(summary["assumption_qualified_claims"])
        lines.append(f"  assumption-qualified claims: {joined}")
    lines.append("")

    lines.append("CLAIMS")
    if not content["assessments"]:
        lines.append("  (none evaluable)")
    for a in content["assessments"]:
        tol = f", tol={a['tolerance']}" if a.get("tolerance") else ""
        method = f" via {a['method']}" if a.get("method") else ""
        qualified = " [assumption-qualified]" if a.get("assumption_qualified") else ""
        # Surface a non-default reproduction level (e.g. estimation) so an estimation verdict is
        # visibly distinct from a simulation one, never conflated (spec: simulation-oracle —
        # "Estimation reproduction is a distinct verdict").
        level = f" [{a['level']}]" if a.get("level") and a["level"] != "simulation" else ""
        lines.append(
            f"  [{a['claim_id']}] {a['quantity']}: {a['verdict']}{level}{qualified}"
            f" (source {a['source_location']}{method}{tol})"
        )
    lines.append("")

    if content["assumptions"]:
        lines.append("ASSUMPTIONS (supplied by Reprolith, not the paper)")
        for asm in content["assumptions"]:
            flag = " [load-bearing]" if asm.get("load_bearing") else ""
            pending = asm.get("verification_item")
            unverified = f" [unverified — pending review: {pending}]" if pending else ""
            lines.append(f"  [{asm['id']}] {asm['description']} -> {asm['chosen']}{flag}{unverified}")
            lines.append(f"      basis: {asm['basis']} (attributed to {asm['attributed_to']})")
        lines.append("")

    if m["gaps"]:
        lines.append("WHAT WAS MISSING")
        for g in m["gaps"]:
            where = f"[{g['claim_id']}] {g['quantity']}: " if g["claim_id"] else ""
            lines.append(f"  {where}{g['needs']}")
        lines.append("")

    lines.append("SCOPE")
    lines.append(f"  {content['scope']['human']}")

    return "\n".join(lines)


__all__ = ["claim_counts", "gap_items", "render_badge", "render_human", "render_machine"]
