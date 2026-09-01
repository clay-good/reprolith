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


def test_an_estimation_level_pass_is_visible_in_the_verdict_summary() -> None:
    """The summary must not read as a clean simulation pass when the claim was re-fitted.

    `derive_overall` deliberately ignores the reproduction level, so `overall`, `claim_counts`,
    and `assumption_qualified_claims` all look clean for an estimation-level reproduction. Every
    other rendering flags it; this one silently did not.
    """
    from reprolith import (
        Certificate,
        ClaimAssessment,
        ComparisonMethod,
        EnginePin,
        PaperIdentity,
        ReferenceKind,
        ReproductionLevel,
        Verdict,
        build_certificate,
    )
    from reprolith.query import ReprolithQuery

    assessment = ClaimAssessment(
        claim_id="k_el", quantity="elimination rate", source_location="Table 1",
        verdict=Verdict.REPRODUCED, method=ComparisonMethod.SCALAR_RELATIVE_ERROR,
        discrepancy="relative error 0.0100", tolerance="reproduced<=0.1, partial<=0.25",
        tolerance_source="class-default", reference_kind=ReferenceKind.NUMERIC,
        level=ReproductionLevel.ESTIMATION,
        protocol="Nelder-Mead least squares from the paper's stated starting values",
    )
    cert: Certificate = build_certificate(
        paper=PaperIdentity(title="re-fitted", doi="10.0/e"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[assessment],
    )
    view = ReprolithQuery._verdict_view(cert)
    assert view["overall"] == "reproduced"
    assert view["estimation_claims"] == ["k_el"]


def test_backlog_health_judges_leases_against_now_not_the_epoch() -> None:
    """An expired lease used to block a claimable entry forever, in both published surfaces."""
    import time

    from reprolith.catalog import Catalog, Identifiers, ModelClass
    from reprolith.query import ReprolithQuery
    from reprolith.supersession import CertificateLedger

    catalog = Catalog()
    catalog.add(Identifiers(title="a paper", accession="ACC0"), model_class=ModelClass.ODE_PKPD)
    claimed = catalog.claim_next("agentA", at=time.time() - 10_000, seconds=10)
    assert claimed is not None
    query = ReprolithQuery(catalog=catalog, ledger=CertificateLedger())
    assert query.backlog_health()["claimable"] == len(catalog.claimable(time.time()))


def test_the_gaps_view_carries_a_failures_whole_cause() -> None:
    """The agent-facing surface reads `gap_items`, so it inherits whatever the render publishes.

    Two human-facing surfaces were found today stating a failure's cause with most of it missing.
    This one was already right — it is pinned so a change to `gap_items` cannot quietly strip the
    evidence from the surface an agent reads without a person seeing it.
    """
    import json
    from pathlib import Path

    from reprolith.mcp_server import load_repository

    root = Path(__file__).parent.parent
    query, _ = load_repository(root / "datasets" / "milestone")
    certificate = json.loads(
        (root / "datasets/milestone/certificates/BIOMD0000001029.json").read_text(encoding="utf-8")
    )
    failed = next(a for a in certificate["assessments"] if a["verdict"] == "failed")
    (digest,) = query.certificates_for(accession="BIOMD0000001029")

    item = next(
        g for g in query.gaps(digest)["gaps"] if g["claim_id"] == failed["claim_id"]
    )
    for part in (failed["discrepancy"], failed["root_cause"], failed["implicated"]):
        assert part in item["needs"], part
    assert f"fault hypothesis: {failed['fault_hypothesis']}" in item["needs"]


def test_the_verdict_summary_names_the_assumption_and_not_only_the_claims_it_qualified() -> None:
    """Third instance of one hole: the summary named the claims and never the value.

    `assumption_qualified_claims` lists twenty-three ids on the shipped metformin certificate and
    leaves out the one sentence that explains the verdict — that Reprolith assumed the stated doses
    are the hydrochloride salt. The human certificate carries it, so does the gap report, so does
    the pre-submission fix list; this is the surface an agent reads to decide whether to cite the
    certificate at all, and it carried the qualification without what qualified it. The same shape
    was already closed twice here, for estimation-level passes and for gap notes.

    Only the assumptions that withhold a clean pass are carried, which is the pair `derive_overall`
    itself consults: a non-load-bearing assumption with nothing to verify does not move the verdict
    and does not belong beside it.
    """
    from reprolith import (
        Assumption,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
    )
    from reprolith.query import ReprolithQuery

    cert = build_certificate(
        paper=PaperIdentity(title="salt form", doi="10.0/s"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="Cmax", quantity="peak", source_location="Table 6",
                            verdict=Verdict.REPRODUCED, assumption_qualified=True),
        ],
        assumptions=[
            Assumption(id="salt", description="the stated doses are metformin HCl",
                       chosen="each dose x 129.16/165.62", basis="the paper's own methods",
                       attributed_to="reprolith", load_bearing=True),
            Assumption(id="route", description="the elimination route", chosen="renal",
                       basis="convention", attributed_to="reprolith", load_bearing=False),
        ],
    )
    view = ReprolithQuery._verdict_view(cert)
    assert view["assumption_qualified_claims"] == ["Cmax"]
    assert [a["id"] for a in view["qualifying_assumptions"]] == ["salt"]
    assert view["qualifying_assumptions"][0]["chosen"] == "each dose x 129.16/165.62"
