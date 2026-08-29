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
from .claims_template import claims_template, unfilled_claims
from .export import build_bundle_sedml, build_omex_archive
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


def _load_claims(path: Path, accession: str | None) -> list[Claim]:
    """The paper's own claims, read from a claims file.

    Three shapes are accepted, because they are the three an author plausibly has: a bare list of
    claim records, an object with a ``claims`` list, and the shape this repository's own
    ``datasets/pkpd_claims.json`` uses — ``entries`` keyed by accession, which needs
    ``--accession`` unless it holds exactly one.
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
        records = entries[accession]["claims"]
    elif isinstance(data, dict):
        records = data["claims"]
    else:
        records = data
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
