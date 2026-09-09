"""The issue asks for a decision and now shows the decision's shape.

`verification-issue` prints everything an expert needs to answer — the question, the estimate, the
basis, the alternatives, what rests on it, and the fingerprint that keeps their name off a question
they never read. Then it said: add it to `datasets/verification_decisions.json`. Which fields? In
what shape? That was in CONTRIBUTING.md, under a hard-coded example for one particular item, so the
one thing a reader of this issue could not do without leaving it was the thing it asks them to do.

What is pinned here is not the wording. It is that the block the issue prints, with the three human
fields filled in, is a record this repository actually accepts — and that its fingerprint is the one
that joins the decision to the item, so the answer lands as *decided* rather than as *stale*.
"""

from __future__ import annotations

import json
import re

import pytest
from reprolith.decisions import RecordedDecision
from reprolith.mcp_server import (
    default_data_dir,
    load_certificates,
    load_repository,
    milestone_certificate_dirs,
)
from reprolith.supersession import CertificateLedger
from reprolith.verification import queue_report

_BLOCK = re.compile(r"```json\n(\{.*?\})\n```", re.DOTALL)


def _query():
    query, _catalog = load_repository(default_data_dir(), aggregate=True)
    return query


def _an_answerable_item() -> dict:
    pending = _query().verification_queue()["pending"]
    assert pending, "this repository publishes at least one item an expert can close"
    return pending[0]


def _record_block(body: str) -> dict:
    found = _BLOCK.search(body)
    assert found is not None, body
    return json.loads(found.group(1))


def test_the_issue_carries_the_record_with_what_only_this_repository_knows_filled() -> None:
    item = _an_answerable_item()
    record = _record_block(_query().verification_issue(item["id"])["body"])
    assert record["item_id"] == item["id"]
    assert record["question_fingerprint"] == item["question_fingerprint"]
    # Blank, not defaulted: `"kind": "confirm"` would be a nudge to agree with the estimate the
    # same issue has just argued for.
    assert record["kind"] == ""
    assert record["corrected_value"] is None


def test_the_blank_block_is_refused_by_name_rather_than_loaded() -> None:
    """The blanks are the instruction. A template that loaded would file an unusable decision."""
    record = _record_block(_query().verification_issue(_an_answerable_item()["id"])["body"])
    with pytest.raises(ValueError) as refused:
        RecordedDecision.from_dict(record)
    for field in ("kind", "expert", "rationale", "decided_on", "source"):
        assert field in str(refused.value)


def test_filling_the_three_human_fields_is_a_record_this_repository_accepts() -> None:
    """The end-to-end the issue promises: copy, fill, and it parses."""
    record = _record_block(_query().verification_issue(_an_answerable_item()["id"])["body"])
    record.update({
        "kind": "confirm",
        "expert": "A Reviewer",
        "rationale": "the declared unit is a deposition error; the dynamics settle it",
        "decided_on": "2026-09-09",
        "source": "https://github.com/clay-good/reprolith/issues/1",
    })
    parsed = RecordedDecision.from_dict(record)
    assert parsed.kind == "confirm" and parsed.corrected_value is None


def test_the_filled_record_lands_on_the_item_as_decided_and_not_as_stale() -> None:
    """The fingerprint in the block has to be the one the join reads, or the answer arrives stale.

    Publishing a fingerprint that did not match would be worse than publishing none: the expert
    would follow the instruction exactly and their decision would come back reported as an answer
    to a question that has since changed.
    """
    item = _an_answerable_item()
    record = _record_block(_query().verification_issue(item["id"])["body"])
    record.update({
        "kind": "confirm", "expert": "A Reviewer", "rationale": "checked against the paper",
        "decided_on": "2026-09-09", "source": "issue 1",
    })
    ledger = CertificateLedger()
    for certs_dir in milestone_certificate_dirs().values():
        load_certificates(ledger, certs_dir)
    pairs = [(digest, cert) for digest, cert in ledger.items()]
    report = queue_report(pairs, (RecordedDecision.from_dict(record),))
    assert [d["id"] for d in report["decided"]] == [item["id"]]
    assert report["stale_decisions"] == []
    assert item["id"] not in [row["id"] for row in report["pending"]]
