"""Reloading a certificate from its stored content (design goal 3: inspectable files)."""

from __future__ import annotations

import json

from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    ReferenceKind,
    Verdict,
    build_certificate,
    certificate_digest,
    certificate_from_content,
)


def _rich_certificate():
    return build_certificate(
        paper=PaperIdentity(title="Two-compartment PK model", doi="10.1/x", pubmed_id="42"),
        engine_pin=EnginePin(engine="copasi", version="4.46", algorithm="deterministic-lsoda"),
        assessments=[
            ClaimAssessment(claim_id="a", quantity="AUC", verdict=Verdict.REPRODUCED,
                            source_location="Table 2", method="relative error", tolerance="5%",
                            reference_kind=ReferenceKind.NUMERIC.value, assumption_qualified=True),
            ClaimAssessment(claim_id="b", quantity="Cmax", verdict=Verdict.FAILED,
                            source_location="Fig 3", discrepancy="12% high", root_cause="ka ambiguous",
                            implicated="absorption rate", fault_hypothesis="manuscript"),
            ClaimAssessment(claim_id="c", quantity="t1/2", verdict=Verdict.NOT_EVALUABLE,
                            source_location="Fig 4"),
        ],
        assumptions=[Assumption(id="k1", description="ka", chosen="1.2", basis="typical",
                                load_bearing=True, alternatives=("0.9", "1.5"))],
        gap_report=("dosing schedule ambiguous",),
    )


def test_content_round_trips_byte_identically() -> None:
    cert = _rich_certificate()
    reloaded = certificate_from_content(cert.content())
    assert reloaded.content() == cert.content()
    assert certificate_digest(reloaded) == certificate_digest(cert)


def test_reloaded_verdict_is_taken_from_storage_not_re_derived() -> None:
    cert = _rich_certificate()
    reloaded = certificate_from_content(cert.content())
    # A mixed result: the stored overall verdict is preserved exactly.
    assert reloaded.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert reloaded.overall is cert.overall


def test_survives_a_json_file_round_trip() -> None:
    cert = _rich_certificate()
    # The content is plain JSON, so it round-trips through a file (design goal 3).
    text = json.dumps(cert.content())
    reloaded = certificate_from_content(json.loads(text))
    assert certificate_digest(reloaded) == certificate_digest(cert)
    # Structured fields survive: assessments, assumptions, gaps, scope.
    assert [a.claim_id for a in reloaded.assessments] == ["a", "b", "c"]
    assert reloaded.assumptions[0].alternatives == ("0.9", "1.5")
    assert reloaded.assessments[1].fault_hypothesis == "manuscript"
    assert reloaded.scope.machine == "reproducible-not-correct-not-clinical"
