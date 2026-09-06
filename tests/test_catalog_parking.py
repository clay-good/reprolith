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


# --- why they gave up -------------------------------------------------------------------------


def _claim_and_release(catalog: Catalog, requester: str, *, at: float, reason: str = "") -> None:
    from reprolith.mcp_server import release_work

    claim_work(catalog, {"requester": requester}, at=at)
    release_work(
        catalog,
        {"accession": "A1", "requester": requester, **({"reason": reason} if reason else {})},
    )


def test_three_claimants_reporting_one_wall_is_reported_as_one_wall() -> None:
    """The same insight `blocked_on` carries for blocked entries: twenty-seven entries waiting on
    one input is a different fact from twenty-seven problems, and so is this."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_release(
            catalog, f"agent-{i}", at=i * 10000.0, reason="the deposited model ships no rate laws"
        )
    diagnosis = entry.parking_diagnosis()
    assert f"All {PARK_AFTER_ATTEMPTS} who spoke gave the same reason" in diagnosis
    assert "ships no rate laws" in diagnosis


def test_different_reasons_are_all_reported() -> None:
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_release(catalog, f"agent-{i}", at=i * 10000.0, reason=f"wall {i}")
    diagnosis = entry.parking_diagnosis()
    for i in range(PARK_AFTER_ATTEMPTS):
        assert f"wall {i}" in diagnosis


def test_the_one_claimant_who_found_something_different_is_not_hidden() -> None:
    """Caught re-auditing the diff that added the reasons. Reporting only the most common one read
    as unanimity whenever it was not: three claimants naming one wall and a fourth naming another
    printed the first and dropped the second, so the claimant who found something *different* —
    the one worth reading — was exactly the one the summary hid.
    """
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_release(catalog, f"agent-{i}", at=i * 10000.0, reason="no runnable model")
    assert entry.is_parked()
    # Deliberately taken after the park, which is the only way a fourth claim happens.
    claim_work(catalog, {"requester": "agent-x", "include_parked": True}, at=90000.0)
    from reprolith.mcp_server import release_work

    release_work(
        catalog,
        {"accession": "A1", "requester": "agent-x", "reason": "the SED-ML names a missing output"},
    )
    diagnosis = entry.parking_diagnosis()
    assert "no runnable model" in diagnosis
    assert "the SED-ML names a missing output" in diagnosis
    assert f"no runnable model ({PARK_AFTER_ATTEMPTS})" in diagnosis, "the shared wall keeps its count"


def test_silence_is_reported_as_silence_not_as_an_absent_problem() -> None:
    """An attempt that ended by lease expiry had nobody there to say anything, and that is worth
    telling apart from a considered answer — otherwise a park with no reasons reads as a park
    whose reasons were unremarkable."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, f"agent-{i}", at=i * 100.0)
    assert "None of them said why" in entry.parking_diagnosis()
    assert "ended by lease expiry" in entry.parking_diagnosis()


def test_a_mix_says_how_many_said_nothing() -> None:
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    _claim_and_release(catalog, "agent-0", at=0.0, reason="no runnable model")
    _claim_and_abandon(catalog, "agent-1", at=10000.0)
    _claim_and_abandon(catalog, "agent-2", at=20000.0)
    diagnosis = entry.parking_diagnosis()
    assert "no runnable model" in diagnosis
    assert "2 ended by lease expiry, saying nothing" in diagnosis


def test_only_the_lease_holder_writes_the_outcome() -> None:
    """A release by anyone else is refused, so nothing can attribute a reason to a claimant who
    did not give one."""
    from reprolith.mcp_server import release_work

    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    claim_work(catalog, {"requester": "agent"}, at=0.0)
    refused = release_work(
        catalog, {"accession": "A1", "requester": "someone-else", "reason": "made up"}
    )
    assert refused == {"released": False, "reason": "not the lease holder"}
    assert entry.attempts[-1].outcome == ""


