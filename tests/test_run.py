"""The blind test-set run and agreement scoring (bootstrap tasks 7.1, 8.1)."""

from __future__ import annotations

import pytest
from reprolith import (
    Catalog,
    ClaimAssessment,
    EnginePin,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    blocked_certificate,
    build_certificate,
    run_test_set,
)

PIN = EnginePin(engine="copasi", version="4.46")


def test_blocked_certificate_abstains_with_a_recorded_reason() -> None:
    cert = blocked_certificate(PaperIdentity(title="t"), PIN)
    assert cert.overall is OverallVerdict.BLOCKED  # abstains, does not fail
    assert cert.gap_report and "claim" in cert.gap_report[0]


def test_every_entry_yields_a_certificate() -> None:
    catalog = Catalog()
    catalog.add(
        Identifiers(title="model A", accession="BIOMD1"), ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="curation"),
    )
    catalog.add(
        Identifiers(title="model B", accession="MODEL2"), ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.NOT_REPRODUCED, source="non-curated"),
    )

    # We have a real certificate for A only; B is abstained (blocked).
    cert_a = build_certificate(
        paper=PaperIdentity(title="model A"), engine_pin=PIN,
        assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
    )
    certs, report = run_test_set(catalog.entries, engine_pin=PIN, certified={"BIOMD1": cert_a})

    # Every entry has a certificate.
    assert len(certs) == 2
    assert certs[0] is cert_a
    assert certs[1].overall is OverallVerdict.BLOCKED  # B abstained

    # Agreement is scored honestly: A reproduced (agrees), B blocked (abstained, disagrees).
    assert report.total == 2
    by_entry = {e.entry: e for e in report.per_entry}
    assert by_entry["BIOMD1"].agree is True
    assert by_entry["MODEL2"].actual == "blocked" and by_entry["MODEL2"].agree is False


def test_run_is_reproducible() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="BIOMD1"), ModelClass.ODE_PKPD,
                ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="c"))
    a = run_test_set(catalog.entries, engine_pin=PIN)[1].to_dict()
    b = run_test_set(catalog.entries, engine_pin=PIN)[1].to_dict()
    assert a == b


def test_run_advances_lifecycle_and_survives_persistence() -> None:
    # The blind run records each entry's lifecycle to its outcome, and the resulting catalog
    # state survives a save/load round trip (the durable registry reflects the run).
    import json

    from reprolith import Catalog, LifecycleState

    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="BIOMD1"), ModelClass.ODE_PKPD,
                ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="c"))
    catalog.add(Identifiers(title="B", accession="MODEL2"), ModelClass.ODE_PKPD,
                ground_truth=GroundTruth(expected=OverallVerdict.NOT_REPRODUCED, source="c"))

    cert_a = build_certificate(
        paper=PaperIdentity(title="A"), engine_pin=PIN,
        assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="T1")],
    )
    run_test_set(catalog.entries, engine_pin=PIN, certified={"BIOMD1": cert_a}, advance=True)

    reloaded = Catalog.from_dict(json.loads(json.dumps(catalog.to_dict())))
    a = reloaded.find(Identifiers(title="A", accession="BIOMD1"))
    b = reloaded.find(Identifiers(title="B", accession="MODEL2"))
    assert a is not None and a.state is LifecycleState.CERTIFIED
    assert b is not None and b.state is LifecycleState.BLOCKED
    # The blocked entry records the precise missing input.
    assert any(t.missing_inputs for t in b.history)


def test_advance_is_idempotent_for_a_non_queued_entry() -> None:
    from reprolith import Catalog, LifecycleState, advance_to_outcome

    catalog = Catalog()
    entry = catalog.add(Identifiers(title="A", accession="X"), ModelClass.ODE_PKPD)
    advance_to_outcome(entry, OverallVerdict.BLOCKED, at="t", actor="a")
    n = len(entry.history)
    advance_to_outcome(entry, OverallVerdict.BLOCKED, at="t", actor="a")  # already advanced
    assert entry.state is LifecycleState.BLOCKED and len(entry.history) == n


