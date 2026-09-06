"""Filling the issue a person opens, instead of asking them to transcribe one.

The `github-collaboration` spec asks that an escalated item surface as a structured issue carrying
the question, the source context, Reprolith's estimate and reasoning, and what depends on it,
"labelled with its model class, its impact rank, and a pending-verification status". Nothing filed
one — and nothing *filled* one either: the template says in its own description that it is opened
by hand, its `labels:` list was empty, and every field had to be copied out of a certificate by
eye. The queue had already put the values in one place; this puts them in the shape the template
asks for.

Two of these tests are about what it refuses to do, and they matter more than the formatting: an
item no expert can close must not be filed at a stranger, and a source location Reprolith does not
have must not be invented to fill a required field.
"""

from __future__ import annotations

from reprolith import (
    ISSUE_LABEL,
    Assumption,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    Verdict,
    build_certificate,
    issue_for_item,
    queue_report,
)
from reprolith.determinism import certificate_digest

PIN = EnginePin(engine="copasi", version="4.46")


def _assumption(**kw):
    base = dict(
        id="a1",
        description="what time unit does the deposit mean",
        chosen="hours",
        basis="the dynamics settle it",
        load_bearing=True,
        alternatives=("the declared 100 hours",),
    )
    base.update(kw)
    return Assumption(**base)


def _cert(*assumptions, title="Zake2021", doi="10.1/x"):
    return build_certificate(
        paper=PaperIdentity(title=title, doi=doi),
        engine_pin=PIN,
        assessments=[
            ClaimAssessment(
                claim_id="c1",
                quantity="AUC",
                verdict=Verdict.REPRODUCED,
                source_location="Table 1",
                assumption_qualified=bool(assumptions),
            )
        ],
        assumptions=list(assumptions),
    )


def _item(*certs, index=0, half="pending"):
    pairs = [(certificate_digest(c), c) for c in certs]
    return queue_report(pairs)[half][index]


# --- what the spec asks the issue to carry ----------------------------------------------------


def test_the_issue_carries_the_question_the_estimate_the_basis_and_the_stakes() -> None:
    item = _item(_cert(_assumption(verification_item="verify:named")))
    issue = issue_for_item(item)
    assert issue["title"] == "[verify] what time unit does the deposit mean"
    for expected in (
        "what time unit does the deposit mean",
        "hours",
        "the dynamics settle it",
        "the declared 100 hours",
        "Zake2021",
        "10.1/x",
    ):
        assert expected in issue["body"], expected


def test_the_labels_are_the_three_the_spec_names() -> None:
    item = _item(_cert(_assumption(verification_item="verify:named")))
    issue = issue_for_item(item, model_classes=["ode-pkpd"])
    assert ISSUE_LABEL in issue["labels"]
    assert "impact:1" in issue["labels"]
    assert "status:pending-verification" in issue["labels"]
    assert "class:ode-pkpd" in issue["labels"]


def test_impact_is_the_real_number_of_dependents() -> None:
    shared = _assumption(verification_item="verify:named")
    item = _item(_cert(shared, title="one"), _cert(shared, title="two"), _cert(shared, title="x"))
    issue = issue_for_item(item)
    assert "impact:3" in issue["labels"]
    assert "3 standing certificates" in issue["body"]
    for title in ("one", "two", "x"):
        assert title in issue["body"]


def test_an_item_spanning_classes_is_labelled_for_each_and_an_unknown_one_for_none() -> None:
    item = _item(_cert(_assumption(verification_item="verify:named")))
    both = issue_for_item(item, model_classes=["spatial", "ode-pkpd", "spatial"])
    assert [x for x in both["labels"] if x.startswith("class:")] == [
        "class:ode-pkpd",
        "class:spatial",
    ]
    assert [x for x in issue_for_item(item)["labels"] if x.startswith("class:")] == []


def test_the_body_carries_the_fingerprint_a_decision_has_to_quote() -> None:
    item = _item(_cert(_assumption(verification_item="verify:named")))
    assert item["question_fingerprint"] in issue_for_item(item)["body"]


