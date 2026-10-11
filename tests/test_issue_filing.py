"""The queue's unasked questions get filed, and no question is ever filed twice.

`reprolith verification-issue` writes an issue and `reprolith issue-reconcile` reports the pending
items that have none. Between the two a person still ran one `gh issue create` per item, and the
`github-collaboration` spec's own carrier section said so: "nothing files the issue".

Filing is the first thing in this package that acts on somebody else's record, so these tests hold
it to the direction that would do harm. A second issue for a question already asked — because its
first one was closed, because the fetch was cut short, because a run failed half-way and was run
again — is the failure. Leaving a question unfiled is not: the queue goes on asking it.

No test here reaches the network. `gh` is a callable, and every test hands in its own.
"""

from __future__ import annotations

import json

import pytest
from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    Verdict,
    build_certificate,
    filing_plan,
    issue_for_item,
    queue_report,
    reconcile_issues,
)
from reprolith.cli import run
from reprolith.determinism import certificate_digest
from reprolith.issue_filing import FETCH_LIMIT, GhError, fetch_issues, file_issues
from reprolith.mcp_server import load_repository
from test_cli import _write_repo  # the same repository the CLI tests build

PIN = EnginePin(engine="copasi", version="4.46")


def _assumption(**kw) -> Assumption:
    base = dict(
        id="a",
        description="what time unit does the deposit mean",
        chosen="hours",
        basis="the dynamics settle it",
        load_bearing=True,
        alternatives=("the declared 100 hours",),
    )
    base.update(kw)
    return Assumption(**base)


def _cert(*assumptions: Assumption, title: str = "t"):
    return build_certificate(
        paper=PaperIdentity(title=title),
        engine_pin=PIN,
        assessments=[
            ClaimAssessment(
                claim_id="c1",
                quantity="AUC",
                verdict=Verdict.REPRODUCED,
                source_location="T1",
                assumption_qualified=bool(assumptions),
            )
        ],
        assumptions=list(assumptions),
    )


def _report(*certs):
    return queue_report([(certificate_digest(c), c) for c in certs], ())


def _plan(report, issues):
    built = {item["id"]: issue_for_item(item) for item in report["pending"]}
    reconciliation = reconcile_issues(
        report, issues, expected_labels={k: v["labels"] for k, v in built.items()}
    )
    return filing_plan(reconciliation, built)


def _as_filed(issue, *, number=1, state="OPEN", labels=None):
    """A planned issue as `gh issue list` prints it once it exists."""
    return {
        "number": number,
        "title": issue["title"],
        "state": state,
        "labels": [{"name": name} for name in (issue["labels"] if labels is None else labels)],
        "body": issue["body"],
    }


class FakeGh:
    """A repository's issues and labels, behind the three `gh` calls filing makes."""

    def __init__(self, *, issues=(), labels=("bug",), fail_on_create: int | None = None):
        self.issues = list(issues)
        self.labels = list(labels)
        self.calls: list[list[str]] = []
        self.fail_on_create = fail_on_create
        self._creates = 0

    def __call__(self, argv, stdin):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        if argv[:2] == ["label", "list"]:
            return json.dumps([{"name": name} for name in self.labels])
        if argv[:2] == ["label", "create"]:
            assert argv[2].casefold() not in {name.casefold() for name in self.labels}, (
                f"GitHub refuses a label that already exists: {argv[2]}"
            )
            self.labels.append(argv[2])
            return ""
        if argv[:2] == ["issue", "create"]:
            self._creates += 1
            if self._creates == self.fail_on_create:
                raise GhError("`gh issue create` failed: HTTP 502")
            labels = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--label"]
            known = {name.casefold() for name in self.labels}
            missing = [name for name in labels if name.casefold() not in known]
            assert not missing, f"GitHub refuses an issue naming a label it lacks: {missing}"
            number = len(self.issues) + 1
            self.issues.append({
                "number": number,
                "title": argv[argv.index("--title") + 1],
                "state": "OPEN",
                "labels": [{"name": name} for name in labels],
                "body": stdin,
            })
            return f"https://github.com/o/r/issues/{number}\n"
        raise AssertionError(f"filing made a gh call it has no business making: {argv}")

    def creates(self) -> list[list[str]]:
        return [call for call in self.calls if call[:2] == ["issue", "create"]]


# --- what the plan holds ------------------------------------------------------------------------


def test_a_pending_item_with_no_issue_is_planned_as_the_issue_the_terminal_prints() -> None:
    report = _report(_cert(_assumption()))
    (item,) = report["pending"]
    written = issue_for_item(item)
    plan = _plan(report, [])
    (planned,) = plan["to_file"]
    assert (planned["title"], planned["labels"], planned["body"]) == (
        written["title"], written["labels"], written["body"],
    )
    assert planned["item_id"] == item["id"]
    assert plan["labels"] == sorted(written["labels"])
    assert "1 pending item(s) have no issue yet" in plan["note"]


