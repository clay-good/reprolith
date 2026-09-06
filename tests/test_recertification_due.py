"""What a repository owes a re-run after an expert answers, and after its own judge moves.

Both halves were reachable only by somebody who already knew to look. The `verification-queue`
spec asks that "a correction triggers re-verification of every dependent entry" —
`reverify_dependents` does it and a person has to know which entries those are, which the
`autonomous-build-loop` spec has listed as agent-carried since the decision record landed. And a
certificate names the revision of the judging code that produced its numbers; `tests/test_pins.py`
holds the *committed* corpus to that, so a reader with their own `--data-dir` could not ask.

These tests hold the answer to the distinctions that make it worth reading: a confirmation owes
nothing, a rejection owes a re-run it cannot have, and a class the report cannot name is said to be
unchecked rather than passed.
"""

from __future__ import annotations

from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    RecordedDecision,
    Verdict,
    build_certificate,
    question_fingerprint,
    queue_report,
    recertification_due,
)
from reprolith.determinism import certificate_digest

CURRENT = EnginePin(engine="reprolith-fd", version="0.0.1", algorithm="euler (rev abc123abc123)")
REVISIONS = {"spatial": "abc123abc123"}


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


def _cert(*assumptions: Assumption, pin: EnginePin = CURRENT, title: str = "a paper"):
    return build_certificate(
        paper=PaperIdentity(title=title),
        engine_pin=pin,
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


def _decision(assumption: Assumption, item_id: str, **kw) -> RecordedDecision:
    base = dict(
        item_id=item_id,
        question_fingerprint=question_fingerprint(assumption),
        kind="confirm",
        expert="A. Curator",
        rationale="the deposited unit contradicts the paper's own tables",
        decided_on="2026-09-06",
        source="https://example.invalid/issues/1",
    )
    base.update(kw)
    return RecordedDecision(**base)


def _due(cert, decisions=(), *, model_classes=None, revisions=None):
    pairs = [(certificate_digest(cert), cert)]
    digest = pairs[0][0]
    return recertification_due(
        queue_report(pairs, decisions),
        pairs,
        model_classes=model_classes if model_classes is not None else {digest: "spatial"},
        current_revisions=REVISIONS if revisions is None else revisions,
    ), digest


# --- the decision half -------------------------------------------------------------------------


def test_a_fresh_certificate_with_no_decision_owes_nothing() -> None:
    report, _ = _due(_cert(_assumption()))
    assert report["due"] == []
    assert "no standing certificate owes a re-run" in report["note"]


def test_a_correction_puts_every_dependent_certificate_on_the_list() -> None:
    assumption = _assumption()
    cert = _cert(assumption)
    pairs = [(certificate_digest(cert), cert)]
    item = queue_report(pairs, ())["pending"][0]
    decision = _decision(assumption, item["id"], kind="correct", corrected_value="100 hours")
    report, digest = _due(cert, [decision])
    (entry,) = report["due"]
    assert entry["digest"] == digest
    (reason,) = entry["reasons"]
    assert reason["kind"] == "correction"
    assert reason["corrected_value"] == "100 hours"
    assert reason["expert"] == "A. Curator"


def test_a_confirmation_owes_no_re_run_and_is_counted_rather_than_listed() -> None:
    """The numbers do not move: the value is still one Reprolith chose and the certificates still
    carry it as load-bearing. Re-issuing would publish the same certificate under a new digest."""
    assumption = _assumption()
    cert = _cert(assumption)
    item = queue_report([(certificate_digest(cert), cert)], ())["pending"][0]
    report, _ = _due(cert, [_decision(assumption, item["id"])])
    assert report["due"] == []
    assert report["confirmations"] == 1
    assert "owe none" in report["note"]


def test_a_rejection_is_blocked_rather_than_due() -> None:
    """A rejection supplies no replacement, so its dependents cannot be re-issued at all — listing
    them as due would ask for a re-run with nothing to re-run against."""
    assumption = _assumption()
    cert = _cert(assumption)
    item = queue_report([(certificate_digest(cert), cert)], ())["pending"][0]
    report, digest = _due(cert, [_decision(assumption, item["id"], kind="reject")])
    assert report["due"] == []
    (blocked,) = report["blocked"]
    assert blocked["digest"] == digest
    assert "supplies no replacement value" in blocked["why"]
    assert "cannot be re-issued" in report["note"]


# --- the freshness half ------------------------------------------------------------------------


def test_a_certificate_naming_an_older_judge_revision_owes_a_re_run() -> None:
    stale = EnginePin(engine="reprolith-fd", version="0.0.1", algorithm="euler (rev 000000000000)")
    report, _ = _due(_cert(pin=stale))
    (entry,) = report["due"]
    (reason,) = entry["reasons"]
    assert reason["kind"] == "engine-revision"
    assert reason["current_revision"] == "abc123abc123"
    assert "not the ones the current code produces" in reason["why"]


def test_a_pin_naming_no_revision_at_all_owes_one_too() -> None:
    """An earlier release wrote pins with no algorithm; a certificate carrying one cannot be shown
    to name the current code, and reading that as fresh is how a stale number stays published."""
    unpinned = EnginePin(engine="reprolith-fd", version="0.0.1")
    report, _ = _due(_cert(pin=unpinned))
    assert report["due_count"] == 1
    assert report["due"][0]["reasons"][0]["pinned"] is None


def test_a_class_whose_label_maps_to_no_revision_is_unchecked_rather_than_passed() -> None:
    """The read surface spells the constraint-based class with a hyphen and `JUDGE_MODULES` with an
    underscore, so a label that fell through would take a whole class out of the check while the
    report still read as complete. Reported as unchecked, not silently passed."""
    cert = _cert()
    digest = certificate_digest(cert)
    report, _ = _due(cert, model_classes={digest: "constraint-based"},
                     revisions={"constraint_based": "abc123abc123"})
    assert report["due"] == []
    (unknown,) = report["unknown_class"]
    assert unknown["digest"] == digest
    assert unknown["model_class"] == "constraint-based"
    assert "could not be checked" in report["note"]


def test_a_certificate_reached_by_both_causes_carries_both_and_sorts_first() -> None:
    assumption = _assumption()
    stale = EnginePin(engine="reprolith-fd", version="0.0.1", algorithm="euler (rev 000000000000)")
    both = _cert(assumption, pin=stale, title="reached twice")
    fresh_stale_only = _cert(pin=stale, title="only the judge moved")
    pairs = [(certificate_digest(c), c) for c in (both, fresh_stale_only)]
    item = queue_report(pairs, ())["pending"][0]
    decision = _decision(assumption, item["id"], kind="correct", corrected_value="100 hours")
    report = recertification_due(
        queue_report(pairs, [decision]),
        pairs,
        model_classes={digest: "spatial" for digest, _ in pairs},
        current_revisions=REVISIONS,
    )
    assert report["due_count"] == 2
    assert report["due"][0]["paper"]["title"] == "reached twice"
    assert {reason["kind"] for reason in report["due"][0]["reasons"]} == {
        "correction", "engine-revision"
    }


def test_the_shipped_repository_owes_no_re_run() -> None:
    """The same fact `tests/test_pins.py` holds the committed certificates to, asked through the
    surface a reader actually has. If this fails after a solver or oracle edit, re-run that class's
    milestone script — the run is the point, not the file."""
    from reprolith.mcp_server import default_data_dir, load_repository

    query, _catalog = load_repository(default_data_dir(), aggregate=True)
    report = query.recertification_due()
    assert report["due"] == [], report["note"]
    assert report["blocked"] == []
    assert report["unknown_class"] == [], "a published certificate whose class nothing here names"


def test_every_class_label_the_surface_uses_maps_to_a_judge_revision() -> None:
    """The two halves of the mapping, held against each other rather than against a list here: a
    class in the read surface with no judge key silently becomes 'unknown', and a judge key
    naming no class is a mapping nobody maintains."""
    from reprolith.mcp_server import milestone_certificate_dirs
    from reprolith.pins import JUDGE_MODULES
    from reprolith.query import _JUDGE_KEYS

    assert set(_JUDGE_KEYS) == set(milestone_certificate_dirs())
    assert set(_JUDGE_KEYS.values()) == set(JUDGE_MODULES)
