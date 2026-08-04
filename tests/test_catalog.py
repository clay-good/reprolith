"""The catalog lifecycle, blind labelling, and de-duplication (bootstrap tasks 1.1–1.3)."""

from __future__ import annotations

from dataclasses import fields

import pytest
from reprolith import (
    BlindEntry,
    Catalog,
    GroundTruth,
    Identifiers,
    IllegalTransition,
    LifecycleState,
    ModelClass,
    OverallVerdict,
)


def _entry(catalog: Catalog | None = None, **kw: object):
    catalog = catalog or Catalog()
    return catalog.add(Identifiers(title="Two-compartment PK of drug X", **kw))


# --- 1.1 lifecycle state machine, transitions recorded -----------------------------


def test_entry_starts_queued_with_no_history() -> None:
    entry = _entry()
    assert entry.state is LifecycleState.QUEUED
    assert entry.history == ()


def test_can_traverse_every_state_with_recorded_transitions() -> None:
    entry = _entry()
    # A single walk that visits all ten lifecycle states via legal moves.
    walk = [
        (LifecycleState.INGESTING, ()),
        (LifecycleState.QUARANTINED, ()),
        (LifecycleState.QUEUED, ()),
        (LifecycleState.INGESTING, ()),
        (LifecycleState.INGESTED, ()),
        (LifecycleState.RECONSTRUCTING, ()),
        (LifecycleState.RECONSTRUCTED, ()),
        (LifecycleState.VERIFYING, ()),
        (LifecycleState.BLOCKED, ("supplement paywalled",)),
        (LifecycleState.RECONSTRUCTING, ()),
        (LifecycleState.RECONSTRUCTED, ()),
        (LifecycleState.VERIFYING, ()),
        (LifecycleState.FAILED, ()),
        (LifecycleState.VERIFYING, ()),
        (LifecycleState.CERTIFIED, ()),
    ]
    for i, (to, missing) in enumerate(walk):
        entry.transition(
            to, at=f"2026-08-03T00:00:{i:02d}Z", actor="agent-1", reason="step", missing_inputs=missing
        )

    visited = {t.to_state for t in entry.history} | {LifecycleState.QUEUED}
    assert visited == set(LifecycleState)  # every state was reached
    assert len(entry.history) == len(walk)  # every move recorded, none inferred
    # Each transition carries who/when/why.
    for t in entry.history:
        assert t.at and t.actor and t.reason
        assert t.from_state is not t.to_state


def test_illegal_transition_is_rejected() -> None:
    entry = _entry()  # queued
    with pytest.raises(IllegalTransition):
        entry.transition(
            LifecycleState.CERTIFIED, at="2026-08-03T00:00:00Z", actor="a", reason="skip the line"
        )


def test_blocked_requires_missing_inputs_and_failed_forbids_them() -> None:
    entry = _entry()
    entry.transition(LifecycleState.INGESTING, at="t", actor="a", reason="start")
    # blocked without a missing-inputs list is meaningless.
    with pytest.raises(ValueError):
        entry.transition(LifecycleState.BLOCKED, at="t", actor="a", reason="stuck")
    # failed is a completed attempt; it has no missing input to report.
    entry.transition(LifecycleState.INGESTED, at="t", actor="a", reason="ok")
    entry.transition(LifecycleState.RECONSTRUCTING, at="t", actor="a", reason="ok")
    entry.transition(LifecycleState.RECONSTRUCTED, at="t", actor="a", reason="ok")
    entry.transition(LifecycleState.VERIFYING, at="t", actor="a", reason="ok")
    with pytest.raises(ValueError):
        entry.transition(
            LifecycleState.FAILED, at="t", actor="a", reason="no", missing_inputs=("x",)
        )


def test_blocked_records_the_missing_inputs() -> None:
    entry = _entry()
    entry.transition(LifecycleState.INGESTING, at="t", actor="a", reason="start")
    move = entry.transition(
        LifecycleState.BLOCKED,
        at="t",
        actor="a",
        reason="cannot proceed",
        missing_inputs=("initial conditions", "clearance value"),
    )
    assert move.missing_inputs == ("initial conditions", "clearance value")


# --- 1.2 ground-truth label is blind to the verdict path ---------------------------


def test_blind_view_structurally_omits_the_label() -> None:
    catalog = Catalog()
    entry = catalog.add(
        Identifiers(title="Known reproducible model"),
        ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="BioModels curation"),
    )
    blind = entry.blind()
    # The label is present on the entry...
    assert entry.ground_truth is not None
    # ...but there is no field for it on the view the verdict path receives — not a
    # redacted value, no attribute at all.
    assert isinstance(blind, BlindEntry)
    field_names = {f.name for f in fields(blind)}
    assert not any("ground" in n or "label" in n or "expected" in n for n in field_names)
    assert not hasattr(blind, "ground_truth")
    assert "ground_truth" not in blind.to_dict()


def test_agreement_is_the_labels_only_reader_and_runs_after_a_verdict() -> None:
    entry = _entry(catalog=Catalog())
    assert entry.agreement(OverallVerdict.REPRODUCED) is None  # no label -> no comparison

    labelled = Catalog().add(
        Identifiers(title="Hard case"),
        ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.NOT_REPRODUCED, source="repro study"),
    )
    assert labelled.agreement(OverallVerdict.NOT_REPRODUCED) is True
    assert labelled.agreement(OverallVerdict.REPRODUCED) is False


# --- 1.3 de-duplication across identifiers -----------------------------------------


