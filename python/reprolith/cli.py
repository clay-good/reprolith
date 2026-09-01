"""The human-facing command-line surface over the read-only query model (spec: ``human-cli``).

Reprolith has two surfaces over one core: an MCP server for agents
(:mod:`reprolith.mcp_server`) and this CLI for humans at a terminal. Both load the same
persisted repository through :func:`reprolith.mcp_server.load_repository` and read it through
the same :class:`~reprolith.query.ReprolithQuery`, so the terminal view and the agent view can
never disagree ("Parity with the human surface"). The CLI computes no verdict of its own; it
formats what the query returns.

Every command reads; one writes. ``export`` is the exception and the only one — it turns a
published reconstruction bundle into a COMBINE archive on disk, because a reconstruction nobody
can run without Reprolith is not a published artifact. It computes nothing: the bundle it exports
is the one the query returns, and the file it writes is what :func:`reprolith.build_bundle_sedml`
makes of it. Structured data prints as indented, sorted JSON with ``--json``
(the exact object an agent gets over MCP); without it, the human-friendly formatters below
render the same data as legible text. A certificate renders through
:func:`reprolith.render.render_human`, the canonical plain-text certificate, so the terminal
never shows a form that could disagree with the published one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from .certify import Claim
from .claim_candidates import propose_claims
from .claims_template import claims_template, unfilled_claims
from .digitization import (
    AmbiguousPanel,
    DigitizedSeries,
    figure_template,
    pairing_faults,
    panel_faults,
    read_digitized_figure,
    series_resolution,
    unfilled_figure,
    window_faults,
)
from .export import build_bundle_sedml, build_omex_archive
from .manuscript_values import (
    check_claim_values,
    check_parameter_values,
    disagreeing_parameters,
    unsupported_claims,
)
from .mcp_server import default_data_dir, load_repository
from .model import RunMetadata
from .persistence import bundle_from_dict
from .presubmission import (
    archive_report,
    pair_report,
    render_archive_human,
    render_pair_human,
)
from .query import ReprolithQuery
from .render import render_human

# render_human derives its text from the certificate content and never reads the run block, so a
# placeholder is correct here: run metadata is deliberately excluded from stored content (it is not
# part of the deterministic certificate), and nothing in the human rendering depends on it.
_NO_RUN = RunMetadata(created_at="", actor="", tool_version="")


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _identifier_kwargs(args: argparse.Namespace) -> dict[str, str]:
    """Resolve the positional identifier under the chosen ``--by`` key."""
    key = args.by.replace("-", "_")
    return {key: args.identifier}


def _cmd_catalog(query: ReprolithQuery, args: argparse.Namespace) -> int:
    entries = query.list_catalog()
    if args.model_class is not None:
        entries = [e for e in entries if e["model_class"] == args.model_class]
    if args.state is not None:
        entries = [e for e in entries if e["state"] == args.state]
    if args.json:
        _print_json(entries)
        return 0
    if not entries:
        print("(no matching catalog entries)")
        return 0
    for e in entries:
        ident = e["identifiers"]
        print(f"{ident['accession'] or '-':<18} {e['model_class']:<16} {e['state']:<12} {ident['title']}")
    print(f"\n{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}")
    return 0


def _cmd_backlog(query: ReprolithQuery, args: argparse.Namespace) -> int:
    health = query.backlog_health()
    if args.json:
        _print_json(health)
        return 0
    print(f"Backlog: {health['total']} entries, {health['claimable']} claimable now "
          f"({health['labelled']} labelled, {health['unlabelled']} unlabelled)")
    for heading, key in (("By state", "by_state"), ("By class", "by_class"),
                         ("By difficulty", "by_difficulty")):
        counts = health[key]
        print(f"\n{heading}:")
        for name in sorted(counts):
            print(f"  {name:<18} {counts[name]}")
    return 0


def _cmd_self_validation(query: ReprolithQuery, args: argparse.Namespace) -> int:
    from .agreement import summarize_report

    report = query.self_validation()
    if args.json:
        _print_json(report)
        return 0
    by_class = report["by_class"]
    if not by_class:
        print("(no self-validation reports loaded)")
        return 0
    print("BLIND SELF-VALIDATION (verdicts vs independently-established ground truth)")
    print(f"  {'class':<18} {'matched':>8} {'abstained':>10} {'other':>6}  of total")
    for label in sorted(by_class):
        s = summarize_report(by_class[label])
        print(f"  {label:<18} {s['matched']:>8} {s['abstained']:>10} {s['other']:>6}  / {s['total']}")
    o = report["overall"]
    print(f"\n  overall: {o['agreements']} matched, {o['abstentions']} honest abstentions, "
          f"{o['other_disagreements']} other, over {o['labelled_entries']} labelled entries "
          f"across {o['classes']} classes")
    print("  (an abstention is a 'blocked' verdict — insufficient information — not a wrong verdict)")
    # The number does not travel without what it can establish. The JSON view and the registry
    # banner both carry `label_basis`; a reader at a terminal was seeing six near-perfect class
    # scores with the one line that says what they are not attached to nothing.
    print("\n  WHAT THESE NUMBERS ESTABLISH")
    for label in sorted(by_class):
        print(f"  {label}: {by_class[label]['label_basis']}")
    return 0


def _cmd_status(query: ReprolithQuery, args: argparse.Namespace) -> int:
    view = query.status(**_identifier_kwargs(args))
    if view is None:
        print(f"unknown paper: {args.by}={args.identifier}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(view)
        return 0
    ident = view["identifiers"]
    print(f"{ident['title']}")
    print(f"  accession: {ident['accession'] or '-'}   class: {view['model_class']}   "
          f"state: {view['state']}")
    if view["history"]:
        print("  history:")
        for t in view["history"]:
            print(f"    {t['from_state']} -> {t['to_state']} ({t['reason']})")
            # BLOCKED is the one state that is required to say what it is blocked on, and
            # `reason` is not it — most shipped entries read "blind run". Without this the
            # terminal reader learns that a paper stalled but never what would unstall it,
            # while the JSON an agent receives has carried the answer all along.
            for missing in t["missing_inputs"]:
                print(f"      missing: {missing}")
    certs = view.get("certificates") or []
    if certs:
        print("  certificates:")
        for digest in certs:
            print(f"    {digest}")
    return 0


def _cmd_certificate(query: ReprolithQuery, args: argparse.Namespace) -> int:
    if args.json:
        view = query.certificate(args.digest)
        if view is None:
            print(f"unknown digest: {args.digest}", file=sys.stderr)
            return 1
        _print_json(view)
        return 0
    cert = query.certificate_object(args.digest)  # human rendering needs the object, not the dict view
    if cert is None:
        print(f"unknown digest: {args.digest}", file=sys.stderr)
        return 1
    print(render_human(cert, _NO_RUN))
    # `render_human` is a pure function of one certificate, so it can only name what this one
    # supersedes, never what superseded it. The CLI holds the ledger and already reports the
    # forward link in `--json`; printing it here keeps the terminal from serving a withdrawn
    # certificate as the current answer, the way the registry page already does.
    replacement = query.superseded_by(args.digest)
    if replacement:
        print(f"\nSUPERSEDED — a later certificate replaced this one: {replacement}")
    return 0


def _cmd_verdict(query: ReprolithQuery, args: argparse.Namespace) -> int:
    view = query.verdict(args.digest)
    if view is None:
        print(f"unknown digest: {args.digest}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(view)
        return 0
    print(f"OVERALL: {view['overall']}")
    counts = view["claim_counts"]
    print("  claims by verdict: " + ", ".join(f"{k}={counts[k]}" for k in counts))
    if view["assumption_qualified_claims"]:
        print("  assumption-qualified: " + ", ".join(view["assumption_qualified_claims"]))
    if view["estimation_claims"]:
        # Every other rendering flags it — the badge never goes green, the human render prints
        # [estimation], pre-submission refuses ready-to-submit. This summary read as a clean pass.
        print("  reproduced only at estimation level: " + ", ".join(view["estimation_claims"]))
    for note in view["gap_notes"]:
        # A gap that never became a claim cannot move the overall verdict, so the terminal would
        # otherwise print an unqualified pass over a certificate that names something missing.
        print(f"  what was missing: {note}")
    print(f"  scope: {view['scope']['human']}")
    if view["superseded_by"]:
        # The gap report and the JSON view both carry it; without it here the terminal is the one
        # published surface where a verdict a correction already replaced reads as the current one.
        print(f"  superseded by: {view['superseded_by']}")
    return 0


def _cmd_gaps(query: ReprolithQuery, args: argparse.Namespace) -> int:
    report = query.gaps(args.digest)
    if report is None:
        print(f"unknown digest: {args.digest}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(report)
        return 0
    items = report["gaps"]
    if not items:
        # Falling straight out here was the one published path that printed a result with no scope
        # flag beside it — and "nothing was missing" is exactly the line that must not stand alone
        # when a correction has already replaced the verdict it belongs to.
        print("(no gaps — nothing was missing)")
    else:
        print("WHAT WAS MISSING")
        for g in items:
            where = f"[{g['claim_id']}] {g['quantity']}: " if g["claim_id"] else ""
            print(f"  {where}{g['needs']}")
    print(f"  scope: {report['scope']['human']}")
    if report["superseded_by"]:
        print(f"  superseded by: {report['superseded_by']}")
    return 0


def _cmd_presubmission(query: ReprolithQuery, args: argparse.Namespace) -> int:
    view = query.presubmission(args.digest)
    if view is None:
        print(f"unknown digest: {args.digest}", file=sys.stderr)
        return 1
    _print_json(view)
    return 0


def _cmd_certificates_for(query: ReprolithQuery, args: argparse.Namespace) -> int:
    digests = query.certificates_for(**_identifier_kwargs(args))
    if args.json:
        _print_json(digests)
        return 0
    if not digests:
        # "this paper has no certificate" and "there is no such paper" are different answers, and
        # every other identifier-taking command exits 1 on the second. Only say the first when the
        # paper is actually known.
        if query.status(**_identifier_kwargs(args)) is None:
            print(f"unknown paper: {args.by}={args.identifier}", file=sys.stderr)
            return 1
        print("(no certificates for this paper)")
        return 0
    for d in digests:
        print(d)
    return 0


def _cmd_dossier(query: ReprolithQuery, args: argparse.Namespace) -> int:
    view = query.dossier(args.accession)
    if view is None:
        print(f"no dossier for accession: {args.accession}", file=sys.stderr)
        return 1
    _print_json(view)
    return 0


def _cmd_bundle(query: ReprolithQuery, args: argparse.Namespace) -> int:
    view = query.bundle(args.accession)
    if view is None:
        print(f"no bundle for accession: {args.accession}", file=sys.stderr)
        return 1
    _print_json(view)
    return 0


def _cmd_export(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Write a published reconstruction as a runnable COMBINE archive."""
    view = query.bundle(args.accession)
    if view is None:
        print(f"no bundle for accession: {args.accession}", file=sys.stderr)
        return 1
    bundle = bundle_from_dict(view)

    model_path = Path(args.model)
    try:
        model_sbml = model_path.read_text(encoding="utf-8")
    except OSError as unreadable:
        print(f"cannot read the model: {unreadable}", file=sys.stderr)
        return 1
    # The store records which file a reconstruction was built from, never its bytes, so the model
    # is supplied here — and a bundle exported against a *different* model would produce an archive
    # that runs something the certificate never judged. The recorded name is what says which file
    # that is, so a mismatch is refused rather than exported.
    recorded = PurePosixPath(bundle.model.filename).name if bundle.model else None
    if recorded is not None and recorded != model_path.name:
        print(
            f"the bundle for {args.accession} was built from '{recorded}', not "
            f"'{model_path.name}'; exporting it against another model would package a run the "
            "certificate never judged",
            file=sys.stderr,
        )
        return 1

    location = recorded or model_path.name
    try:
        experiment = build_bundle_sedml(bundle, model_sbml, model_location=location)
        archive = build_omex_archive(model_sbml, experiment.sedml, model_location=location)
    except ValueError as refused:
        print(str(refused), file=sys.stderr)
        return 1

    out = Path(args.out)
    # Whether the path already held something is read before writing, because afterwards it is
    # this archive either way — and the one command that writes should say when it replaced a file
    # rather than leave the person to notice later.
    replaced = out.exists()
    try:
        out.write_bytes(archive)
    except OSError as unwritable:
        # A directory, a path whose parent does not exist, a read-only location: ordinary mistakes
        # for the only command here that writes, and a traceback is not an answer to any of them.
        print(f"cannot write the archive: {unwritable}", file=sys.stderr)
        return 1
    if args.json:
        _print_json({
            "archive": str(out),
            "bytes": len(archive),
            "replaced_existing_file": replaced,
            "expressed": list(experiment.expressed),
            "unexpressed": list(experiment.unexpressed),
        })
        return 0
    print(f"wrote {out} ({len(archive)} bytes)" + (", replacing what was there" if replaced else ""))
    print(f"claims expressed: {', '.join(experiment.expressed)}")
    for line in experiment.unexpressed:
        # Printed, never swallowed: an archive short of a claim reads as a reconstruction that
        # never had one, and the terminal is where the person exporting it finds out.
        print(f"not expressed: {line}")
    return 0


