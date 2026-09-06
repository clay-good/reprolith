"""Bounding how many times the same unit of work can be handed out for nothing.

The `autonomous-build-loop` spec asks that a unit failing its gates repeatedly be parked with a
diagnosis rather than retried forever, and its own "what carries each requirement today" section
said nothing carried it. That was worse than an absent counter. `release_lease` records nothing
and an abandoned claim ends by lease expiry, which is only the clock passing — so a claim that
achieved nothing left no trace of any kind, and the entry was offered again the instant its lease
lapsed. Because the pool is ranked by readiness first, an *easy* entry that defeats everyone who
takes it sits at the head of the queue in front of every agent that asks for work, permanently.

These tests hold the bound to the three things that make it safe: it counts a real attempt, it
clears itself on real progress, and it never puts an entry out of reach — only out of the pool
handed out unasked.
"""

from __future__ import annotations

import json

from reprolith import Catalog, Identifiers, LifecycleState, ModelClass
from reprolith.catalog import PARK_AFTER_ATTEMPTS
from reprolith.mcp_server import claim_work


def _catalog(*accessions: str, difficulty: str | None = None) -> Catalog:
    catalog = Catalog()
    for accession in accessions:
        catalog.add(
            Identifiers(title=f"paper {accession}", accession=accession),
            ModelClass.ODE_PKPD,
            difficulty=difficulty,
        )
    return catalog


def _claim_and_abandon(catalog: Catalog, requester: str, *, at: float) -> None:
    """One fruitless claim: leased, then left until the lease lapses. Nothing else records this."""
    catalog.claim_next(requester, at=at, seconds=1.0)


# --- what counts as an attempt ----------------------------------------------------------------


def test_a_claim_is_recorded_even_when_nothing_else_happens() -> None:
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    assert entry.attempts == ()
    _claim_and_abandon(catalog, "agent", at=0.0)
    assert [a.requester for a in entry.attempts] == ["agent"]
    assert entry.attempts[0].state is LifecycleState.QUEUED


def test_an_entry_leaves_the_pool_after_the_stated_number_of_fruitless_claims() -> None:
    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        assert len(catalog.claimable(i * 100.0)) == 1, "still offered before the bound"
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    assert catalog.claimable(1000.0) == []
    assert [e.identifiers.accession for e in catalog.parked(1000.0)] == ["A1"]


def test_the_bound_is_not_one_because_a_lapsed_lease_is_an_ordinary_event() -> None:
    """An agent is interrupted, a process dies. Parking on the first of those would withdraw
    work over an accident, which costs more than one extra try."""
    assert PARK_AFTER_ATTEMPTS > 1
    catalog = _catalog("A1")
    _claim_and_abandon(catalog, "agent", at=0.0)
    assert len(catalog.claimable(100.0)) == 1


# --- what clears it ---------------------------------------------------------------------------


def test_any_progress_clears_the_run_without_anything_resetting_a_counter() -> None:
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS - 1):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    entry.transition(
        LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="started"
    )
    assert entry.attempts_without_progress() == ()
    assert entry.is_parked() is False
    # And the attempts themselves are not erased — the record of what was tried survives.
    assert len(entry.attempts) == PARK_AFTER_ATTEMPTS - 1


def test_a_parked_entry_unparks_itself_the_moment_its_state_moves() -> None:
    """Derived, not latched: nothing has to remember to lower a flag, which is the failure mode
    a stored 'parked' boolean would have had."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    assert entry.is_parked()
    entry.transition(
        LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="started"
    )
    assert entry.is_parked() is False


def test_a_block_counts_as_progress() -> None:
    """`blocked` is a real finding about the entry, not a failure to move it: the claim that
    established it did work, and the next claim is not a repeat of the last."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    _claim_and_abandon(catalog, "agent", at=0.0)
    entry.transition(
        LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="started"
    )
    entry.transition(
        LifecycleState.BLOCKED,
        at="2026-09-06T00:01:00Z",
        actor="agent",
        reason="supplement is paywalled",
        missing_inputs=("the supplement",),
    )
    assert entry.attempts_without_progress() == ()


# --- what it must never do --------------------------------------------------------------------


def test_a_parked_entry_is_out_of_the_pool_not_out_of_reach() -> None:
    """No surface performs the quarantine that is the state machine's only other way out of
    `queued`, so an entry that stopped being claimable at all would be a permanent wedge."""
    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    assert catalog.claimable(1000.0) == []
    offered = catalog.claimable(1000.0, include_parked=True)
    assert [e.identifiers.accession for e in offered] == ["A1"]


