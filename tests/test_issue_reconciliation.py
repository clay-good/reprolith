"""The queue and its GitHub issues each know what the other says.

`reprolith verification-issue` writes the issue and a person files it; from that moment the two
sides drifted with nothing able to see it. The queue is derived from the standing certificates on
every call, so an item disappears the instant its certificates are superseded while its issue keeps
asking; and an issue can be closed, relabelled, or never opened without anything in the repository
noticing. The `github-collaboration` spec asks that "neither silently diverges from the other", and
its own carrier section named this half as missing.

These tests hold the comparison to what makes it worth running: it matches on the fingerprint
rather than on anything editable, it sees drift in both directions, it refuses a fetch that left
out the field the match depends on, and it changes nothing on either side.
"""

from __future__ import annotations

import pytest
from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    RecordedDecision,
    Verdict,
    build_certificate,
    issue_for_item,
    question_fingerprint,
    queue_report,
    reconcile_issues,
)
from reprolith.determinism import certificate_digest

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


def _report(*certs, decisions=()):
    return queue_report([(certificate_digest(c), c) for c in certs], decisions)


def _issue(item, *, number=1, state="OPEN", labels=None, body=None):
    """The issue as `gh issue list --json number,title,state,labels,body` prints one."""
    written = issue_for_item(item) if body is None else None
    return {
        "number": number,
        "title": written["title"] if written else "[verify] something",
        "state": state,
        "labels": [{"name": name} for name in (labels if labels is not None else written["labels"])],
        "body": written["body"] if written else body,
    }


def _only(report):
    (item,) = report["pending"]
    return item


# --- the two sides agreeing ------------------------------------------------------------------


def test_an_open_issue_for_a_pending_item_is_in_sync() -> None:
    report = _report(_cert(_assumption()))
    item = _only(report)
    result = reconcile_issues(
        report, [_issue(item)], expected_labels={item["id"]: issue_for_item(item)["labels"]}
    )
    assert result["divergent"] == []
    assert result["in_sync"] == 1
    assert result["unfiled"] == []
    assert result["issues"][0]["item_id"] == item["id"]
    assert result["issues"][0]["status"] == "pending"


def test_an_unrelated_issue_is_ignored_rather_than_reported() -> None:
    report = _report(_cert(_assumption()))
    item = _only(report)
    unrelated = {
        "number": 9, "title": "flaky test", "state": "OPEN",
        "labels": [{"name": "bug"}], "body": "no fingerprint here",
    }
    result = reconcile_issues(
        report, [_issue(item), unrelated], expected_labels={}
    )
    assert result["ignored_issues"] == 1
    assert [record["number"] for record in result["issues"]] == [1]


# --- drift the queue can see -------------------------------------------------------------------


def test_a_pending_item_with_no_issue_is_reported_as_unfiled() -> None:
    report = _report(_cert(_assumption()))
    result = reconcile_issues(report, [], expected_labels={})
    assert [entry["id"] for entry in result["unfiled"]] == [_only(report)["id"]]
    assert result["unfiled_count"] == 1
    assert "no issue at all" in result["note"]


def test_an_issue_closed_while_its_question_is_still_pending_diverges() -> None:
    report = _report(_cert(_assumption()))
    item = _only(report)
    result = reconcile_issues(report, [_issue(item, state="CLOSED")], expected_labels={})
    (record,) = result["divergent"]
    assert record["status"] == "pending"
    assert "closed while its question is still pending" in record["divergences"][0]
    # …and it is not also counted as unfiled: the issue exists, it is the state that is wrong.
    assert result["unfiled"] == []


def test_a_relabelled_issue_diverges_on_the_labels_it_lost() -> None:
    report = _report(_cert(_assumption()))
    item = _only(report)
    expected = issue_for_item(item)["labels"]
    result = reconcile_issues(
        report,
        [_issue(item, labels=[label for label in expected if not label.startswith("impact:")])],
        expected_labels={item["id"]: expected},
    )
    (record,) = result["divergent"]
    assert "missing the label(s)" in record["divergences"][0]
    assert f"impact:{item['impact']}" in record["divergences"][0]


def test_an_issue_stripped_of_the_label_is_still_matched_by_its_question() -> None:
    """Keying on the label alone would let a relabelled issue — the drift this reports — vanish
    from the report by having drifted."""
    report = _report(_cert(_assumption()))
    item = _only(report)
    result = reconcile_issues(report, [_issue(item, labels=[])], expected_labels={})
    assert result["issues"][0]["item_id"] == item["id"]
    assert result["ignored_issues"] == 0


def test_an_open_issue_for_a_question_nothing_rests_on_diverges() -> None:
    """The certificates behind an item were superseded, or its question was reworded: either way
    the issue is asking for work that no longer lands anywhere."""
    report = _report(_cert(_assumption()))
    stale = _issue(_only(report))
    reworded = _report(_cert(_assumption(basis="the deposit's own annotation settles it")))
    result = reconcile_issues(reworded, [stale], expected_labels={})
    (record,) = result["divergent"]
    assert record["status"] == "no-longer-asked"
    assert record["item_id"] is None
    assert "no standing certificate rests on any more" in record["divergences"][0]


def test_a_closed_issue_for_a_question_nothing_asks_is_not_a_divergence() -> None:
    report = _report(_cert(_assumption()))
    stale = _issue(_only(report), state="CLOSED")
    result = reconcile_issues(_report(_cert()), [stale], expected_labels={})
    assert result["divergent"] == []
    assert result["issues"][0]["status"] == "no-longer-asked"


