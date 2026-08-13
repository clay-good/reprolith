"""The human-facing command-line surface over the read-only query model (spec: ``human-cli``).

Reprolith has two surfaces over one core: an MCP server for agents
(:mod:`reprolith.mcp_server`) and this CLI for humans at a terminal. Both load the same
persisted repository through :func:`reprolith.mcp_server.load_repository` and read it through
the same :class:`~reprolith.query.ReprolithQuery`, so the terminal view and the agent view can
never disagree ("Parity with the human surface"). The CLI computes no verdict of its own; it
formats what the query returns.

Every command is read-only. Structured data prints as indented, sorted JSON with ``--json``
(the exact object an agent gets over MCP); without it, the human-friendly formatters below
render the same data as legible text. A certificate renders through
:func:`reprolith.render.render_human`, the canonical plain-text certificate, so the terminal
never shows a form that could disagree with the published one.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .mcp_server import default_data_dir, load_repository
from .model import RunMetadata
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
    print(f"Backlog: {health['total']} entries "
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
    return 0


def _cmd_certificate(query: ReprolithQuery, args: argparse.Namespace) -> int:
    if args.json:
        view = query.certificate(args.digest)
        if view is None:
            print(f"unknown digest: {args.digest}", file=sys.stderr)
            return 1
        _print_json(view)
        return 0
    cert = query._ledger.get(args.digest)  # human rendering needs the object, not the dict view
    if cert is None:
        print(f"unknown digest: {args.digest}", file=sys.stderr)
        return 1
    print(render_human(cert, _NO_RUN))
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
    print(f"  scope: {view['scope']['human']}")
    return 0


def _cmd_gaps(query: ReprolithQuery, args: argparse.Namespace) -> int:
    items = query.gaps(args.digest)
    if items is None:
        print(f"unknown digest: {args.digest}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(items)
        return 0
    if not items:
        print("(no gaps — nothing was missing)")
        return 0
    print("WHAT WAS MISSING")
    for g in items:
        where = f"[{g['claim_id']}] {g['quantity']}: " if g["claim_id"] else ""
        print(f"  {where}{g['needs']}")
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
    p.set_defaults(func=_cmd_presubmission)

    p = sub.add_parser("certificates-for", help="every certificate digest issued for a paper")
    add_identifier(p)
    add_json(p)
    p.set_defaults(func=_cmd_certificates_for)

    p = sub.add_parser("dossier", help="the ingested dossier for an accession")
    p.add_argument("accession", help="the entry accession")
    p.set_defaults(func=_cmd_dossier)

    p = sub.add_parser("bundle", help="the reconstruction bundle for an accession")
    p.add_argument("accession", help="the entry accession")
    p.set_defaults(func=_cmd_bundle)

    return parser


def run(argv: list[str] | None = None) -> int:
    """Parse ``argv`` and execute one read-only command; return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.data_dir is not None:
        # An explicit --data-dir means "read exactly this state" — no cross-class aggregation.
        query, _catalog = load_repository(args.data_dir)
    else:
        # The default view aggregates every class's published milestone certificates, so a
        # verdict from any of the six classes is reachable, not just the PK/PD one.
        query, _catalog = load_repository(default_data_dir(), aggregate=True)
    result: int = args.func(query, args)
    return result


def main() -> None:  # pragma: no cover - console-script entry point
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["build_parser", "main", "run"]
