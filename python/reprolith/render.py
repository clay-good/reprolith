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
from .oracle import ReferenceKind


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


def is_figure_read(reference_kind: object) -> bool:
    """Whether a reference kind means the value was read off a picture.

    One predicate, because two surfaces answer this question from two shapes: the human render
    walks :func:`render_machine`'s dicts by design — so the human and machine forms cannot
    disagree — and :func:`figure_read_claims` walks the certificate's own assessments. Both used
    to spell the comparison out, one against a bare string literal, and a rename of the enum
    member would have left the render silently marking nothing.
    """
    return reference_kind == ReferenceKind.DIGITIZED_FIGURE.value


def figure_read_claims(cert: Certificate) -> list[str]:
    """The claims judged against values read off a picture rather than against published numbers.

    The reference counterpart of :func:`estimation_claims`, and it exists for the same reason: a
    figure reading is a weaker result about the same question, so a surface summarizing a
    certificate should read a list rather than decide for itself what ``digitized-figure`` implies.
    The human render marks these ``[figure-reading]``; the author-facing report had no notion of
    them at all, and called a pass judged in a band twice as wide a clean pass with nothing said
    about it.
    """
    return [a.claim_id for a in cert.assessments if is_figure_read(a.reference_kind)]


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
        # `implicated` and `fault_hypothesis` are causes too, and falling straight through to the
        # abstention sentence told a reader a claim had no evaluable output when the certificate
        # says it was evaluated and missed.
        #
        # Every part that is present, not the first one. `next(...)` took whichever came first and
        # dropped the rest, which was invisible while every shortfall was `uncategorized` against
        # the claim's own quantity — and became the worst line in the document the moment a real
        # cause existed. The twice-daily entry's brain claims rendered as the bare token
        # `apparent-manuscript-error`: this engine's most serious statement, that a named paper's
        # table is wrong, printed beside that paper's DOI with none of the evidence for it and no
        # sign that `Fault` is, in its own words, "always a hypothesis, never a proven cause".
        # `presubmission._claim_issue_and_fix` was already carrying the evidence on the
        # neighbouring surface, which is what the comment here used to claim and the code did not.
        measured = (a.discrepancy or "").strip()
        cause = ", ".join(
            part for part in ((a.root_cause or "").strip(), (a.implicated or "").strip()) if part
        )
        hypothesis = (a.fault_hypothesis or "").strip()
        stated = "; ".join(
            part
            for part in (
                measured,
                cause,
                f"fault hypothesis: {hypothesis}" if hypothesis else "",
            )
            if part
        )
        # Stripped, and for every verdict this renders: `require_stated_cause` only strips for
        # partial and failed, so a whitespace root cause on a not-evaluable claim printed as "   ".
        needs = stated or "evaluable output or reference data for this claim"
        items.append(
            {
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "verdict": a.verdict.value,
                "source_location": a.source_location,
                "needs": needs,
            }
        )
    for a in cert.assessments:
        # Walked directly rather than resolved by id. Ids are unique — `build_certificate` and the
        # load path both refuse a repeat — but a lookup that assumes it silently answers the first
        # match, and this loop is the one place a claim's row is fetched by id rather than iterated.
        if a.level is not ReproductionLevel.ESTIMATION:
            continue
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
            # The counterpart, and it belongs in the same block for the same reason: a script
            # reading this summary should not have to walk the assessments and decide for itself
            # what `digitized-figure` implies. Emitted always, so a consumer can tell "none read
            # off a picture" from "this certificate predates the field".
            "figure_read_claims": figure_read_claims(cert),
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
        # A cap, not a repaint — the same correction the gap branch below already carries. Setting
        # the amber unconditionally *raised* the two verdicts beneath it: a failed estimation claim
        # rendered amber instead of red, and an abstained one amber instead of grey, so for any
        # estimation-level certificate red and grey were unreachable. The spec asks that an
        # estimation result never be green and never read as a clean pass; it does not authorize
        # promoting a failure. `judge_estimation`'s own abstention branch sets this level, so this
        # is a live path rather than a hand-built one.
        if color == _BADGE_COLOR["reproduced"]:
            color = _BADGE_COLOR["partially-reproduced"]
    if cert.gap_report:
        # The overall verdict is derived from the claims alone, so a result that went missing
        # before it ever became a claim cannot lower it. This badge is the most compressed
        # rendering there is — one word and one colour — and it is the one a reader meets first,
        # so it must not show a clean green pass over a non-empty "what was missing" report.
        #
        # Only ever a downgrade. Setting the amber unconditionally *upgraded* the two verdicts
        # below it — and `run.blocked_certificate` always carries a gap report, so every abstention
        # the pipeline produces (30 of the 31 PK/PD entries) turned from grey to amber, and a
        # not-reproduced result with a gap turned from red to amber. Grey became unreachable.
        verdict = f"{verdict} (gaps)"
        if color == _BADGE_COLOR["reproduced"]:
            color = _BADGE_COLOR["partially-reproduced"]
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
    if content.get("supersedes"):
        # Part of the machine content, so the two renderings have to agree on it: a certificate
        # that replaced an earlier one says which, or a reader comparing the two cannot tell which
        # is the correction.
        lines.append(f"Supersedes: {content['supersedes']}")
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
        # A value read off a figure is a measurement of a picture, and the certificate is judged
        # against it in a band twice as wide as a printed number's. The machine form has carried
        # `reference_kind` since the beginning; the human form showed only the widened tolerance,
        # which a reader can see is 0.20 and cannot see is 0.20 *because* the reference is a
        # reading. Marked like the other qualifications, and only when it applies, so no
        # certificate already published renders differently.
        reading = " [figure-reading]" if is_figure_read(a.get("reference_kind")) else ""
        lines.append(
            f"  [{a['claim_id']}] {a['quantity']}: {a['verdict']}{level}{qualified}{reading}"
            f" (source {a['source_location']}{method}{tol})"
        )
        if a.get("protocol"):
            # A judgment's number is only re-runnable with the run that produced it — the sampling
            # for an ensemble, the window and sample count for a time course.
            lines.append(f"      protocol: {a['protocol']}")
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