def test_an_item_whose_issue_is_open_is_not_planned_again() -> None:
    report = _report(_cert(_assumption()))
    (issue,) = _plan(report, [])["to_file"]
    plan = _plan(report, [_as_filed(issue)])
    assert plan["to_file"] == []
    assert plan["labels"] == []
    assert plan["already_asked"] == 1


def test_an_item_whose_issue_was_closed_is_a_divergence_and_not_a_second_issue() -> None:
    """The direction that matters. A maintainer closed the issue and the question is still
    pending: that is a disagreement for a person to read, and re-filing would overrule one side
    of it every time the command ran."""
    report = _report(_cert(_assumption()))
    (issue,) = _plan(report, [])["to_file"]
    plan = _plan(report, [_as_filed(issue, state="CLOSED")])
    assert plan["to_file"] == []
    assert plan["divergent_count"] == 1
    assert "issue-reconcile" in plan["note"]


def test_an_item_whose_issue_lost_its_label_is_not_planned_again() -> None:
    report = _report(_cert(_assumption()))
    (issue,) = _plan(report, [])["to_file"]
    assert _plan(report, [_as_filed(issue, labels=["question"])])["to_file"] == []


def test_the_plan_is_in_the_queue_s_rank_order() -> None:
    shared = _assumption(id="shared", description="which clock")
    lone = _assumption(id="lone", description="which salt form")
    report = _report(_cert(shared, title="p1"), _cert(shared, lone, title="p2"))
    plan = _plan(report, [])
    assert [issue["impact"] for issue in plan["to_file"]] == [2, 1]
    assert [issue["item_id"] for issue in plan["to_file"]] == [
        item["id"] for item in report["pending"]
    ]


def test_an_engine_limit_is_never_planned() -> None:
    ours = _assumption(id="ours", description="the ensemble drawn", author_can_close=False)
    report = _report(_cert(ours))
    assert report["engine_limits"], "the fixture no longer builds an engine limit"
    assert _plan(report, [])["to_file"] == []


# --- filing -------------------------------------------------------------------------------------


def test_filing_creates_the_labels_an_issue_needs_before_the_issue() -> None:
    report = _report(_cert(_assumption()))
    plan = _plan(report, [])
    gh = FakeGh(labels=["bug", "Verification"])
    outcome = file_issues(plan, gh)
    assert outcome["failure"] is None
    assert [filed["url"] for filed in outcome["filed"]] == ["https://github.com/o/r/issues/1"]
    # `Verification` is `verification` to GitHub, so it is not created a second time.
    assert outcome["labels_created"] == ["impact:1", "status:pending-verification"]
    (created,) = gh.issues
    assert created["body"] == plan["to_file"][0]["body"]
    assert created["title"] == plan["to_file"][0]["title"]


def test_what_was_filed_reconciles_as_in_sync_and_a_second_run_files_nothing() -> None:
    report = _report(_cert(_assumption(id="x", description="which clock")),
                     _cert(_assumption(id="y", description="which salt"), title="p2"))
    gh = FakeGh()
    file_issues(_plan(report, fetch_issues(gh)), gh)
    assert len(gh.creates()) == 2
    again = _plan(report, fetch_issues(gh))
    assert again["to_file"] == []
    assert again["divergent_count"] == 0
    file_issues(again, gh)
    assert len(gh.creates()) == 2
    # With nothing to file it does not ask for the labels either.
    assert gh.calls[-1][:2] == ["issue", "list"]


def test_a_failure_stops_the_run_and_the_next_run_files_only_the_rest() -> None:
    report = _report(_cert(_assumption(id="x", description="which clock")),
                     _cert(_assumption(id="y", description="which salt"), title="p2"),
                     _cert(_assumption(id="z", description="which route"), title="p3"))
    gh = FakeGh(fail_on_create=2)
    outcome = file_issues(_plan(report, fetch_issues(gh)), gh)
    assert outcome["failure"] == "`gh issue create` failed: HTTP 502"
    assert len(outcome["filed"]) == 1
    assert len(outcome["not_filed"]) == 2
    assert len(gh.creates()) == 2, "it carried on past the failure"
    outcome = file_issues(_plan(report, fetch_issues(gh)), gh)
    assert outcome["failure"] is None
    assert len(gh.issues) == 3
    assert len({issue["body"] for issue in gh.issues}) == 3


def test_a_fetch_that_came_back_full_is_refused_rather_than_trusted() -> None:
    """`gh issue list` stops at its limit without saying so, and every issue past the cut would
    read as never filed."""
    gh = FakeGh(issues=[
        {"number": n, "title": "t", "state": "OPEN", "labels": [], "body": ""}
        for n in range(FETCH_LIMIT)
    ])
    with pytest.raises(GhError, match="nothing was filed"):
        fetch_issues(gh)