def test_the_body_says_answering_does_not_re_issue_anything() -> None:
    """The one misreading an issue can cause: a confirmation is not a re-certification."""
    item = _item(_cert(_assumption(verification_item="verify:named")))
    assert "does not re-issue" in issue_for_item(item)["body"]


# --- what it refuses --------------------------------------------------------------------------


def test_an_engine_limit_is_refused_rather_than_filed_at_a_stranger() -> None:
    """No expert decision closes one, so filing it asks for a judgment that cannot help — the
    overstatement the queue's two headings exist to prevent."""
    item = _item(
        _cert(_assumption(verification_item="verify:limit", author_can_close=False)),
        half="engine_limits",
    )
    try:
        issue_for_item(item)
    except ValueError as refused:
        assert "limit of this engine" in str(refused)
    else:  # pragma: no cover - the assertion below reports it
        raise AssertionError("an engine-limit item was filed as a question for an expert")


def test_no_source_location_is_invented_for_an_assumption() -> None:
    """The template requires a section, equation, table or figure. Reprolith has one for a
    *claim* and not for an assumption, whose basis is a reason rather than a place. Filling the
    field with a plausible location would be its worst possible failure."""
    item = _item(_cert(_assumption(verification_item="verify:named")))
    body = issue_for_item(item)["body"]
    assert "records no section, equation, table or figure for an assumption" in body
    # And it does not borrow the claim's location, which belongs to a different thing.
    assert "Table 1" not in body


def test_a_derived_id_sends_the_reader_to_what_they_can_actually_grep() -> None:
    """No certificate contains a derived id, so printing it as the thing to search for would
    send an opener looking for a string that is in no file."""
    item = _item(_cert(_assumption()))
    body = issue_for_item(item)["body"]
    assert "No certificate names this id" in body
    assert "a1" in body


def test_a_named_id_is_given_as_the_citation_it_is() -> None:
    item = _item(_cert(_assumption(verification_item="verify:named")))
    assert "The certificates name this item as `verify:named`" in issue_for_item(item)["body"]


# --- the surfaces -----------------------------------------------------------------------------


def test_the_committed_queue_generates_an_issue_for_every_answerable_item() -> None:
    """Read off the real repository rather than a fixture, so an item shape the generator cannot
    fill fails here rather than at the moment somebody tries to open the issue."""
    from reprolith.mcp_server import default_data_dir, load_repository

    query, _ = load_repository(default_data_dir(), aggregate=True)
    report = query.verification_queue()
    assert report["pending"], "the queue is empty; this test guards nothing"
    for item in report["pending"]:
        issue = issue_for_item(item)
        assert issue["title"].startswith("[verify] ")
        assert issue["body"].strip()
        assert f"impact:{item['impact']}" in issue["labels"]


def test_the_cli_prints_the_issue_and_names_the_ids_when_asked_for_an_unknown_one(capsys) -> None:
    from reprolith.cli import run

    assert run(["verification-issue", "verify:time-unit-of-the-Zake2021-deposits"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("title:  [verify] ")
    assert "labels: verification, impact:4" in out
    assert "class:ode-pkpd" in out

    assert run(["verification-issue", "verify:nothing"]) == 1
    assert "unknown queue item" in capsys.readouterr().err


def test_every_committed_certificate_reports_the_class_it_was_published_under() -> None:
    """The registry page has always labelled its cards with the model class; the two queried
    surfaces could not answer the question at all, which is a disagreement waiting to happen."""
    from collections import Counter

    from reprolith.mcp_server import default_data_dir, load_repository

    query, _ = load_repository(default_data_dir(), aggregate=True)
    classes = Counter(query.model_class_of(digest) for digest, _ in query.ledger.items())
    assert None not in classes, "a published certificate belongs to no class"
    assert set(classes) == {
        "ode-pkpd",
        "kinetic",
        "constraint-based",
        "logical",
        "stochastic",
        "spatial",
    }
