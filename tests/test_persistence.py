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


def test_dossier_round_trips_through_json() -> None:
    import json

    from reprolith import (
        Dossier,
        DossierClaim,
        Equation,
        ExtractionConfidence,
        Gap,
        GapKind,
        ModelArtifact,
        Parameter,
        dossier_digest,
        dossier_from_dict,
    )

    dossier = Dossier(
        entry="10.1/x",
        state_variables=("A_gut", "A_central"),
        equations=(Equation(target="A_central", expression="ka*A_gut - ke*A_central",
                            source_location="Eq 1"),),
        parameters=(Parameter(name="ke", value=0.1, unit="1/h", source_location="Table 1",
                              confidence=ExtractionConfidence.INTERPRETED),),
        initial_conditions=(Parameter(name="A_gut", value=100.0, unit="mg", source_location="M"),),
        claims=(DossierClaim(id="C1", quantity="AUC", conditions="100mg", source_location="T2",
                             reference_kind=ReferenceKind.NUMERIC, reference_data=(1.0, 2.0)),
                DossierClaim(id="S1", quantity="schematic", conditions="", source_location="F1",
                             targetable=False),),
        gaps=(Gap(element="CL", kind=GapKind.PARAMETER, detail="unreported", load_bearing=True),),
        artifacts=(ModelArtifact(filename="m.xml", detected_format="sbml", validates=True),),
    )
    reloaded = dossier_from_dict(json.loads(json.dumps(dossier.to_dict())))
    assert reloaded.to_dict() == dossier.to_dict()
    assert dossier_digest(reloaded) == dossier_digest(dossier)
    assert reloaded.parameters[0].confidence is ExtractionConfidence.INTERPRETED
    assert reloaded.claims[0].reference_kind is ReferenceKind.NUMERIC


def test_bundle_round_trips_through_json() -> None:
    import json

    from reprolith import (
        Assumption,
        EnginePin,
        ModelArtifact,
        ModelOrigin,
        NonReconstructable,
        RecipeStep,
        ReconstructionBundle,
        bundle_from_dict,
    )

    bundle = ReconstructionBundle(
        entry="10.1/x",
        engine_pin=EnginePin(engine="copasi", version="4.46", algorithm="lsoda"),
        model=ModelArtifact(filename="author.xml", detected_format="sbml", validates=True),
        origin=ModelOrigin.AUTHOR_SUPPLIED,
        recipe=(RecipeStep(claim_id="C1", protocol="100mg IV", output="AUC", time_span="0-24h"),),
        assumptions=(Assumption(id="k", description="ka", chosen="1.2", basis="typical",
                                load_bearing=True, alternatives=("0.9",)),),
        non_reconstructable=(NonReconstructable(claim_id="C2", reason="no protocol"),),
        mismatches=("Eq 2 vs Table 1",),
        source_dossier="10.1/x",
    )
    reloaded = bundle_from_dict(json.loads(json.dumps(bundle.to_dict())))
    assert reloaded.to_dict() == bundle.to_dict()
    assert reloaded.origin is ModelOrigin.AUTHOR_SUPPLIED
    assert reloaded.load_bearing_assumptions()[0].id == "k"


def test_a_stored_verdict_that_does_not_follow_from_its_evidence_is_refused() -> None:
    """The honesty invariants must hold for a certificate read off disk, not only one just built."""
    import pytest

    cert = build_certificate(
        paper=PaperIdentity(title="P", doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[
            ClaimAssessment(
                claim_id="c1", quantity="Cmax", verdict=Verdict.REPRODUCED,
                source_location="Table 1", assumption_qualified=True,
            )
        ],
    )
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    content = cert.content()
    assert certificate_from_content(content).overall is OverallVerdict.PARTIALLY_REPRODUCED

    # Hand-edited to claim a clean pass over an assumption-qualified claim.
    content["overall"] = "reproduced"
    with pytest.raises(ValueError, match="does not follow"):
        certificate_from_content(content)


def test_pruning_withdraws_a_certificate_the_run_no_longer_produces(tmp_path) -> None:
    # A milestone runner writes one file per entry and never cleared what was there before, so an
    # entry withdrawn from a reference set stayed published — counted by the registry while the
    # self-validation report beside it did not count it.
    from reprolith.persistence import prune_certificate_directory

    for stem in ("kept", "withdrawn"):
        (tmp_path / f"{stem}.json").write_text("{}", encoding="utf-8")
        (tmp_path / f"{stem}.txt").write_text("", encoding="utf-8")
    (tmp_path / "notes.md").write_text("", encoding="utf-8")

    assert prune_certificate_directory(tmp_path, {"kept"}) == ["withdrawn"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["kept.json", "kept.txt", "notes.md"]