def test_advance_maps_not_reproduced_to_failed() -> None:
    from reprolith import Catalog, LifecycleState, advance_to_outcome

    catalog = Catalog()
    entry = catalog.add(Identifiers(title="A", accession="X"), ModelClass.ODE_PKPD)
    advance_to_outcome(entry, OverallVerdict.NOT_REPRODUCED, at="t", actor="a")
    assert entry.state is LifecycleState.FAILED
    # A failed attempt ran to completion, so it records no missing input.
    assert all(not t.missing_inputs for t in entry.history)


def test_a_certificate_for_another_paper_is_refused_when_no_side_states_an_identifier() -> None:
    """Five of the six classes certify models with no DOI and no PubMed ID.

    The guard compared doi/pubmed only when *both* sides stated one, so for 29 of the 30 published
    certificates it compared nothing: a certificate filed under the wrong accession was accepted in
    silence, scored against that other paper's ground-truth label, and the run still reported full
    agreement. The title is the only thing left that tells the two apart.
    """
    from reprolith import Certificate, EnginePin, OverallVerdict, PaperIdentity, Scope
    from reprolith.catalog import Catalog, Identifiers, ModelClass
    from reprolith.run import require_same_paper

    catalog = Catalog()
    entry = catalog.add(Identifiers(title="Kholodenko2000 MAPK cascade", accession="BIOMD10"),
                        ModelClass.KINETIC)
    other = Certificate(
        paper=PaperIdentity(title="Elowitz2000 repressilator", doi=""),
        engine_pin=EnginePin(engine="e", version="1"),
        overall=OverallVerdict.BLOCKED, scope=Scope(), assessments=(), assumptions=(),
    )
    with pytest.raises(ValueError, match="different paper"):
        require_same_paper(entry, other, "BIOMD10")

    # …and the variation the doi-only rule existed to tolerate still passes: one record naming the
    # paper more fully than the other is one paper, not two.
    fuller = Certificate(
        paper=PaperIdentity(title="Kholodenko2000 MAPK cascade (oscillatory signaling)", doi=""),
        engine_pin=EnginePin(engine="e", version="1"),
        overall=OverallVerdict.BLOCKED, scope=Scope(), assessments=(), assumptions=(),
    )
    require_same_paper(entry, fuller, "BIOMD10")


def test_the_title_rule_accepts_an_inserted_word_and_refuses_a_reordering() -> None:
    """Contiguity was the wrong lever and a token set was too loose.

    A set comparison made word order free, so two different papers matched. Requiring the words to
    be *contiguous* then refused the ordinary variation — an inserted word — including the example
    this module's own docstring gives. And any subsequence rule needs a length floor, or a one-word
    title names every paper containing that word.
    """
    from reprolith.run import _is_word_subsequence, _title_tokens

    def names_the_same_paper(one: str, other: str) -> bool:
        ours, theirs = _title_tokens(one), _title_tokens(other)
        return bool(ours) and bool(theirs) and (
            _is_word_subsequence(ours, theirs) or _is_word_subsequence(theirs, ours)
        )

    assert names_the_same_paper("E. coli core model", "E. coli core metabolic model")
    assert names_the_same_paper("E. coli core", "E. coli core metabolic model")
    assert names_the_same_paper(
        "Effect of insulin on glucose uptake", "Effect of insulin on hepatic glucose uptake"
    )
    # Two different papers, same words, different order.
    assert not names_the_same_paper(
        "Effect of insulin on glucose uptake", "Effect of glucose on insulin uptake"
    )
    # Too short to witness anything.
    assert not names_the_same_paper("model", "A model of glycolytic oscillations")
    assert not names_the_same_paper("cell cycle", "The cell cycle in fission yeast")