def _claim_records(path: Path, accession: str | None) -> list[dict[str, Any]]:
    """The claims file's raw records, before they become :class:`Claim` objects.

    The value check reads records rather than claims: an unfilled one has no ``reported`` and
    would be refused on the way to a ``Claim``, and "this template is not filled in yet" is
    something the check should report rather than fail on.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        entries = data["entries"]
        if accession is None:
            if len(entries) != 1:
                raise ValueError(
                    "this claims file holds several papers; name one with --accession "
                    f"({', '.join(sorted(entries))})"
                )
            accession = next(iter(entries))
        if accession not in entries:
            raise ValueError(
                f"no claims for {accession!r} in this file ({', '.join(sorted(entries))})"
            )
        records = _records_of(entries[accession])
    elif isinstance(data, dict):
        records = _records_of(data)
    else:
        records = data
    return list(records)


def _records_of(holder: dict[str, Any]) -> list[dict[str, Any]]:
    """The claim records in an object, under either key a Reprolith file uses.

    ``claims-propose`` writes them under ``candidates``, deliberately: a number a table prints is
    not yet a claim. Both keys are read here so the two commands compose without a rename, and an
    unedited candidates file reaching a check that needs real claims is refused for the reason
    that actually applies — no model output named — rather than for the key it is stored under.
    """
    for key in ("claims", "candidates", "parameters"):
        if key in holder:
            return list(holder[key])
    raise ValueError(
        "this file holds no claims: expected a 'claims' list (or 'candidates', as "
        f"claims-propose writes, or 'parameters'), and it has {', '.join(sorted(holder)) or 'nothing'}"
    )


def _load_claims(path: Path, accession: str | None) -> list[Claim]:
    """The paper's own claims, read from a claims file.

    Three shapes are accepted, because they are the three an author plausibly has: a bare list of
    claim records, an object with a ``claims`` list, and the shape this repository's own
    ``datasets/pkpd_claims.json`` uses — ``entries`` keyed by accession, which needs
    ``--accession`` unless it holds exactly one.
    """
    records = _claim_records(path, accession)
    blanks = unfilled_claims(records)
    if blanks:
        # A template passed in unfilled is the ordinary mistake, and it used to arrive as a
        # TypeError from float(None) inside Claim.from_record. Every blank is named at once, so
        # one run says everything there is to write.
        raise ValueError(
            "this claims file still has the blanks a template leaves for you:\n  - "
            + "\n  - ".join(blanks)
        )
    return [Claim.from_record(record) for record in records]


def _read_pair(args: argparse.Namespace) -> tuple[str, str, dict[str, str]]:
    """The document, the model, and the data files the document names, read from beside it."""
    from .sedml import sedml_data_sources

    document, model = Path(args.sedml), Path(args.model)
    sedml = document.read_text(encoding="utf-8")
    data: dict[str, str] = {}
    for source in sedml_data_sources(sedml):
        beside = document.parent / source
        if beside.is_file():
            # Read from where the document says it is, exactly as a reader would. A source the
            # author does not have is left out, and the check reports it as missing values.
            data[source] = beside.read_text(encoding="utf-8")
    return sedml, model.read_text(encoding="utf-8"), data


def _cmd_claims_check(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Check a claims file's reported values against the tables the paper prints."""
    try:
        records = _claim_records(Path(args.claims), args.accession)
        tables = json.loads(Path(args.tables).read_text(encoding="utf-8"))
    except OSError as unreadable:
        print(f"cannot read the claims: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as unusable:
        print(f"cannot read the claims: {unusable}", file=sys.stderr)
        return 1
    rows = tables.get("tables", tables) if isinstance(tables, dict) else {}
    if not isinstance(rows, dict) or not rows:
        print(
            "the tables file holds no tables: expected {'Table 6': {'rows': [[...]]}}, or the "
            "shape datasets/manuscripts/ uses, which nests that under 'tables'",
            file=sys.stderr,
        )
        return 1

    checks = check_claim_values(records, rows)
    if args.json:
        _print_json({"checks": [c.to_dict() for c in checks]})
    else:
        print(f"CLAIMS CHECKED AGAINST {len(rows)} TABLE(S): {', '.join(sorted(rows))}")
        for check in checks:
            mark = {True: "ok", False: "NOT FOUND", None: "not checked"}[check.found]
            print(f"  [{check.claim_id}] {mark}: {check.detail}")
        unchecked = [c for c in checks if c.found is None]
        if unchecked:
            # Never folded in with the failures: a value read from a figure panel or a sentence is
            # not a defect, and an absence of evidence is not evidence of absence.
            print(f"  ({len(unchecked)} claim(s) were not checked — see the reason on each)")
    # Non-zero only for a value the cited table does not print. An unchecked claim is not a
    # finding, so it must not fail a pre-submission hook.
    return 1 if unsupported_claims(checks) else 0


def _cmd_params_check(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Check a model's declared parameter values against the ones the paper reports for them."""
    try:
        records = _claim_records(Path(args.parameters), args.accession)
        model = Path(args.model).read_text(encoding="utf-8")
    except OSError as unreadable:
        print(f"cannot read the parameters: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as unusable:
        print(f"cannot read the parameters: {unusable}", file=sys.stderr)
        return 1
    try:
        checks = check_parameter_values(model, records)
    except ValueError as unreadable:
        print(f"cannot read the model: {unreadable}", file=sys.stderr)
        return 1

    if args.json:
        _print_json({"checks": [c.to_dict() for c in checks]})
    else:
        print(f"{len(checks)} PARAMETER(S) CHECKED AGAINST {Path(args.model).name}")
        for check in checks:
            mark = {True: "ok", False: "MISMATCH", None: "not compared"}[check.agrees]
            print(f"  [{check.parameter}] {mark}: {check.detail}")
        uncompared = [c for c in checks if c.agrees is None]
        if uncompared:
            # Never folded in with the mismatches, for the reason claims-check gives: a value that
            # could not be compared is not a value that is wrong.
            print(f"  ({len(uncompared)} parameter(s) were not compared — see the reason on each)")
    return 1 if disagreeing_parameters(checks) else 0


def _cmd_claims_propose(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Propose candidate claims from the tables the paper prints."""
    try:
        loaded = json.loads(Path(args.tables).read_text(encoding="utf-8"))
    except OSError as unreadable:
        print(f"cannot read the tables: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError) as unusable:
        print(f"cannot read the tables: {unusable}", file=sys.stderr)
        return 1
    tables = loaded.get("tables", loaded) if isinstance(loaded, dict) else {}
    if not isinstance(tables, dict) or not tables:
        print(
            "the tables file holds no tables: expected {'Table 6': {'rows': [[...]]}}, or the "
            "shape datasets/manuscripts/ uses, which nests that under 'tables'",
            file=sys.stderr,
        )
        return 1

    proposed = propose_claims(tables, accession=args.accession)
    rendered = json.dumps(proposed, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(rendered, end="")
        return 0
    try:
        Path(args.out).write_text(rendered, encoding="utf-8")
    except OSError as unwritable:
        print(f"cannot write the candidates: {unwritable}", file=sys.stderr)
        return 1
    body = proposed["entries"][args.accession] if args.accession is not None else proposed
    print(f"wrote {args.out}")
    print(f"  {len(body['candidates'])} candidate(s) from {', '.join(body['tables_read'])}")
    for note in body["notes"]:
        print(f"  note: {note}")
    return 0


#: The widest gap, as a fraction of the span, at which a reading is coarse enough to be worth
#: saying so. Not invented here: five evenly spaced points span 25% each and a flawless five-point
#: reading of an oral PK curve already exceeds the whole pass budget, while ten points span 11% and
#: cost 0.09 of it. Between the two measurements, so it fires on the reading that was measured to
#: be too coarse for a curved shape and not on the one that was not.
_COARSE_READING = 0.20


def _write_every_panel(document: str, out_dir: Path) -> int:
    """One template per panel the document plots, so a four-panel paper is one command.

    Still one file per panel — the boundary is the point, not the number of invocations. Each is
    named for the plot it reads, since that is the only name both files agree on.
    """
    from .sedml import enumerate_sedml_panels

    panels = enumerate_sedml_panels(document)
    if not panels:
        print(
            "this document plots nothing, so it states no curve to read off a figure",
            file=sys.stderr,
        )
        return 1
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as unwritable:
        print(f"cannot write the templates: {unwritable}", file=sys.stderr)
        return 1
    for panel in panels:
        template = figure_template(document, panel=panel.plot_id)
        path = out_dir / f"{panel.plot_id}.json"
        # A replaced file is said, not silently overwritten: a curator who has already filled one
        # in would otherwise lose the reading and see a success line.
        replaced = " (replaced)" if path.exists() else ""
        try:
            path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError as unwritable:
            print(f"cannot write the templates: {unwritable}", file=sys.stderr)
            return 1
        print(f"wrote {path}{replaced}")
        print(f"  {panel.label}: {len(template['series'])} curve(s) to read off your figure")
    print("  one file per panel: each states its own axes, and every reading in it was read "
          "off them")
    return 0


def _cmd_figure_template(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Write the digitization file, with the one part of it nobody can guess filled in."""
    if (args.archive is None) == (args.sedml is None):
        print(
            "give either an archive or --sedml: the curves to read come from your simulation "
            "document, whether or not it is packaged",
            file=sys.stderr,
        )
        return 1
    try:
        if args.archive is not None:
            from .omex import archive_documents

            document, _ = archive_documents(Path(args.archive).read_bytes())
            if document is None:
                # Not a defect in the archive, and not something to write a file about: which
                # curves a paper shows is the document's statement, and there is no document.
                print(
                    "this archive ships no simulation document, so nothing in it says which "
                    "curves your paper shows; there is no reading to pair to a claim",
                    file=sys.stderr,
                )
                return 1
        else:
            document = Path(args.sedml).read_text(encoding="utf-8")
        if args.out_dir is not None:
            return _write_every_panel(document, Path(args.out_dir))
        template = figure_template(document, panel=args.plot)
    except AmbiguousPanel as ambiguous:
        # Not a defect in the document: a paper with two panels is a paper with two panels, and
        # what is missing is the curator's statement of which one they read.
        print(str(ambiguous), file=sys.stderr)
        return 1
    except OSError as unreadable:
        print(f"cannot read the document: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError) as unusable:
        print(f"cannot read the document: {unusable}", file=sys.stderr)
        return 1

    rendered = json.dumps(template, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(rendered, end="")
        return 0
    try:
        Path(args.out).write_text(rendered, encoding="utf-8")
    except OSError as unwritable:
        print(f"cannot write the template: {unwritable}", file=sys.stderr)
        return 1
    print(f"wrote {args.out}")
    print(f"  {len(template['series'])} curve(s) to read off your figure")
    for note in template["notes"]:
        print(f"  note: {note}")
    print("  the pairing is filled in; the figure, the tool, both axes and every point are yours")
    return 0


def _document_claims(
    args: argparse.Namespace,
) -> tuple[tuple[Any, ...], tuple[tuple[float, float, int], ...], tuple[Any, ...]] | None:
    """What the given document says: its curves, the runs it states, and its panels."""
    if args.archive is None and args.sedml is None:
        return None
    from .sedml import enumerate_sedml_claims, enumerate_sedml_panels, parse_sedml_recipes

    if args.archive is not None:
        from .omex import archive_documents

        document, _ = archive_documents(Path(args.archive).read_bytes())
        if document is None:
            raise ValueError(
                "this archive ships no simulation document, so nothing in it says which curves "
                "your paper shows; there is no pairing to check"
            )
    else:
        document = Path(args.sedml).read_text(encoding="utf-8")
    # `parse_sedml_recipes` drops any time course it cannot run verbatim, so an empty set of
    # runs is "this document states no run to judge a curve over" and not "the run is 0-0".
    runs = tuple(dict.fromkeys(
        (recipe.output_start, recipe.duration, recipe.steps)
        for recipe in parse_sedml_recipes(document)
    ))
    return tuple(enumerate_sedml_claims(document)), runs, enumerate_sedml_panels(document)


def _cmd_figure_check(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Read a curator's figure digitization and say whether it is usable as a reference."""
    if args.archive is not None and args.sedml is not None:
        print(
            "give either an archive or --sedml, not both: the pairing is checked against one "
            "document",
            file=sys.stderr,
        )
        return 1
    series: tuple[DigitizedSeries, ...] = ()
    for path in args.series:
        try:
            text = Path(path).read_text(encoding="utf-8")
            # A template handed straight back is the ordinary mistake, and reading it would refuse
            # on whichever blank it reached first — which says nothing about the other four.
            loaded = json.loads(text)
            blanks = unfilled_figure(loaded) if isinstance(loaded, dict) else ()
            if blanks:
                print(f"{path} has not been filled in yet:", file=sys.stderr)
                for blank in blanks:
                    print(f"  {blank}", file=sys.stderr)
                return 1
            series += read_digitized_figure(text)
        except OSError as unreadable:
            print(f"cannot read the digitization: {unreadable}", file=sys.stderr)
            return 1
        except (UnicodeDecodeError, ValueError) as unusable:
            print(f"cannot read the digitization: {unusable}", file=sys.stderr)
            return 1

    # Without a document there is no pairing to check: the file names claim ids, and whether they
    # are the right ones is a question about the document they were read off, which this command
    # was never given. That is reported below rather than passed over silently.
    try:
        read = _document_claims(args)
    except OSError as unreadable:
        print(f"cannot read the document: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError) as unusable:
        print(f"cannot read the document: {unusable}", file=sys.stderr)
        return 1

    claims, runs, panels = read if read is not None else (None, (), ())
    windows = tuple((start, duration) for start, duration, _steps in runs)
    faults = pairing_faults(claims, series, carrier="your document") if claims is not None else ()
    # One file is one panel: `figure-template` will not write two plots into one file, and a file
    # written by hand or by an older template can still do it. Once the axis ranges are filled in
    # there is nothing left to notice.
    faults += panel_faults(series, panels, carrier="your document")
    # A reading that does not span the run is refused at the join, in Python, long after the
    # curator has finished — and both numbers that say so are on disk while they are still here.
    short = window_faults(series, windows, carrier="your document") if windows else ()
    # A curator reads one panel at a time, so a document whose other curves are unread is the
    # ordinary case and not a fault. It is said, because "checked clean" over one of nine curves
    # reads as nine.
    unread = tuple(
        claim.id for claim in (claims or ())
        if claim.targetable and not claim.reference_data
        and claim.id not in {s.claim_id for s in series}
    )

    plotted = {claim.id: claim.quantity for claim in (claims or ())}
    resolutions = [series_resolution(s) for s in series]
    if args.json:
        _print_json({
            "series": [{**s.to_dict(), "resolution": r} for s, r in zip(series, resolutions)],
            "pairing": None if claims is None else {
                "checked_against": "archive" if args.archive is not None else "sedml",
                "faults": list(faults),
                "curves_not_read": list(unread),
                # The runs the document states, each as [start, end, steps]. The windows the
                # faults are computed against are the first two of each, so they are not repeated.
                "runs": [list(r) for r in runs],
                "window_faults": list(short),
            },
        })
        return 1 if faults or short else 0
    read_from = ", ".join(dict.fromkeys(reading.figure for reading in series))
    print(f"{len(series)} SERIES READ FROM {read_from}, "
          f"DIGITIZED WITH {series[0].digitizer}")
    for reading, resolution in zip(series, resolutions):
        low, high = resolution["span"]
        # The panel is named per series once more than one file is in play: a claim id says
        # nothing about which picture it was read off, and that is the fact a curator checking
        # two panels needs.
        panel = f"{reading.figure} " if len(set(r.figure for r in series)) > 1 else ""
        print(f"  {panel}[{reading.claim_id}] {reading.curve}: {resolution['points']} point(s) "
              f"over {low}-{high} {reading.x_axis.unit}, in {reading.y_axis.unit}")
        # The curve label is the curator's own words for the curve; the quantity is the
        # document's. Printed side by side and never compared: renaming 'MAPK_PP' to 'the upper
        # curve' is ordinary, and a reading of the wrong curve of the right figure passes every
        # check on this page — this is the one place a curator can see it.
        plots = plotted.get(reading.claim_id)
        if plots is not None:
            print(f"      your document plots {plots} there")
        # Reported, never judged: between two read points the reference is the curator's straight
        # line, and how much of the comparison rests on it is a fact they should see rather than a
        # threshold this command invented.
        print(f"      widest gap between readings: {resolution['widest_gap_fraction']:.0%} of the "
              "span, over which the reference is interpolated")
        # Still not a verdict, and no longer a number nobody has a scale for. A flawless five-point
        # reading of an oral PK curve — a 25% gap — misses the curve it was read off by 0.25
        # against a 0.20 pass budget, and a ten-point one by 0.09
        # (tests/test_digitization_interpolation_cost.py). A flat curve read at five points costs
        # nothing, so how curved this one is remains the curator's to weigh.
        if resolution["widest_gap_fraction"] > _COARSE_READING:
            print("      at that spacing a flawless reading of a curved shape can spend the whole "
                  "tolerance on its own straight lines: measured at 0.25 against a 0.20 budget "
                  "for an oral PK curve read at five points, and 0.09 at ten")
        # The thing a curator cannot see in their own file: a curve is judged on the run's own
        # samples, so a reading of three points against a run of a thousand is judged almost
        # entirely against the straight lines between them. Stated, never judged — the wider
        # figure band is what covers it, and how much of it is doing work is theirs to weigh.
        for start, duration, steps in runs:
            if start > min(x for x, _ in reading.points) or duration > max(
                x for x, _ in reading.points
            ):
                continue
            samples = steps + 1
            print(f"      your document samples {start:g}-{duration:g} {reading.x_axis.unit} "
                  f"{samples} times, and this "
                  f"curve was read at {resolution['points']}: the other "
                  f"{samples - resolution['points']} are the straight line between readings")
    if claims is None:
        print("  the claim ids in this file were not checked: no document was given to check "
              "them against (pass the archive, or --sedml)")
    else:
        for fault in faults:
            print(f"  PAIRED WITH THE WRONG CLAIM: {fault}")
        for fault in short:
            print(f"  READ OVER TOO SHORT A WINDOW: {fault}")
        if unread:
            # A document plotting forty curves produces one unreadable line, and a truncation that
            # does not say it truncated reads as "that was all of them".
            shown = ", ".join(unread[:5])
            rest = f", and {len(unread) - 5} more" if len(unread) > 5 else ""
            print(f"  {len(unread)} curve(s) your document plots are not read here, and stay "
                  f"unjudged: {shown}{rest}")
        if not faults and not short:
            print("  every series is paired with a curve your document plots and can carry values")
            if windows:
                print("  and every one of them covers a window your document runs")
    print("  no model was run and no claim was judged: this reads the file, nothing else")
    return 1 if faults or short else 0


def _cmd_claims_template(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Write the claims file the author-facing check needs, from the files the author has."""
    if (args.archive is None) == (args.model is None):
        print(
            "give either an archive or --model (with --sedml, if you have a document): a "
            "template is written for the one model whose results your paper reports",
            file=sys.stderr,
        )
        return 1
    try:
        if args.archive is not None:
            from .omex import archive_documents

            sedml, model = archive_documents(Path(args.archive).read_bytes())
        else:
            model = Path(args.model).read_text(encoding="utf-8")
            sedml = (
                Path(args.sedml).read_text(encoding="utf-8") if args.sedml is not None else None
            )
        template = claims_template(model, sedml=sedml, accession=args.accession)
    except OSError as unreadable:
        print(f"cannot read the model: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError) as unreadable:
        print(f"cannot read the model: {unreadable}", file=sys.stderr)
        return 1

    rendered = json.dumps(template, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(rendered, end="")
        return 0
    try:
        Path(args.out).write_text(rendered, encoding="utf-8")
    except OSError as unwritable:
        print(f"cannot write the template: {unwritable}", file=sys.stderr)
        return 1
    body = template["entries"][args.accession] if args.accession is not None else template
    print(f"wrote {args.out}")
    print(f"  {len(body['claims'])} claim(s) to fill in, from the curves your document plots")
    for withheld in body.get("withheld", ()):
        print(f"  withheld: {withheld}")
    # A document plotting forty reaction fluxes produces forty near-identical notes, and a
    # summary nobody reads is worse than a shorter one — but a truncation that does not say it
    # truncated reads as "that was all of them", so the remainder is counted, not dropped.
    notes = body["notes"]
    for note in notes[:5]:
        print(f"  note: {note}")
    if len(notes) > 5:
        print(f"  ... and {len(notes) - 5} more note(s), all of them in the file's 'notes'")
    return 0


def _cmd_archive_check(query: ReprolithQuery, args: argparse.Namespace) -> int:
    """Report what a reproducer would find in a COMBINE archive, before any certificate exists."""
    if (args.archive is None) == (args.sedml is None or args.model is None):
        print(
            "give either an archive or both --sedml and --model: a check reads one experiment "
            "against the one model it names",
            file=sys.stderr,
        )
        return 1
    archive: bytes | None = None
    pair: tuple[str, str, dict[str, str]] | None = None
    try:
        if args.archive is not None:
            archive = Path(args.archive).read_bytes()
        else:
            pair = _read_pair(args)
    except OSError as unreadable:
        print(f"cannot read the archive: {unreadable}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, ValueError) as unreadable:
        print(f"cannot read the archive: {unreadable}", file=sys.stderr)
        return 1
    claims: list[Claim] = []
    if args.claims is not None:
        try:
            claims = _load_claims(Path(args.claims), args.accession)
        except (OSError, ValueError, KeyError, TypeError) as unusable:
            # A mistyped path, a shape this does not read, a record missing a field: all of them
            # are the author's file rather than their archive, and none is worth a traceback.
            print(f"cannot read the claims: {unusable}", file=sys.stderr)
            return 1
    if archive is not None:
        report = archive_report(archive, claims=claims)
        rendered = render_archive_human(archive, claims=claims)
    else:
        assert pair is not None
        sedml, sbml, data_files = pair
        name = Path(args.model).name
        report = pair_report(
            sedml, sbml, claims=claims, data_files=data_files, model_filename=name
        )
        rendered = render_pair_human(
            sedml, sbml, claims=claims, data_files=data_files, model_filename=name
        )
    if args.json:
        _print_json(report)
    else:
        print(rendered)
    # The exit code answers the question the command asks. An author wiring this into a
    # pre-submission hook needs "is this ready" to be actionable, and a report that always exits 0
    # says READY and NOT YET READY in the same voice.
    return 0 if report["ready_to_submit"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reprolith",
        description="Read Reprolith's catalog, certificates, and gap reports from the terminal — "
        "the same read-only surface agents reach over MCP.",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="repository state to read (default: the bundled milestone run)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_json(p: argparse.ArgumentParser) -> None:
        # Every read command takes --json, including the three whose only form is already the raw
        # object: the flag is the documented way to ask any command for what an agent receives, and
        # a command that rejected it would make that promise false.
        p.add_argument("--json", action="store_true", help="emit the raw JSON an agent receives")

    def add_identifier(p: argparse.ArgumentParser) -> None:
        p.add_argument("identifier", help="the paper identifier to look up")
        p.add_argument(
            "--by", choices=["accession", "doi", "pubmed-id", "title"], default="accession",
            help="which identifier the positional is (default: accession)",
        )

    p = sub.add_parser("catalog", help="list catalog entries (blind public view)")
    p.add_argument("--model-class", default=None, help="filter by model class")
    p.add_argument("--state", default=None, help="filter by lifecycle state")
    add_json(p)
    p.set_defaults(func=_cmd_catalog)

    p = sub.add_parser("backlog", help="backlog depth by state, class, and difficulty")
    add_json(p)
    p.set_defaults(func=_cmd_backlog)

    p = sub.add_parser(
        "self-validation",
        help="blind track record: verdicts vs independently-established ground truth",
    )
    add_json(p)
    p.set_defaults(func=_cmd_self_validation)

    p = sub.add_parser("status", help="a paper's lifecycle status and history")
    add_identifier(p)
    add_json(p)
    p.set_defaults(func=_cmd_status)

    p = sub.add_parser("certificate", help="the full certificate for a digest (human text)")
    p.add_argument("digest", help="the certificate's content digest")
    add_json(p)
    p.set_defaults(func=_cmd_certificate)

    p = sub.add_parser("verdict", help="the scope-qualified verdict for a digest")
    p.add_argument("digest", help="the certificate's content digest")
    add_json(p)
    p.set_defaults(func=_cmd_verdict)

    p = sub.add_parser("gaps", help="the 'what was missing' report for a digest")
    p.add_argument("digest", help="the certificate's content digest")
    add_json(p)
    p.set_defaults(func=_cmd_gaps)

    p = sub.add_parser("presubmission", help="the author-facing pre-submission report for a digest")
    p.add_argument("digest", help="the certificate's content digest")
    add_json(p)
    p.set_defaults(func=_cmd_presubmission)

    p = sub.add_parser("certificates-for", help="every certificate digest issued for a paper")
    add_identifier(p)
    add_json(p)
    p.set_defaults(func=_cmd_certificates_for)

    p = sub.add_parser("dossier", help="the ingested dossier for an accession")
    p.add_argument("accession", help="the entry accession")
    add_json(p)
    p.set_defaults(func=_cmd_dossier)

    p = sub.add_parser("bundle", help="the reconstruction bundle for an accession")
    p.add_argument("accession", help="the entry accession")
    add_json(p)
    p.set_defaults(func=_cmd_bundle)

    p = sub.add_parser(
        "archive-check",
        help="what a reproducer would find in a COMBINE archive (no model is run)",
    )
    p.add_argument(
        "archive", nargs="?", default=None,
        help="the .omex archive to check (or use --sedml and --model for loose files)",
    )
    p.add_argument("--sedml", default=None, help="the simulation document, when it is not packaged")
    p.add_argument("--model", default=None, help="the model the document names, when it is not packaged")
    p.add_argument(
        "--claims", default=None,
        help="a JSON file of the results your paper reports, so the check can also say whether "
             "the archive runs them (without it, that is not checked)",
    )
    p.add_argument(
        "--accession", default=None,
        help="which paper's claims to read, when --claims holds more than one",
    )
    add_json(p)
    p.set_defaults(func=_cmd_archive_check)

    p = sub.add_parser(
        "claims-check",
        help="check a claims file's reported values against the tables your paper prints",
    )
    p.add_argument("--claims", required=True, help="the claims file to check")
    p.add_argument(
        "--tables", required=True,
        help="the paper's table rows as JSON — the shape datasets/manuscripts/ uses",
    )
    p.add_argument(
        "--accession", default=None,
        help="which paper's claims to read, when --claims holds more than one",
    )
    add_json(p)
    p.set_defaults(func=_cmd_claims_check)

    p = sub.add_parser(
        "params-check",
        help="check your model's parameter values against the ones your paper reports",
    )
    p.add_argument("--model", required=True, help="the SBML model file to read the values from")
    p.add_argument(
        "--parameters", required=True,
        help="a JSON file pairing each model parameter id with the value your paper reports for "
             "it — the shape datasets/pkpd_parameters.json uses",
    )
    p.add_argument(
        "--accession", default=None,
        help="which paper's parameters to read, when the file holds more than one",
    )
    add_json(p)
    p.set_defaults(func=_cmd_params_check)

    p = sub.add_parser(
        "claims-propose",
        help="propose candidate claims from the tables your paper prints (you pick)",
    )
    p.add_argument(
        "--tables", required=True,
        help="the paper's table rows as JSON — the shape datasets/manuscripts/ uses",
    )
    p.add_argument(
        "--accession", default=None,
        help="wrap the result under this accession, the shape a multi-paper claims file uses",
    )
    p.add_argument("--out", default=None, help="write here instead of to standard output")
    p.set_defaults(func=_cmd_claims_propose)

    p = sub.add_parser(
        "claims-template",
        help="write the claims file archive-check needs, with the blanks left for you",
    )
    p.add_argument(
        "archive", nargs="?", default=None,
        help="the .omex archive to read the model and document out of (or use --model)",
    )
    p.add_argument("--model", default=None, help="the model file, when it is not packaged")
    p.add_argument(
        "--sedml", default=None,
        help="the simulation document, when you have one; without it no claim is written, "
             "because a model says what can be read and never what your paper showed",
    )
    p.add_argument(
        "--accession", default=None,
        help="wrap the result under this accession, the shape a multi-paper claims file uses",
    )
    p.add_argument("--out", default=None, help="write here instead of to standard output")
    p.set_defaults(func=_cmd_claims_template)

    p = sub.add_parser(
        "figure-template",
        help="write the digitization file for the curves your document plots (you read them)",
    )
    p.add_argument(
        "archive", nargs="?", default=None,
        help="the .omex archive to read the document out of (or use --sedml)",
    )
    p.add_argument(
        "--sedml", default=None,
        help="your simulation document, when it is not packaged; its plots say which curves your "
             "paper shows",
    )
    p.add_argument(
        "--plot", default=None,
        help="which of your document's plots this file is the reading of, when it has more than "
             "one; one file is one panel, because its axes are stated once",
    )
    p.add_argument("--out", default=None, help="write here instead of to standard output")
    p.add_argument(
        "--out-dir", default=None,
        help="write one template per panel into this directory, named for the plot it reads; "
             "a paper with four figures is then one command and still four files",
    )
    p.set_defaults(func=_cmd_figure_template)

    p = sub.add_parser(
        "figure-check",
        help="check a digitization of your figure before it is used as a reference",
    )
    p.add_argument(
        "--series", required=True, action="append", metavar="FILE",
        help="a plot digitizer's output for one figure panel as JSON: the figure, the digitizer, "
             "both axes, and one series of [x, y] points per curve. Repeat it for a paper with "
             "more than one panel — the pairing is then checked across all of them",
    )
    p.add_argument(
        "archive", nargs="?", default=None,
        help="the .omex archive the digitization was paired against (or use --sedml); without "
             "either, the claim ids in the file are not checked",
    )
    p.add_argument(
        "--sedml", default=None,
        help="your simulation document, when it is not packaged; the pairing is checked against "
             "the curves it plots",
    )
    add_json(p)
    p.set_defaults(func=_cmd_figure_check)

    p = sub.add_parser(
        "export",
        help="write a reconstruction as a runnable COMBINE archive (the one command that writes)",
    )
    p.add_argument("accession", help="the entry accession")
    p.add_argument("--model", required=True, help="the SBML file the reconstruction was built from")
    p.add_argument("--out", required=True, help="where to write the .omex archive")
    add_json(p)
    p.set_defaults(func=_cmd_export)

    return parser


def run(argv: list[str] | None = None) -> int:
    """Parse ``argv`` and execute one read-only command; return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.data_dir is not None:
        # An explicit --data-dir means "read exactly this state" — no cross-class aggregation.
        try:
            query, _catalog = load_repository(args.data_dir)
        except FileNotFoundError as unreadable:
            # A mistyped path is the ordinary failure here (the README tells a reader to point an
            # installed copy at a checkout), so it gets a message, not a traceback.
            print(str(unreadable), file=sys.stderr)
            return 1
    else:
        # The default view aggregates every class's published milestone certificates, so a
        # verdict from any of the six classes is reachable, not just the PK/PD one.
        try:
            query, _catalog = load_repository(default_data_dir(), aggregate=True)
        except FileNotFoundError as unreadable:
            # default_data_dir() composes a message written for a human running an installed copy
            # outside a checkout; only the --data-dir branch was showing it to them.
            print(str(unreadable), file=sys.stderr)
            return 1
    try:
        result: int = args.func(query, args)
    except ValueError as refused:
        # The query layer refuses rather than publishes when committed state does not add up (an
        # agreement report whose counters cannot partition, for one). MCP reports that as a tool
        # error; the terminal raised a traceback for the same state.
        print(str(refused), file=sys.stderr)
        return 1
    return result


def main() -> None:  # pragma: no cover - console-script entry point
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["build_parser", "main", "run"]