def test_the_fetch_asks_for_closed_issues_and_is_not_narrowed_to_the_label() -> None:
    gh = FakeGh()
    fetch_issues(gh, repo="o/r")
    (call,) = gh.calls
    assert call[call.index("--state") + 1] == "all"
    assert call[call.index("--limit") + 1] == str(FETCH_LIMIT)
    assert "--label" not in call
    assert call[call.index("--repo") + 1] == "o/r"


# --- the command --------------------------------------------------------------------------------


def test_the_dry_run_names_what_it_would_file_and_calls_nothing(tmp_path, capsys, monkeypatch):
    repo, _ = _write_repo(tmp_path)
    issues = tmp_path / "issues.json"
    issues.write_text("[]", encoding="utf-8")

    def no_gh(argv, stdin):
        raise AssertionError(f"a dry run reached for gh: {argv}")

    monkeypatch.setattr("reprolith.issue_filing.run_gh", no_gh)
    assert run(["--data-dir", str(repo), "issue-file", str(issues)]) == 0
    out = capsys.readouterr().out
    assert "would file: [verify] " in out
    assert "nothing was filed" in out


def test_apply_files_through_gh_and_a_second_apply_files_nothing(tmp_path, capsys, monkeypatch):
    repo, _ = _write_repo(tmp_path)
    gh = FakeGh()
    monkeypatch.setattr("reprolith.issue_filing.run_gh", gh)
    assert run(["--data-dir", str(repo), "issue-file", "--apply", "--repo", "o/r"]) == 0
    out = capsys.readouterr().out
    assert "filed: https://github.com/o/r/issues/1" in out
    assert "created label: verification" in out
    assert all("--repo" in call for call in gh.calls)
    # The issue it opened is the one `verification-issue` prints for that item.
    query, _catalog = load_repository(repo)
    item = query.verification_queue()["pending"][0]
    assert gh.issues[0]["body"] == query.verification_issue(item["id"])["body"]
    assert run(["--data-dir", str(repo), "issue-file", "--apply", "--repo", "o/r"]) == 0
    assert len(gh.creates()) == 1
    assert "0 pending item(s) have no issue yet" in capsys.readouterr().out


def test_apply_with_a_file_is_refused_before_anything_is_called(tmp_path, capsys, monkeypatch):
    """A file is a snapshot; an issue opened since it was written would be opened again."""
    repo, _ = _write_repo(tmp_path)
    issues = tmp_path / "issues.json"
    issues.write_text("[]", encoding="utf-8")
    gh = FakeGh()
    monkeypatch.setattr("reprolith.issue_filing.run_gh", gh)
    assert run(["--data-dir", str(repo), "issue-file", str(issues), "--apply"]) == 1
    assert run(["--data-dir", str(repo), "issue-file"]) == 1
    assert gh.calls == []
    assert "not both" in capsys.readouterr().err


def test_a_failed_apply_exits_nonzero_and_says_a_rerun_is_safe(tmp_path, capsys, monkeypatch):
    repo, _ = _write_repo(tmp_path)
    monkeypatch.setattr("reprolith.issue_filing.run_gh", FakeGh(fail_on_create=1))
    assert run(["--data-dir", str(repo), "issue-file", "--apply"]) == 1
    captured = capsys.readouterr()
    assert "NOT filed: [verify] " in captured.out
    assert "stopped: `gh issue create` failed: HTTP 502" in captured.err
    assert "not filed twice" in captured.err


def test_apply_without_gh_is_a_message(tmp_path, capsys, monkeypatch):
    repo, _ = _write_repo(tmp_path)

    def missing(argv, stdin):
        raise GhError("the GitHub CLI `gh` is not installed or not on PATH")

    monkeypatch.setattr("reprolith.issue_filing.run_gh", missing)
    assert run(["--data-dir", str(repo), "issue-file", "--apply"]) == 1
    assert "cannot read the issues: the GitHub CLI `gh` is not installed" in capsys.readouterr().err


def test_json_carries_the_plan_and_what_applying_it_did(tmp_path, capsys, monkeypatch):
    repo, _ = _write_repo(tmp_path)
    issues = tmp_path / "issues.json"
    issues.write_text("[]", encoding="utf-8")
    assert run(["--data-dir", str(repo), "issue-file", str(issues), "--json"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["applied"] is None
    assert len(dry["to_file"]) == 1
    monkeypatch.setattr("reprolith.issue_filing.run_gh", FakeGh())
    assert run(["--data-dir", str(repo), "issue-file", "--apply", "--json"]) == 0
    applied = json.loads(capsys.readouterr().out)["applied"]
    assert [filed["item_id"] for filed in applied["filed"]] == [dry["to_file"][0]["item_id"]]
    assert applied["failure"] is None
