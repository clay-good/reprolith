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


def test_the_load_path_refuses_what_the_builder_refuses() -> None:
    """"The invariants hold for the ones read back off disk" was only half true.

    The load path re-derived the verdict and pinned the scope text, but not the other two: a
    stored estimation assessment with no protocol, or two assumptions sharing an id, loaded clean
    while `build_certificate` refuses both — and the public registry reads certificates from disk
    and never rebuilds them.
    """
    import pytest
    from reprolith import (
        Assumption,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        ReproductionLevel,
        Verdict,
        build_certificate,
        certificate_from_content,
    )

    base = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="c1", quantity="k", source_location="Table 1",
                            verdict=Verdict.REPRODUCED, level=ReproductionLevel.ESTIMATION,
                            protocol="Nelder-Mead from the paper's stated starting values"),
        ],
    )
    no_protocol = base.content()
    del no_protocol["assessments"][0]["protocol"]
    with pytest.raises(ValueError, match="must record the protocol"):
        certificate_from_content(no_protocol)

    twice = build_certificate(
        paper=PaperIdentity(title="p", doi="10.0/p"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[],
        assumptions=[Assumption(id="A", description="d", chosen="x", basis="b",
                                attributed_to="reprolith", load_bearing=False)],
    ).content()
    twice["assumptions"].append(dict(twice["assumptions"][0]))
    with pytest.raises(ValueError, match="appears twice"):
        certificate_from_content(twice)


def test_a_stored_miss_with_no_stated_cause_is_refused_on_the_way_in_and_out() -> None:
    """The judges require a cause for a non-pass; the builder and the load path did not.

    A stored `failed` with no cause loaded clean, and `render.gap_items` then explained it as
    "no evaluable output" — a reason invented for a claim the certificate says was evaluated and
    missed. The public registry reads certificates off disk and never rebuilds them.
    """
    import pytest
    from reprolith import (
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
    )
    from reprolith.persistence import certificate_from_content

    def assessment(**kw):
        return ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.FAILED,
                               source_location="Fig 1", **kw)

    def certificate(a):
        return build_certificate(paper=PaperIdentity(title="t", doi="10.0/t"),
                                 engine_pin=EnginePin(engine="e", version="1"), assessments=[a])

    for causeless in (assessment(), assessment(root_cause=""), assessment(root_cause="   ")):
        with pytest.raises(ValueError, match="has to say what missed"):
            certificate(causeless)

    good = certificate(assessment(root_cause="parameter-value-mismatch"))
    content = good.content()
    assert certificate_from_content(content).overall is good.overall
    # …and the same refusal on the way back in, from a hand-edited file.
    content["assessments"][0]["root_cause"] = None
    with pytest.raises(ValueError, match="has to say what missed"):
        certificate_from_content(content)


def test_a_stored_pin_that_contradicts_its_own_protocol_is_refused() -> None:
    """A certificate carried two accounts of what computed it, and nothing compared them.

    `certify_logical` refuses a pin claiming exhaustive enumeration over a space z3 searched. The
    load path did not, and both facts are on the certificate itself.
    """
    import pytest
    from reprolith import (
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
    )
    from reprolith.persistence import certificate_from_content

    honest = build_certificate(
        paper=PaperIdentity(title="big network", doi="10.0/b"),
        engine_pin=EnginePin(engine="reprolith-logical", version="0.0.1",
                             algorithm="synchronous-update, sat-fixed-points (z3 4.12)"),
        assessments=[ClaimAssessment(
            claim_id="ss", quantity="steady state", verdict=Verdict.REPRODUCED,
            source_location="Fig 1",
            protocol="60 nodes, SAT search (2^60 states is beyond exhaustive enumeration)",
        )],
    )
    content = honest.content()
    assert certificate_from_content(content).overall is honest.overall

    # Swapping the pin to the other path is refused…
    content["engine_pin"]["algorithm"] = "synchronous-update, exhaustive-state-enumeration"
    with pytest.raises(ValueError, match="does not name the solver that ran it"):
        certificate_from_content(content)
    # …and so is the easier edit: deleting the solver, leaving a pin that names no path at all.
    content["engine_pin"]["algorithm"] = "synchronous-update"
    with pytest.raises(ValueError, match="does not name the solver that ran it"):
        certificate_from_content(content)


def test_pruning_a_withdrawn_certificate_takes_its_badge_too() -> None:
    """The certificate and its render were withdrawn and the embeddable verdict badge was not."""
    import tempfile
    from pathlib import Path

    from reprolith.persistence import prune_certificate_directory

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for stem in ("KEPT", "WITHDRAWN"):
            for suffix in (".json", ".txt", ".svg"):
                (directory / f"{stem}{suffix}").write_text("x", encoding="utf-8")
        assert prune_certificate_directory(directory, ["KEPT"]) == ["WITHDRAWN"]
        assert sorted(p.name for p in directory.iterdir()) == [
            "KEPT.json", "KEPT.svg", "KEPT.txt"
        ]