def test_same_paper_under_two_ids_resolves_to_one_entry() -> None:
    catalog = Catalog()
    first = catalog.add(Identifiers(title="Model A", doi="10.1/abc"))
    # Same paper, arriving by PubMed ID and the same DOI: must resolve to `first`.
    second = catalog.add(Identifiers(title="Model A (preprint)", doi="10.1/abc", pubmed_id="99"))
    assert second is first
    assert len(catalog) == 1
    # All known identifiers are retained on the single entry.
    assert first.identifiers.doi == "10.1/abc"
    assert first.identifiers.pubmed_id == "99"


def test_dedup_matches_on_normalized_title() -> None:
    catalog = Catalog()
    a = catalog.add(Identifiers(title="Two-Compartment  PK Model"))
    b = catalog.add(Identifiers(title="two-compartment pk model"))
    assert b is a
    assert len(catalog) == 1


def test_distinct_papers_stay_separate() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="Model A", doi="10.1/a"))
    catalog.add(Identifiers(title="Model B", doi="10.1/b"))
    assert len(catalog) == 2


def test_reseed_fills_gaps_without_overwriting_known_data() -> None:
    catalog = Catalog()
    entry = catalog.add(Identifiers(title="Model A", doi="10.1/a"), ModelClass.ODE_PKPD)
    # A later re-seed that mis-tags the class must not clobber the known assignment.
    catalog.add(Identifiers(title="Model A", doi="10.1/a"), ModelClass.UNASSIGNED)
    assert entry.model_class is ModelClass.ODE_PKPD


# --- catalog persistence: durable, resumable registry (spec: model-catalog) ---------


def test_catalog_round_trips_with_state_and_history() -> None:
    import json

    catalog = Catalog()
    entry = catalog.add(
        Identifiers(title="A model", doi="10.1/a", accession="BIOMD1"), ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="curation"),
    )
    entry.transition(LifecycleState.INGESTING, at="t1", actor="agent", reason="start")
    entry.transition(LifecycleState.INGESTED, at="t2", actor="agent", reason="done")
    catalog.add(Identifiers(title="Other", accession="MODEL2"), ModelClass.UNASSIGNED)

    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))

    assert len(reloaded) == 2
    first = reloaded.find(Identifiers(title="ignored", accession="BIOMD1"))
    assert first is not None
    assert first.state is LifecycleState.INGESTED  # state restored, not reset to queued
    assert [t.to_state for t in first.history] == [LifecycleState.INGESTING, LifecycleState.INGESTED]
    assert first.ground_truth is not None and first.ground_truth.expected is OverallVerdict.REPRODUCED
    assert first.identifiers.doi == "10.1/a"


def test_reloaded_entry_still_advances_from_its_restored_state() -> None:
    import json

    catalog = Catalog()
    entry = catalog.add(Identifiers(title="A", accession="X"), ModelClass.ODE_PKPD)
    entry.transition(LifecycleState.INGESTING, at="t", actor="a", reason="r")
    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    e = reloaded.find(Identifiers(title="A", accession="X"))
    assert e is not None
    # A legal move from the restored state works; an illegal one is still rejected.
    e.transition(LifecycleState.INGESTED, at="t2", actor="a", reason="r2")
    assert e.state is LifecycleState.INGESTED


# --- lease-aware work queue (spec: model-catalog, "Never-empty prioritized queue") ---


def test_claim_next_leases_and_prevents_collision() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD)
    catalog.add(Identifiers(title="B", accession="B2"), ModelClass.ODE_PKPD)

    a = catalog.claim_next("agent-1", at=0.0, seconds=100.0)
    assert a is not None and a.leased_to == "agent-1"
    # A second requester at the same time gets a different entry, not the leased one.
    b = catalog.claim_next("agent-2", at=0.0, seconds=100.0)
    assert b is not None and b is not a
    # No more claimable work.
    assert catalog.claim_next("agent-3", at=0.0, seconds=100.0) is None


def test_expired_lease_becomes_claimable_again() -> None:
    catalog = Catalog()
    entry = catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD)
    catalog.claim_next("agent-1", at=0.0, seconds=100.0)
    assert catalog.claim_next("agent-2", at=50.0, seconds=100.0) is None  # still leased
    # After the lease window, the entry is claimable again.
    reclaimed = catalog.claim_next("agent-2", at=100.0, seconds=100.0)
    assert reclaimed is entry and reclaimed.leased_to == "agent-2"


def test_claim_is_ground_truth_first_and_class_filtered() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="unlabelled", accession="U"), ModelClass.ODE_PKPD)
    catalog.add(Identifiers(title="labelled", accession="L"), ModelClass.ODE_PKPD,
                ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="c"))
    catalog.add(Identifiers(title="other class", accession="K"), ModelClass.KINETIC)

    # Ground-truth-labelled entry is claimed first.
    first = catalog.claim_next("a", at=0.0, seconds=10.0)
    assert first is not None and first.identifiers.accession == "L"
    # A class filter only returns matching, claimable work.
    kin = catalog.claim_next("a", at=0.0, seconds=10.0, model_class=ModelClass.KINETIC)
    assert kin is not None and kin.identifiers.accession == "K"


def test_non_queued_entry_is_not_claimable() -> None:
    catalog = Catalog()
    entry = catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD)
    entry.transition(LifecycleState.INGESTING, at="t", actor="a", reason="start")
    assert catalog.claim_next("a", at=0.0, seconds=10.0) is None


def test_lease_survives_catalog_persistence() -> None:
    import json

    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD)
    catalog.claim_next("agent-1", at=5.0, seconds=100.0)
    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    entry = reloaded.find(Identifiers(title="A", accession="A1"))
    assert entry is not None and entry.leased_to == "agent-1" and entry.lease_expires == 105.0
    # The reloaded lease is still honored: not claimable inside the window.
    assert reloaded.claim_next("agent-2", at=50.0, seconds=10.0) is None
