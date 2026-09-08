"""The stop condition, answered rather than asserted.

The `autonomous-build-loop` spec says the loop stops when "the goal is met, the publishable backlog
is exhausted, or further progress is gated entirely on open escalations", with a summary of what it
parked and what it escalated. Every piece of that became machine-readable separately — what is
claimable, what each blocked entry waits on, what repeated fruitless claims parked, and what is
escalated — and nothing put them together, so an agent deciding to stop called three reads and
merged them by eye. "The backlog is exhausted" was a claim rather than an answer.

The tests that matter here are the ones about *which* reason is given: everything blocked on one
input, everything parked, and a genuinely empty backlog are three different situations, and a
report that collapses them tells a loop nothing about what would unblock it.
"""

from __future__ import annotations

import json

from reprolith import Catalog, Identifiers, LifecycleState, ModelClass
from reprolith.catalog import PARK_AFTER_ATTEMPTS
from reprolith.query import ReprolithQuery
from reprolith.supersession import CertificateLedger


def _query(catalog: Catalog) -> ReprolithQuery:
    return ReprolithQuery(catalog, CertificateLedger())


def _entry(catalog: Catalog, accession: str):
    return catalog.add(
        Identifiers(title=f"paper {accession}", accession=accession), ModelClass.ODE_PKPD
    )


# --- is there work ----------------------------------------------------------------------------


def test_work_available_carries_no_stop_reason() -> None:
    catalog = Catalog()
    _entry(catalog, "A1")
    status = _query(catalog).loop_status(at=0.0)
    assert status["publishable_work"] is True
    assert status["stop_reason"] is None
    assert status["claimable"] == 1


def test_an_empty_backlog_says_so_plainly() -> None:
    status = _query(Catalog()).loop_status(at=0.0)
    assert status["publishable_work"] is False
    assert "nothing in a workable state" in status["stop_reason"]


# --- which reason -----------------------------------------------------------------------------


def test_a_blocked_backlog_names_the_input_that_would_release_the_most() -> None:
    catalog = Catalog()
    for accession in ("A1", "A2"):
        entry = _entry(catalog, accession)
        entry.transition(
            LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="start"
        )
        entry.transition(
            LifecycleState.BLOCKED,
            at="2026-09-06T00:01:00Z",
            actor="agent",
            reason="missing",
            missing_inputs=("the manuscript's claims",),
        )
    status = _query(catalog).loop_status(at=0.0)
    assert status["publishable_work"] is False
    assert "2 entries blocked" in status["stop_reason"]
    assert "the manuscript's claims" in status["stop_reason"]


