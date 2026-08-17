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

import html
from collections.abc import Iterable
from typing import Any

from .enums import ReproductionLevel, Verdict
from .model import Certificate, RunMetadata


def claim_counts(cert: Certificate) -> dict[str, int]:
    """The number of claims at each verdict, every verdict present (zero if unused)."""
    counts = {v.value: 0 for v in Verdict}
    for a in cert.assessments:
        counts[a.verdict.value] += 1
    return counts


def estimation_claims(cert: Certificate) -> list[str]:
    """The claims reproduced at estimation level rather than by simulation.

    Simulation reproduction — run the described model, check the shown output — is the primary
    target; an estimation reproduction re-fits parameters from data and is a weaker result about a
    different question. The spec requires the two never be conflated, so every surface that
    summarizes a certificate reads this one list rather than deciding for itself.
    """
    return [a.claim_id for a in cert.assessments if a.level is ReproductionLevel.ESTIMATION]


def gap_items(cert: Certificate) -> list[dict[str, Any]]:
    """The structured "what was missing" report for anything short of full reproduction.

    One item per claim that did not cleanly reproduce, each tying the shortfall to the
    claim it blocks — its identifier, quantity, verdict, source location, and the specific
    thing needed to close it (the implicated root cause, else the observed discrepancy, else
    a plain statement that evaluable output or reference data is required).

    A claim that reproduced *only because Reprolith supplied an assumption* did not cleanly
    reproduce either, so it appears here too — otherwise this report would call an
    assumption-qualified pass "nothing missing" while the overall verdict is
    ``partially-reproduced``. Each load-bearing assumption is listed as its own item naming the
    exact condition the paper left out, so the honesty payload always states *why* a clean pass
    was withheld. Certificate-level gap notes follow, not tied to a single claim.
    """
    items: list[dict[str, Any]] = []
    for a in cert.assessments:
        if a.verdict is Verdict.REPRODUCED:
            if a.assumption_qualified:
                items.append(
                    {
                        "claim_id": a.claim_id,
                        "quantity": a.quantity,
                        "verdict": a.verdict.value,
                        "source_location": a.source_location,
                        "needs": "reproduced only under an assumption Reprolith supplied, not a clean pass",
                    }
                )
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
    for claim_id in estimation_claims(cert):
        a = next(x for x in cert.assessments if x.claim_id == claim_id)
        if a.verdict is not Verdict.REPRODUCED:
            continue  # already listed above with its own shortfall
        items.append(
            {
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "verdict": a.verdict.value,
                "source_location": a.source_location,
                "needs": "reproduced at estimation level (parameters re-fit from data); "
                         "simulation reproduction of this claim was not demonstrated",
            }
        )
    for asm in cert.assumptions:
        # An assumption still awaiting expert confirmation withholds the clean pass exactly as a
        # load-bearing one does (derive_overall consults both), so the report that exists to say
        # why the pass was withheld has to name it too.
        if not asm.load_bearing and not asm.verification_item:
            continue
        pending = (
            f" — awaiting expert confirmation ({asm.verification_item})"
            if asm.verification_item
            else ""
        )
        items.append(
            {
                "claim_id": None,
                "quantity": None,
                "verdict": None,
                "source_location": None,
                "needs": f"{asm.description} — Reprolith assumed {asm.chosen} "
                         f"({asm.basis}){pending}",
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
            "estimation_claims": estimation_claims(cert),
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

    The colour reflects the overall verdict and reserves green for an unqualified *simulation*
    reproduction, so neither a qualified result nor one obtained by re-fitting parameters can
    render as a clean success. The label says "reproduced (estimation)" when any claim was judged
    at estimation level, because a green badge reading "reproduced" is exactly the conflation the
    two levels exist to prevent. The scope statement travels in the badge's title and cannot be
    emptied.

    The scope text comes from the certificate, which may have been contributed by someone else,
    so it is escaped: this badge is embedded raw into the public registry page, and an SVG
    ``<title>`` is not a text-only element to an HTML parser.
    """
    verdict = cert.overall.value
    color = _BADGE_COLOR[verdict]
    if estimation_claims(cert):
        verdict = f"{verdict} (estimation)"
        color = _BADGE_COLOR["partially-reproduced"]  # never green: no simulation reproduction shown
    label = "reprolith"
    label_w = len(label) * 7 + 10
    value_w = len(verdict) * 7 + 10
    total = label_w + value_w
    scope = html.escape(cert.scope.machine)
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
        if a.get("protocol"):
            # A sampled judgment's number is only re-runnable with the sampling that produced it.
            lines.append(f"      sampling: {a['protocol']}")
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


def _track_record_banner(self_validation: dict[str, Any]) -> str:
    """Render the blind self-validation summary as an HTML banner for the public registry.

    Uses :func:`reprolith.agreement.summarize_report`, the same honesty split the CLI and MCP
    surfaces use, so the browsable credibility number can never disagree with the queried one. An
    abstention (a ``blocked`` verdict) is shown apart from a wrong verdict; no blended rate.
    """
    from .agreement import summarize_report

    by_class = self_validation.get("by_class", {})
    if not by_class:
        return ""
    rows = []
    for label in sorted(by_class):
        s = summarize_report(by_class[label])
        rows.append(
            f"<tr><td>{html.escape(label)}</td><td>{s['matched']}</td>"
            f"<td>{s['abstained']}</td><td>{s['other']}</td><td>{s['total']}</td></tr>"
        )
    o = self_validation.get("overall", {})
    foot = (
        f"<tr class=\"tr-total\"><td>overall</td><td>{o.get('agreements', 0)}</td>"
        f"<td>{o.get('abstentions', 0)}</td><td>{o.get('other_disagreements', 0)}</td>"
        f"<td>{o.get('labelled_entries', 0)}</td></tr>"
    )
    return (
        '<section class="track-record"><h2>Blind self-validation</h2>'
        '<p class="tr-note">How each class’s blind verdicts matched independently-established '
        "ground truth. An <em>abstention</em> (a “blocked” verdict — insufficient "
        "information) is shown apart from a wrong verdict; no single blended rate conflates them.</p>"
        '<p class="tr-note"><strong>What these numbers do and do not establish.</strong> Where a '
        "class’s entries all carry the same expected verdict, “always answer that verdict” would "
        "score the same, so the number is evidence of agreement with an independent "
        "implementation and of abstaining when the evidence is missing — not of telling a "
        "reproducible result from an irreproducible one. The PK/PD label is BioModels’ curation "
        "status, which is also readable from the accession prefix, so read its row the same way. "
        "Each dataset states its own caveat in full.</p>"
        "<table><thead><tr><th>class</th><th>matched</th><th>abstained</th><th>other</th>"
        f"<th>of total</th></tr></thead><tbody>{''.join(rows)}</tbody><tfoot>{foot}</tfoot></table>"
        "</section>"
    )


def render_registry(
    entries: Iterable[tuple[str, Certificate]],
    *,
    title: str = "Reprolith reproduction registry",
    self_validation: dict[str, Any] | None = None,
) -> str:
    """A self-contained, browsable HTML registry of certificates (spec: certificate-publication).

    ``entries`` pairs each certificate with its model class (the class lives on the catalog entry,
    not the certificate). Each card carries the status badge, the per-verdict claim counts, the
    certificate's content digest (its stable identifier — the string every read surface takes), and
    the honesty payload: what was missing, and each load-bearing assumption Reprolith had to supply.
    A published qualified result that showed only a badge and a title would put the reader one step
    away from the reason it was qualified, which is the one thing the registry exists to carry.
    Grouped so a non-expert can navigate it, and the scope statement travels inescapably. Verdicts keep the badge colours' honesty rule — a qualified or partial
    result is never rendered green — so no browsing path collapses a qualified result into a clean
    success ("No silent green"). Filter controls for model class and overall verdict are inline and
    degrade gracefully: with scripting off, every entry stays visible. (Source is shown per entry;
    freshness needs run timestamps the certificate content omits, so it is not a filter here.)
    """
    from .canonical import content_hash
    from .scope import Scope

    rows = list(entries)
    # The page-wide disclaimer is the scope statement itself, not whichever certificate happens
    # to sort first: one contributed file must not be able to reword the disclaimer every other
    # entry on the page is published under.
    scope_human = Scope().human
    classes = sorted({model_class for model_class, _ in rows})
    verdicts = ["reproduced", "partially-reproduced", "not-reproduced", "blocked"]

    cards: list[str] = []
    for model_class, cert in sorted(rows, key=lambda r: (r[0], r[1].overall.value, r[1].paper.title)):
        counts = claim_counts(cert)
        verdict = cert.overall.value
        ids = ", ".join(
            f"{k}={cert.paper.to_dict()[k]}"
            for k in ("doi", "pubmed_id")
            if cert.paper.to_dict().get(k)
        )
        count_line = ", ".join(f"{k}={counts[k]}" for k in counts if counts[k])
        digest = content_hash(cert.content())
        gaps = "".join(
            f"<li>{html.escape(item['needs'])}</li>" for item in gap_items(cert)
        )
        gap_block = (
            f'<details class="gaps"><summary>what was missing '
            f'({len(gap_items(cert))})</summary><ul>{gaps}</ul></details>'
            if gaps
            else ""
        )
        cards.append(
            f'<article class="entry" data-class="{html.escape(model_class)}" '
            f'data-verdict="{verdict}">'
            f'<div class="badge">{render_badge(cert)}</div>'
            f'<h3>{html.escape(cert.paper.title)}</h3>'
            f'<p class="meta">{html.escape(model_class)}'
            f'{" · " + html.escape(ids) if ids else ""}</p>'
            f'<p class="verdict v-{verdict}">{verdict}</p>'
            f'<p class="counts">{html.escape(count_line) if count_line else "no evaluable claims"}</p>'
            f'{gap_block}'
            f'<p class="digest"><code>{html.escape(digest)}</code></p>'
            f"</article>"
        )

    def buttons(name: str, values: Iterable[str]) -> str:
        chips = "".join(
            f'<button data-filter="{name}" data-value="{html.escape(v)}">{html.escape(v)}</button>'
            for v in values
        )
        return f'<div class="filter" data-group="{name}">' \
               f'<button data-filter="{name}" data-value="all" class="on">all</button>{chips}</div>'

    style = (
        "body{font-family:system-ui,sans-serif;margin:2rem;color:#222}"
        "h1{margin-bottom:.25rem}.disclaimer{color:#555;max-width:48rem}"
        ".filters{margin:1rem 0}.filter{display:inline-block;margin-right:1rem}"
        ".filter button{margin:.1rem;padding:.2rem .5rem;cursor:pointer}"
        ".filter button.on{background:#222;color:#fff}"
        ".entry{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:.5rem 0}"
        ".entry h3{margin:.4rem 0}.meta{color:#666;font-size:.9rem;margin:.2rem 0}"
        ".verdict{font-weight:600}.v-reproduced{color:#3a3}.v-partially-reproduced{color:#a80}"
        ".v-not-reproduced{color:#c33}.v-blocked{color:#777}.counts{color:#444;font-size:.9rem}"
        ".gaps{margin:.4rem 0;font-size:.9rem}.gaps summary{cursor:pointer;color:#a80}"
        ".gaps ul{margin:.3rem 0 .3rem 1.2rem;color:#444}"
        ".digest{margin:.3rem 0 0;font-size:.75rem;color:#888;word-break:break-all}"
        ".track-record{margin:1rem 0;padding:1rem;border:1px solid #ddd;border-radius:8px;background:#fafafa}"
        ".track-record h2{margin:.2rem 0}.tr-note{color:#555;max-width:48rem;font-size:.9rem}"
        ".track-record table{border-collapse:collapse;margin-top:.5rem}"
        ".track-record th,.track-record td{padding:.2rem .8rem;text-align:right;border-bottom:1px solid #eee}"
        ".track-record th:first-child,.track-record td:first-child{text-align:left}"
        ".track-record .tr-total{font-weight:600}"
    )
    script = (
        "const st={class:'all',verdict:'all'};"
        "document.querySelectorAll('.filter button').forEach(function(b){"
        "b.onclick=function(){"
        "st[b.dataset.filter]=b.dataset.value;"
        "b.parentNode.querySelectorAll('button').forEach(function(x){x.classList.remove('on');});"
        "b.classList.add('on');"
        "document.querySelectorAll('.entry').forEach(function(e){"
        "const ok=(st.class==='all'||e.dataset.class===st.class)&&"
        "(st.verdict==='all'||e.dataset.verdict===st.verdict);"
        "e.style.display=ok?'':'none';});};});"
    )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{style}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f'<p class="disclaimer">{html.escape(scope_human)}</p>'
        f"{_track_record_banner(self_validation) if self_validation else ''}"
        '<div class="filters">'
        f"{buttons('class', classes)}{buttons('verdict', verdicts)}</div>"
        f'<main>{"".join(cards) if cards else "<p>No certificates yet.</p>"}</main>'
        f"<script>{script}</script></body></html>"
    )


__all__ = [
    "claim_counts",
    "gap_items",
    "render_badge",
    "render_human",
    "render_machine",
    "render_registry",
]
