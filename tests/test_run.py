"""The blind test-set run and agreement scoring (bootstrap tasks 7.1, 8.1)."""

from __future__ import annotations

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
