"""Opening the verification issues the queue is owed (spec: ``github-collaboration``).

This is the one module in the package that reaches the network, and it does so through the
``gh`` command rather than an HTTP client of its own: the credentials, the host and the repository
are then the ones the person or workflow running it already chose, and Reprolith holds none of
them. Everything that decides *what* is filed is elsewhere and pure —
:func:`reprolith.reconcile_issues` and :func:`reprolith.filing_plan` — so what lives here is only
the three ``gh`` calls, each behind a ``run`` callable a test replaces.

It opens issues and creates the labels they need. It closes, reopens, edits and relabels nothing.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Optional

#: Runs ``gh`` with these arguments and this standard input, and returns what it printed.
Runner = Callable[[Sequence[str], Optional[str]], str]

#: How many issues one fetch asks for. ``gh issue list`` returns thirty unless told otherwise, and
#: a fetch that stopped short would read every issue past the cut as never filed — which this
#: module would then file a second time. A fetch that comes back full is refused for that reason.
FETCH_LIMIT = 1000

_ISSUE_FIELDS = "number,title,state,labels,body"


class GhError(RuntimeError):
    """``gh`` is missing, refused, or answered with something this cannot read."""


def run_gh(argv: Sequence[str], stdin: str | None = None) -> str:
    """Run ``gh`` and return its standard output, or raise :class:`GhError` with its own words."""
    try:
        done = subprocess.run(
            ["gh", *argv], input=stdin, capture_output=True, text=True, encoding="utf-8", check=False
        )
    except FileNotFoundError as missing:
        raise GhError(
            "the GitHub CLI `gh` is not installed or not on PATH; this package holds no GitHub "
            "credentials of its own and files through it"
        ) from missing
    if done.returncode != 0:
        raise GhError(f"`gh {' '.join(argv[:2])}` failed: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def _repo_args(repo: str | None) -> list[str]:
    return ["--repo", repo] if repo else []


def fetch_issues(run: Runner = run_gh, *, repo: str | None = None) -> list[dict[str, Any]]:
    """Every issue in the repository, open and closed, as :func:`reprolith.reconcile_issues` reads them.

    Not narrowed to the verification label: the reconciliation keys on the label *or* the question
    fingerprint, and a filed issue that lost its label is still an issue asking the question.
    """
    printed = run(
        ["issue", "list", "--state", "all", "--limit", str(FETCH_LIMIT), "--json", _ISSUE_FIELDS,
         *_repo_args(repo)],
        None,
    )
    try:
        issues = json.loads(printed)
    except ValueError as unreadable:
        raise GhError(f"`gh issue list` did not print JSON: {unreadable}") from unreadable
    if not isinstance(issues, list):
        raise GhError(f"`gh issue list` printed {type(issues).__name__}, not a list of issues")
    if len(issues) >= FETCH_LIMIT:
        raise GhError(
            f"the repository has at least {FETCH_LIMIT} issues and the fetch stops there, so an "
            "issue past the cut would read as never filed and be filed again; nothing was filed"
        )
    return issues


def _existing_labels(run: Runner, repo: str | None) -> set[str]:
    """The repository's label names, case-folded.

    GitHub compares label names without regard to case, so `Verification` already there is
    `verification` already there, and creating it again is refused.
    """
    printed = run(["label", "list", "--limit", "1000", "--json", "name", *_repo_args(repo)], None)
    try:
        return {str(label["name"]).casefold() for label in json.loads(printed)}
    except (ValueError, KeyError, TypeError) as unreadable:
        raise GhError(f"`gh label list` did not print a list of labels: {unreadable!r}") from unreadable


def file_issues(
    plan: Mapping[str, Any], run: Runner = run_gh, *, repo: str | None = None
) -> dict[str, Any]:
    """Open every issue in a :func:`reprolith.filing_plan`, creating the labels they need first.

    Returns what was filed (each with the URL ``gh`` printed), what was not, and the failure that
    stopped it if one did. It stops at the first failure rather than carrying on past it: the
    issues are filed in the queue's rank order, and a re-run fetches the issues afresh, so
    whatever was opened before the failure is seen and not opened twice.
    """
    pending = list(plan["to_file"])
    filed: list[dict[str, Any]] = []
    created: list[str] = []
    failure: str | None = None
    try:
        if pending:
            existing = _existing_labels(run, repo)
            for label in plan["labels"]:
                if label.casefold() not in existing:
                    run(["label", "create", label, *_repo_args(repo)], None)
                    created.append(label)
        while pending:
            issue = pending[0]
            argv = ["issue", "create", "--title", issue["title"], "--body-file", "-"]
            for label in issue["labels"]:
                argv += ["--label", label]
            url = run([*argv, *_repo_args(repo)], issue["body"]).strip()
            filed.append({"item_id": issue["item_id"], "title": issue["title"], "url": url})
            pending.pop(0)
    except GhError as stopped:
        failure = str(stopped)
    return {
        "filed": filed,
        "labels_created": created,
        "not_filed": [{"item_id": issue["item_id"], "title": issue["title"]} for issue in pending],
        "failure": failure,
    }


__all__ = ["FETCH_LIMIT", "GhError", "Runner", "fetch_issues", "file_issues", "run_gh"]