def test_a_parked_backlog_is_a_different_answer_from_a_blocked_one() -> None:
    """Both report zero claimable, and what would fix them is not remotely the same."""
    catalog = Catalog()
    _entry(catalog, "A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        catalog.claim_next("agent", at=i * 100.0, seconds=1.0)
    status = _query(catalog).loop_status(at=1000.0)
    assert status["publishable_work"] is False
    assert "parked after repeated claims" in status["stop_reason"]
    assert [p["accession"] for p in status["parked"]] == ["A1"]
    assert status["parked"][0]["diagnosis"]


def test_an_unaddressable_backlog_says_what_makes_it_unworkable() -> None:
    """An entry with no accession is claimable and unofferable: it cannot be finished or
    released, because both address an entry by accession."""
    catalog = Catalog()
    catalog.add(Identifiers(title="no accession here"), ModelClass.ODE_PKPD)
    status = _query(catalog).loop_status(at=0.0)
    assert status["publishable_work"] is False
    assert "carrying no accession" in status["stop_reason"]
    assert status["claimable_without_accession"] == 1


# --- what it escalates ------------------------------------------------------------------------


def test_a_backlog_that_is_blocked_and_parked_at_once_names_both() -> None:
    """Caught re-auditing the diff that added this. These are not alternatives — a backlog can be
    part blocked and part parked at the same time, and what would lift each is entirely different.
    An if/elif chain reported the blocked entries and said nothing about the parked ones, which is
    precisely what this field exists to stop.
    """
    catalog = Catalog()
    blocked = _entry(catalog, "B1")
    blocked.transition(
        LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="start"
    )
    blocked.transition(
        LifecycleState.BLOCKED,
        at="2026-09-06T00:01:00Z",
        actor="agent",
        reason="missing",
        missing_inputs=("a paywalled supplement",),
    )
    _entry(catalog, "P1")
    for i in range(PARK_AFTER_ATTEMPTS):
        catalog.claim_next("agent", at=i * 100.0, seconds=1.0)
    catalog.add(Identifiers(title="no accession here"), ModelClass.ODE_PKPD)

    reason = _query(catalog).loop_status(at=1000.0)["stop_reason"]
    assert "a paywalled supplement" in reason
    assert "parked after repeated claims" in reason
    assert "carrying no accession" in reason


def test_the_stop_reason_counts_read_as_english() -> None:
    """It is the headline the terminal prints and the string an agent keys on; "1 entries" is
    noise in the one sentence that has to be read carefully."""
    catalog = Catalog()
    entry = _entry(catalog, "B1")
    entry.transition(
        LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="start"
    )
    entry.transition(
        LifecycleState.BLOCKED,
        at="2026-09-06T00:01:00Z",
        actor="agent",
        reason="missing",
        missing_inputs=("a supplement",),
    )
    reason = _query(catalog).loop_status(at=0.0)["stop_reason"]
    assert "1 entry blocked" in reason
    assert "1 entries" not in reason
    # And with one blocked entry on one input, "1 of them" is not the phrasing.
    assert "all on one input" in reason


def test_escalations_are_split_the_way_the_queue_splits_them() -> None:
    """A loop asking whether it is gated "entirely on open escalations" needs to know which of
    its own gates it could lift itself: an expert's question and this engine's limit are not the
    same kind of wait."""
    from reprolith.mcp_server import default_data_dir, load_repository

    query, _ = load_repository(default_data_dir(), aggregate=True)
    status = query.loop_status()
    queue = query.verification_queue()
    assert status["escalated"]["awaiting_expert"] == queue["pending_count"]
    assert status["escalated"]["engine_limits"] == queue["engine_limits_count"]
    assert status["escalated"]["decided"] == queue["decided_count"]


# --- what it refuses to claim -----------------------------------------------------------------


def test_standing_counts_what_is_published_and_says_it_is_not_a_record_of_a_run() -> None:
    """The spec asks for "what it accomplished". That is the git history, and a field here
    summarizing a run would invent a record this package does not keep."""
    from reprolith.mcp_server import default_data_dir, load_repository

    query, _ = load_repository(default_data_dir(), aggregate=True)
    status = query.loop_status()
    assert status["standing"]["certificates"] == 39
    assert sum(status["standing"]["by_class"].values()) == 39
    assert "not what any one run produced" in status["standing_note"]


def test_standing_counts_only_what_still_stands() -> None:
    """A superseded certificate is not a published result; counting one reports work that has
    already been replaced.

    Built rather than read off the repository: no committed certificate has been superseded, so
    checking this against the corpus computes the same number on both sides of the assertion and
    passes whether the filter is there or not.
    """
    from reprolith import (
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
    )

    pin = EnginePin(engine="copasi", version="4.46")
    paper = PaperIdentity(title="one paper", doi="10.1/x")

    def cert(verdict, supersedes=None, **extra):
        return build_certificate(
            paper=paper,
            engine_pin=pin,
            assessments=[
                ClaimAssessment(
                    claim_id="c1",
                    quantity="AUC",
                    verdict=verdict,
                    source_location="T1",
                    **extra,
                )
            ],
            supersedes=supersedes,
        )

    original = cert(Verdict.REPRODUCED)
    ledger = CertificateLedger()
    ledger.issue(original)
    # A published miss has to say what missed — the certificate refuses one that does not.
    ledger.issue(
        cert(
            Verdict.FAILED,
            supersedes=original,
            discrepancy="off by 40%",
            root_cause="parameter-value-mismatch",
        )
    )
    status = ReprolithQuery(Catalog(), ledger).loop_status(at=0.0)
    assert len(ledger.items()) == 2
    assert status["standing"]["certificates"] == 1
    assert sum(status["standing"]["by_class"].values()) == 1


# --- the surfaces -----------------------------------------------------------------------------


def test_the_terminal_prints_the_reason_and_the_json_is_the_tool_object(capsys) -> None:
    from reprolith.cli import run
    from reprolith.mcp_server import default_data_dir, load_repository

    assert run(["loop-status"]) == 0
    out = capsys.readouterr().out
    assert "NO PUBLISHABLE WORK" in out
    assert "27 entries blocked" in out
    # Four for an expert, since the spatial wall moved into the half an expert can close: a claim
    # carries the boundary its source names, so somebody who knows which wall the paper used
    # settles it. And five engine limits, the newest being the noise entry's ensemble — the
    # sampling is this engine's draw and no wording in a paper clears it. That entry certifies
    # *two* claims off one ensemble and adds *one* item, which is the rule the queue states in its
    # own report: one limitation asked twice is one question with two dependents. The counts are
    # read off the same report the JSON below carries, so this pins the *line*, not the arithmetic.
    assert "escalated: 4 awaiting an expert, 5 limits of this engine" in out

    assert run(["loop-status", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    query, _ = load_repository(default_data_dir(), aggregate=True)
    assert printed["stop_reason"] == query.loop_status()["stop_reason"]


def test_the_terminal_counts_read_as_english_too(tmp_path, capsys) -> None:
    """The `stop_reason` pluralization fix was made in the query and not swept to the line the
    terminal prints directly above it, so one read "1 entry blocked" and the other "1 claimable
    entries". A helper one surface has and the other does not is a drift that had already
    happened."""
    import json as _json

    from reprolith.cli import run

    catalog = Catalog()
    _entry(catalog, "A1")
    catalog.add(Identifiers(title="no accession here"), ModelClass.ODE_PKPD)
    (tmp_path / "catalog.json").write_text(_json.dumps(catalog.to_dict()), encoding="utf-8")
    for sub in ("certificates", "dossiers", "bundles"):
        (tmp_path / sub).mkdir()

    assert run(["--data-dir", str(tmp_path), "loop-status"]) == 0
    out = capsys.readouterr().out
    assert "1 claimable entry" in out
    assert "1 claimable entries" not in out
    assert "1 queued entry carries no accession" in out
    # An empty breakdown after a zero is the same kind of noise.
    assert "standing: 0 certificates\n" in out
    assert "()" not in out
