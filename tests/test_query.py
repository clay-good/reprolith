"""The read-only agent-facing query surface (bootstrap tasks 6.1, 6.3, 6.4)."""

from __future__ import annotations

import json

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


def test_the_track_record_publishes_its_numbers_without_the_answer_key() -> None:
    """The blindness rule is about the label's value, wherever it appears — not one field name.

    A committed agreement report pairs each accession with its ground-truth label, and those
    accessions are the same ones sitting in the live work queue. Published verbatim, the track
    record would hand a reproducing agent the answer for the paper it is about to claim.
    """
    from reprolith.query import self_validation_summary

    reports = {
        "ode-pkpd": {
            "per_entry": [
                {"entry": "BIOMD0000000765", "expected": "reproduced", "actual": "blocked",
                 "agree": False},
            ],
            "total": 1, "agreements": 0, "disagreements": 1, "agreement_rate": 0.0,
            "confusion": {"reproduced->blocked": 1},
        }
    }
    summary = self_validation_summary(reports)
    serialized = json.dumps(summary)
    assert "BIOMD0000000765" not in serialized
    assert "expected" not in serialized
    # The aggregate track record survives intact, abstention counted as abstention.
    assert summary["by_class"]["ode-pkpd"]["total"] == 1
    assert summary["by_class"]["ode-pkpd"]["confusion"] == {"reproduced->blocked": 1}
    assert summary["overall"] == {
        "classes": 1, "labelled_entries": 1, "agreements": 0,
        "abstentions": 1, "other_disagreements": 0,
    }


def _paper_cert(title, verdict, supersedes=None):
    return build_certificate(
        paper=PaperIdentity(title=title, doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(
            claim_id="c1", quantity="Cmax", verdict=verdict, source_location="T1",
            root_cause=None if verdict is Verdict.REPRODUCED else "the paper omits clearance",
        )],
        supersedes=supersedes,
    )


def test_a_superseded_verdict_is_never_served_as_the_current_answer() -> None:
    """A reader holding a digest — the identity the project asks people to cite — must be told."""
    from reprolith import Catalog, CertificateLedger, certificate_digest

    ledger = CertificateLedger()
    old = _paper_cert("One paper", Verdict.REPRODUCED)
    ledger.issue(old)
    new = _paper_cert("One paper", Verdict.FAILED, supersedes=old)
    ledger.issue(new)
    query = ReprolithQuery(Catalog(), ledger)

    assert query.verdict(certificate_digest(old))["superseded_by"] == certificate_digest(new)
    assert query.certificate(certificate_digest(old))["superseded_by"] == certificate_digest(new)
    assert query.verdict(certificate_digest(new))["superseded_by"] is None


def test_the_current_certificate_leads_even_when_a_middle_link_was_never_published() -> None:
    """Without the missing link, the superseded root looks like a head; order must not be arbitrary."""
    from reprolith import Catalog, CertificateLedger, certificate_digest

    root = _paper_cert("One paper", Verdict.REPRODUCED)
    middle = _paper_cert("One paper", Verdict.FAILED, supersedes=root)
    current = _paper_cert("One paper", Verdict.FAILED, supersedes=middle)
    for order in ((root, current), (current, root)):
        ledger = CertificateLedger()
        for cert in order:
            ledger.issue(cert)
        digests = ReprolithQuery(Catalog(), ledger).certificates_for(title="One paper")
        # The deeper chain leads, whichever order the ledger happens to hold them in.
        assert digests[0] == certificate_digest(current), order