def test_parking_one_entry_does_not_withhold_another() -> None:
    catalog = _catalog("A1", "A2")
    for i in range(PARK_AFTER_ATTEMPTS):
        entry = catalog.claim_next("agent", at=i * 100.0, seconds=1.0)
        assert entry.identifiers.accession == "A1", "the head of the queue is offered every time"
    remaining = catalog.claimable(1000.0)
    assert [e.identifiers.accession for e in remaining] == ["A2"]


def test_the_diagnosis_names_who_took_it_and_how_to_take_it_anyway() -> None:
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    diagnosis = entry.parking_diagnosis()
    assert f"claimed {PARK_AFTER_ATTEMPTS} times" in diagnosis
    assert "agent took it every time" in diagnosis
    assert "include_parked" in diagnosis


def test_the_diagnosis_separates_one_agent_failing_thrice_from_three_agents_failing_once() -> None:
    """Different problems, and only one of them is likely to be the entry's fault."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, f"agent-{i}", at=i * 100.0)
    assert f"{PARK_AFTER_ATTEMPTS} different claimants took it" in entry.parking_diagnosis()


def test_an_unparked_entry_has_no_diagnosis() -> None:
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    assert entry.parking_diagnosis() is None


# --- what the surfaces say --------------------------------------------------------------------


def test_claim_work_says_why_the_pool_is_empty_rather_than_only_that_it_is() -> None:
    """A pool that quietly got smaller is the dead end this refusal had to be taught to talk its
    way out of once already, in front of 31 entries."""
    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    refusal = claim_work(catalog, {"requester": "agent"}, at=1000.0)
    assert refusal["claimed"] is False
    assert "parked" in refusal["reason"]
    assert "include_parked" in refusal["reason"]
    assert refusal["parked"][0]["accession"] == "A1"
    assert refusal["parked"][0]["attempts_without_progress"] == PARK_AFTER_ATTEMPTS


def test_claim_work_hands_over_a_parked_entry_only_when_asked_and_says_it_did() -> None:
    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    claimed = claim_work(
        catalog, {"requester": "agent", "include_parked": True}, at=1000.0
    )
    assert claimed["claimed"] is True
    assert claimed["parked"] is True
    assert "include_parked" in claimed["parking_diagnosis"]


def test_a_freshly_claimed_entry_is_not_reported_as_parked() -> None:
    catalog = _catalog("A1")
    claimed = claim_work(catalog, {"requester": "agent"}, at=0.0)
    assert claimed["claimed"] is True
    assert claimed["parked"] is False
    assert claimed["parking_diagnosis"] is None


def test_backlog_health_explains_the_gap_between_queued_and_claimable() -> None:
    """A parked entry is still queued, so the two numbers disagree with nothing to explain them
    unless the parks are named."""
    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    health = catalog.backlog_health(1000.0)
    assert health["by_state"]["queued"] == 1
    assert health["claimable"] == 0
    assert [p["accession"] for p in health["parked"]] == ["A1"]
    assert health["parked"][0]["diagnosis"]


# --- persistence ------------------------------------------------------------------------------


def test_attempts_survive_a_save_and_load() -> None:
    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    entry = reloaded.find(Identifiers(title="", accession="A1"))
    assert entry.is_parked()
    assert reloaded.claimable(1000.0) == []


def test_a_catalog_written_before_attempts_existed_loads_as_never_claimed() -> None:
    """The truth about those files: nothing recorded a claim, so nothing is known to have been
    tried. Defaulting the other way would park entries nobody has touched."""
    catalog = _catalog("A1")
    record = catalog.to_dict()
    for entry in record["entries"]:
        entry.pop("attempts")
    reloaded = Catalog.from_dict(record)
    assert reloaded.find(Identifiers(title="", accession="A1")).attempts == ()
    assert len(reloaded.claimable(1000.0)) == 1


def test_the_committed_catalog_still_offers_what_it_offered() -> None:
    """The bound is new and the shipped catalog predates it; nothing there should be parked by
    the mere act of adding the counter."""
    from reprolith.mcp_server import default_data_dir

    file = default_data_dir() / "catalog.json"
    catalog = Catalog.from_dict(json.loads(file.read_text(encoding="utf-8")))
    assert catalog.parked(0.0) == []