def test_a_labelled_issue_with_no_fingerprint_is_reported_rather_than_matched() -> None:
    hand_written = {
        "number": 4, "title": "[verify] the time unit", "state": "OPEN",
        "labels": [{"name": "verification"}], "body": "somebody typed this out by hand",
    }
    result = reconcile_issues(_report(_cert()), [hand_written], expected_labels={})
    (record,) = result["divergent"]
    assert record["status"] == "unrecognized"
    assert "no question fingerprint" in record["divergences"][0]


def test_an_open_issue_for_a_decided_item_diverges_without_promising_a_re_issue() -> None:
    assumption = _assumption()
    cert = _cert(assumption)
    pending = _report(cert)
    item = _only(pending)
    decision = RecordedDecision(
        item_id=item["id"],
        question_fingerprint=question_fingerprint(assumption),
        kind="confirm",
        expert="A. Curator",
        rationale="the deposited unit contradicts the paper's own tables",
        decided_on="2026-09-06",
        source="https://example.invalid/issues/1",
    )
    decided = _report(cert, decisions=[decision])
    assert decided["decided_count"] == 1
    result = reconcile_issues(decided, [_issue(item)], expected_labels={})
    (record,) = result["divergent"]
    assert record["status"] == "decided"
    assert "still open" in record["divergences"][0]
    # The one sentence this must not lose: an answer is not a re-certification.
    assert "does not lift" in record["divergences"][0]


def test_an_engine_limit_issue_is_named_as_one_no_decision_closes() -> None:
    """`verification-issue` refuses to write one, so an open issue asking it was filed by hand or
    before the item became an engine limit — and it asks a stranger for a judgment that cannot
    help."""
    report = _report(_cert(_assumption(author_can_close=False)))
    assert report["engine_limits_count"] == 1
    limit = report["engine_limits"][0]
    body = f"### The specific question\n\n```\n{limit['question_fingerprint']}\n```\n"
    result = reconcile_issues(
        report,
        [{"number": 7, "title": "[verify] x", "state": "OPEN",
          "labels": [{"name": "verification"}], "body": body}],
        expected_labels={},
    )
    (record,) = result["divergent"]
    assert record["status"] == "engine-limit"
    assert "no expert decision closes" in record["divergences"][0]


# --- what it refuses, and what it never does ---------------------------------------------------


@pytest.mark.parametrize("field", ["number", "state", "body"])
def test_a_fetch_that_left_out_a_field_is_refused_rather_than_read_as_drift(field: str) -> None:
    report = _report(_cert(_assumption()))
    raw = _issue(_only(report))
    del raw[field]
    with pytest.raises(ValueError, match=field):
        reconcile_issues(report, [raw], expected_labels={})


def test_the_report_says_it_resolves_nothing() -> None:
    report = _report(_cert(_assumption()))
    result = reconcile_issues(report, [_issue(_only(report), state="CLOSED")], expected_labels={})
    assert "nothing here closes, reopens or relabels anything" in result["note"]


def test_two_open_issues_asking_one_question_both_diverge() -> None:
    """A decision attaches to the question, not to an issue: answer one duplicate and the other
    keeps asking with nothing able to tell that it was answered."""
    report = _report(_cert(_assumption()))
    item = _only(report)
    result = reconcile_issues(
        report, [_issue(item, number=1), _issue(item, number=2)], expected_labels={}
    )
    assert len(result["divergent"]) == 2
    assert "asks the same question as #2" in result["issues"][0]["divergences"][0]
    assert "asks the same question as #1" in result["issues"][1]["divergences"][0]


def test_a_closed_duplicate_is_not_a_divergence() -> None:
    """Filed twice and tidied up is the ordinary shape, not drift."""
    report = _report(_cert(_assumption()))
    item = _only(report)
    result = reconcile_issues(
        report,
        [_issue(item, number=1), _issue(item, number=2, state="CLOSED")],
        expected_labels={},
    )
    assert [record["number"] for record in result["divergent"]] == [2]
    assert "closed while its question is still pending" in result["divergent"][0]["divergences"][0]


def test_a_body_quoting_a_certificate_digest_is_still_matched_on_its_question() -> None:
    """A digest is the same shape as a fingerprint. Matching on the first 64-hex token in the body
    would attach the issue to whatever a maintainer pasted above the question."""
    report = _report(_cert(_assumption()))
    item = _only(report)
    written = issue_for_item(item)
    quoted = "the certificate is " + "a" * 64 + "\n\n" + written["body"]
    result = reconcile_issues(
        report,
        [{"number": 1, "title": written["title"], "state": "OPEN",
          "labels": [{"name": name} for name in written["labels"]], "body": quoted}],
        expected_labels={},
    )
    assert result["issues"][0]["item_id"] == item["id"]
    assert result["divergent"] == []


def test_the_issue_this_repository_would_file_reconciles_as_in_sync() -> None:
    """The two commands share a format and nothing held them to it: `verification-issue` writes
    the fingerprint into the body and `issue-reconcile` reads it back out, so a change to either
    one silently unmatches every filed issue. This runs the shipped repository through both."""
    from reprolith.mcp_server import default_data_dir, load_repository

    query, _catalog = load_repository(default_data_dir(), aggregate=True)
    pending = query.verification_queue()["pending"]
    assert pending, "the shipped repository queues nothing to reconcile"
    filed = []
    for number, item in enumerate(pending, start=1):
        written = query.verification_issue(item["id"])
        filed.append({
            "number": number,
            "title": written["title"],
            "state": "OPEN",
            "labels": [{"name": name} for name in written["labels"]],
            "body": written["body"],
        })
    result = query.issue_reconciliation(filed)
    assert result["divergent"] == []
    assert result["unfiled"] == []
    assert result["in_sync"] == len(pending)
