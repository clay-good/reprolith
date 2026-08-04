"""The read-only agent-facing query surface (bootstrap tasks 6.1, 6.3, 6.4)."""

from __future__ import annotations

from reprolith import (
    Catalog,
    CertificateLedger,
    ClaimAssessment,
    EnginePin,
    GroundTruth,
    Identifiers,
    LifecycleState,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    ReprolithQuery,
    Verdict,
    build_certificate,
)


def _cert(version: str = "4.42", verdict: Verdict = Verdict.REPRODUCED, qualified: bool = False,
          supersedes=None):
    return build_certificate(
        paper=PaperIdentity(title="Two-compartment PK model", doi="10.1/x"),
        engine_pin=EnginePin(engine="biosimulators/copasi", version=version),
        assessments=[
            ClaimAssessment(claim_id="c1", quantity="AUC", verdict=verdict, source_location="Fig 1",
                            assumption_qualified=qualified),
            ClaimAssessment(claim_id="c2", quantity="Cmax", verdict=Verdict.FAILED,
                            source_location="Fig 2", root_cause="ka ambiguous"),
        ],
        supersedes=supersedes,
    )


def _fixture() -> tuple[ReprolithQuery, Catalog, CertificateLedger, str]:
    catalog = Catalog()
    catalog.add(
        Identifiers(title="Two-compartment PK model", doi="10.1/x"),
        ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.PARTIALLY_REPRODUCED, source="curation"),
    )
    ledger = CertificateLedger()
    digest = ledger.issue(_cert())
    return ReprolithQuery(catalog, ledger), catalog, ledger, digest


# --- 6.1 queries change no state and return full qualifications --------------------


def test_queries_change_no_state() -> None:
    query, catalog, ledger, digest = _fixture()
    before_catalog = [e.to_dict() for e in catalog.entries]
    before_ledger = ledger.items()

    # Exercise every read path, repeatedly.
    for _ in range(2):
        query.list_catalog()
        query.status(doi="10.1/x")
        query.certificate(digest)
        query.verdict(digest)
        query.gaps(digest)
        query.certificates_for(doi="10.1/x")

    assert [e.to_dict() for e in catalog.entries] == before_catalog
    assert ledger.items() == before_ledger


def test_certificate_query_returns_full_qualifications() -> None:
    query, _, _, digest = _fixture()
    cert = query.certificate(digest)
    assert cert is not None
    # The per-claim verdicts, overall verdict, scope, and gaps all travel together.
    assert cert["verdict"]["overall"] == OverallVerdict.PARTIALLY_REPRODUCED.value
    assert cert["scope"]["machine"] == "reproducible-not-correct-not-clinical"
    assert {g["claim_id"] for g in cert["gaps"]} == {"c2"}


def test_unknown_lookups_return_none() -> None:
    query, _, _, _ = _fixture()
    assert query.status(doi="10.9/missing") is None
    assert query.certificate("0" * 64) is None
    assert query.verdict("0" * 64) is None
    assert query.gaps("0" * 64) is None


def test_catalog_query_is_blind_to_the_ground_truth_label() -> None:
    query, _, _, _ = _fixture()
    entries = query.list_catalog()
    assert entries and all("ground_truth" not in e for e in entries)
    status = query.status(doi="10.1/x")
    assert status is not None and "ground_truth" not in status


def test_catalog_query_filters() -> None:
    query, catalog, _, _ = _fixture()
    catalog.add(Identifiers(title="Some FBA model"), ModelClass.CONSTRAINT_BASED)
    assert len(query.list_catalog(model_class=ModelClass.ODE_PKPD)) == 1
    assert len(query.list_catalog(state=LifecycleState.QUEUED)) == 2


# --- 6.3 no code path returns a bare boolean --------------------------------------


def test_verdict_is_scope_qualified_never_a_bare_boolean() -> None:
    query, _, _, digest = _fixture()
    result = query.verdict(digest)
    assert not isinstance(result, bool)
    assert isinstance(result, dict)
    # The scope flag is inescapable, and the qualification structure travels with it.
    assert result["scope"]["machine"] == "reproducible-not-correct-not-clinical"
    assert "overall" in result and "claims" in result and "claim_counts" in result


def test_assumption_qualification_travels_in_the_verdict() -> None:
    catalog = Catalog()
    ledger = CertificateLedger()
    digest = ledger.issue(_cert(verdict=Verdict.REPRODUCED, qualified=True))
    query = ReprolithQuery(catalog, ledger)
    result = query.verdict(digest)
    assert result is not None
    assert result["assumption_qualified_claims"] == ["c1"]


# --- 6.4 parity: the surface reports the core's verdict, defines none of its own ---


def test_surface_verdict_matches_the_core_certificate() -> None:
    catalog = Catalog()
    ledger = CertificateLedger()
    cert = _cert()
    digest = ledger.issue(cert)
    query = ReprolithQuery(catalog, ledger)
    # The surface reads the certificate the core produced; it computes no verdict itself.
    assert query.verdict(digest)["overall"] == cert.overall.value
    assert query.certificate(digest)["overall"] == cert.overall.value


def test_certificates_for_lists_lineage_newest_first() -> None:
    catalog = Catalog()
    ledger = CertificateLedger()
    v1 = _cert("4.42")
    d1 = ledger.issue(v1)
    v2 = _cert("4.43", supersedes=v1)
    d2 = ledger.issue(v2)
    query = ReprolithQuery(catalog, ledger)
    assert query.certificates_for(doi="10.1/x") == [d2, d1]