def test_a_reason_cannot_be_written_onto_an_attempt_already_handed_back() -> None:
    """The library-level guard, which the MCP refusal above never reaches: `release_lease` on an
    entry that is no longer leased must not attach a reason to whoever claimed it last. Otherwise
    a second release — or any caller with the object — backdates an explanation onto somebody
    else's attempt, and the diagnosis reports a wall that claimant never described."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    catalog.claim_next("agent", at=0.0, seconds=1.0)
    entry.release_lease("what actually stopped me")
    assert entry.attempts[-1].outcome == "what actually stopped me"
    entry.release_lease("a second, unattributable story")
    assert entry.attempts[-1].outcome == "what actually stopped me"


def test_a_release_without_a_reason_still_releases_and_says_it_recorded_none() -> None:
    from reprolith.mcp_server import release_work

    catalog = _catalog("A1")
    claim_work(catalog, {"requester": "agent"}, at=0.0)
    assert release_work(catalog, {"accession": "A1", "requester": "agent"}) == {
        "released": True,
        "reason_recorded": False,
    }


def test_an_outcome_survives_a_save_and_load() -> None:
    catalog = _catalog("A1")
    _claim_and_release(catalog, "agent", at=0.0, reason="no runnable model")
    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    entry = reloaded.find(Identifiers(title="", accession="A1"))
    assert entry.attempts[-1].outcome == "no runnable model"


def test_a_saved_attempt_that_the_bound_could_never_see_is_refused() -> None:
    """`_require_coherent_entry` exists because a hand-edited or badly merged catalog loads
    whatever it says, and it did not know about attempts. Parking compares an attempt's
    `progress_marker` against the history as it stands, so a marker past the end can never match:
    that attempt is invisible to the count for ever and the entry simply never parks — silently,
    which is the same shape of permanent wedge the lease-expiry check already guards.
    """
    import pytest

    catalog = _catalog("A1")
    for i in range(PARK_AFTER_ATTEMPTS):
        _claim_and_abandon(catalog, "agent", at=i * 100.0)
    record = catalog.to_dict()
    record["entries"][0]["attempts"][0]["progress_marker"] = 5
    with pytest.raises(ValueError, match="can never be compared"):
        Catalog.from_dict(json.loads(json.dumps(record)))


def test_a_negative_progress_marker_is_refused_too() -> None:
    import pytest

    catalog = _catalog("A1")
    _claim_and_abandon(catalog, "agent", at=0.0)
    record = catalog.to_dict()
    record["entries"][0]["attempts"][0]["progress_marker"] = -1
    with pytest.raises(ValueError, match="can never be compared"):
        Catalog.from_dict(json.loads(json.dumps(record)))


def test_a_coherent_attempt_record_still_loads() -> None:
    """The guard has to admit every record the writer produces, or it is a bound on saving."""
    catalog = _catalog("A1")
    entry = catalog.find(Identifiers(title="", accession="A1"))
    _claim_and_abandon(catalog, "agent", at=0.0)
    # The real path back to a second claim: an entry stops being claimable the moment it moves,
    # so it has to come back through the queue before anyone can take it again.
    entry.transition(
        LifecycleState.INGESTING, at="2026-09-06T00:00:00Z", actor="agent", reason="started"
    )
    entry.transition(
        LifecycleState.BLOCKED,
        at="2026-09-06T00:01:00Z",
        actor="agent",
        reason="missing",
        missing_inputs=("a supplement",),
    )
    entry.transition(
        LifecycleState.QUEUED, at="2026-09-06T00:02:00Z", actor="curator", reason="it arrived"
    )
    entry.release_lease()
    _claim_and_abandon(catalog, "agent", at=100.0)
    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    markers = [a.progress_marker for a in reloaded.find(Identifiers(title="", accession="A1")).attempts]
    assert markers == [0, 3], markers
    # And that second claim is the only one the retry bound can still see, because the three
    # transitions in between are exactly the progress that clears the run.
    assert len(reloaded.find(Identifiers(title="", accession="A1")).attempts_without_progress()) == 1