#: What an author can do with this page. The registry publishes verdicts on other people's work,
#: which is no use at all to the person deciding what to ship — and the check that is use to them
#: needs no submission, no queue, and no certificate. It is stated where they will actually see it,
#: and stated exactly: it reads their files and reaches no verdict, so nothing here can be read as
#: a certificate obtained by running a command.
_AUTHOR_BANNER = (
    '<section class="authors"><h2>Writing one of these? Check it first</h2>'
    "<p>Before you submit, you can see what a reproducer would find in your own archive — or in "
    "the model and simulation document as they sit in your directory. It reads your files, runs "
    "no model, reaches no verdict, and issues no certificate.</p>"
    "<pre><code>pip install reprolith\n"
    "reprolith archive-check paper.omex --claims my_claims.json\n"
    "reprolith archive-check --sedml paper.sedml --model paper.xml --claims my_claims.json"
    "</code></pre>"
    "<p>With <code>--claims</code> — the results your paper reports — it also answers the question "
    "nothing in your archive can: does the experiment you ship actually run them? Every file can "
    "be valid, and the run can complete, while producing a neighbouring arm nobody published.</p>"
    "</section>"
)


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
    # Coerced to int like the per-class row above, not interpolated raw: these are the only four
    # values on the page that reach the HTML without passing through escaping, and a count is a
    # number or it is nothing.
    totals = [int(o.get(key, 0)) for key in
              ("agreements", "abstentions", "other_disagreements", "labelled_entries")]
    foot = (
        '<tr class="tr-total"><td>overall</td>'
        + "".join(f"<td>{value}</td>" for value in totals)
        + "</tr>"
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
    # A certificate another one replaced must not read as a current result: the registry holds both
    # records, and two equal cards — the withdrawn one still wearing its badge — is exactly how a
    # corrected verdict keeps being cited. The replacements name what they replaced, so the
    # superseded set is derivable from the page's own contents.
    superseded = {
        cert.supersedes: content_hash(cert.content())
        for _, cert in rows
        if cert.supersedes is not None
    }
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
        replaced_by = superseded.get(digest)
        superseded_block = (
            f'<p class="superseded">superseded — a later certificate replaced this one: '
            f'<code>{html.escape(replaced_by)}</code></p>'
            if replaced_by
            else ""
        )
        cards.append(
            f'<article class="entry{" superseded" if replaced_by else ""}" '
            f'data-class="{html.escape(model_class)}" '
            f'data-verdict="{verdict}" data-superseded="{"yes" if replaced_by else "no"}">'
            f'{superseded_block}'
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
        ".entry.superseded{border-color:#c33;background:#fff8f8;opacity:.85}"
        ".superseded{margin:0 0 .4rem;color:#c33;font-weight:600;font-size:.9rem}"
        ".superseded code{font-weight:400;word-break:break-all}"
        ".track-record{margin:1rem 0;padding:1rem;border:1px solid #ddd;border-radius:8px;background:#fafafa}"
        ".track-record h2{margin:.2rem 0}.tr-note{color:#555;max-width:48rem;font-size:.9rem}"
        ".track-record table{border-collapse:collapse;margin-top:.5rem}"
        ".track-record th,.track-record td{padding:.2rem .8rem;text-align:right;border-bottom:1px solid #eee}"
        ".track-record th:first-child,.track-record td:first-child{text-align:left}"
        ".track-record .tr-total{font-weight:600}"
        ".authors{margin:1rem 0;padding:1rem;border:1px solid #ddd;border-radius:8px}"
        ".authors h2{margin:.2rem 0}.authors p{color:#555;max-width:48rem;font-size:.9rem}"
        ".authors pre{background:#f6f6f6;padding:.6rem;border-radius:6px;overflow-x:auto;"
        "font-size:.85rem}"
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
        f"{_AUTHOR_BANNER}"
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
