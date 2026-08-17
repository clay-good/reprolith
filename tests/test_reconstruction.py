"""Reconstruction bundle shape and gap-closure discipline (task 0.2 shape; 3.2-3.4)."""

from __future__ import annotations

from reprolith import (
    ClaimAssessment,
    Dossier,
    DossierClaim,
    EnginePin,
    Gap,
    GapKind,
    ModelArtifact,
    ModelOrigin,
    NonReconstructable,
    OverallVerdict,
    RecipeStep,
    ReconstructionBundle,
    Verdict,
    build_certificate,
    close_gap,
)
from reprolith.model import PaperIdentity

PIN = EnginePin(engine="biosimulators/copasi", version="4.42")


# --- 0.2 an empty example validates against its shape ------------------------------


def test_minimal_bundle_is_valid() -> None:
    bundle = ReconstructionBundle(entry="10.1/x", engine_pin=PIN)
    assert bundle.validate() == []
    assert bundle.to_dict()["engine_pin"]["engine"] == "biosimulators/copasi"


# --- 3.2 gap-closures are assumptions attributed to Reprolith, not the paper -------


def test_close_gap_attributes_to_reprolith_with_basis_and_alternatives() -> None:
    gap = Gap(element="initial gut amount", kind=GapKind.INITIAL_CONDITION,
              detail="not stated in Methods")
    a = close_gap(gap, chosen="full dose in gut", basis="oral bolus is the stated route",
                  alternatives=("split between gut and central",))
    assert a.attributed_to == "reprolith"  # never the paper's own value
    assert a.basis and a.alternatives == ("split between gut and central",)
    assert a.description.startswith("gap-closure for initial gut amount")


# --- 3.3 load-bearing gaps yield load-bearing assumptions --------------------------


def test_load_bearing_gap_yields_load_bearing_assumption() -> None:
    heavy = Gap(element="absorption rate ka", kind=GapKind.PARAMETER,
                detail="unreported", load_bearing=True)
    light = Gap(element="observation unit", kind=GapKind.UNIT, detail="implied", load_bearing=False)
    bundle = ReconstructionBundle(
        entry="10.1/x", engine_pin=PIN,
        assumptions=(
            close_gap(heavy, chosen="1.2 /h", basis="typical oral ka"),
            close_gap(light, chosen="mg/L", basis="axis label"),
        ),
    )
    lb = bundle.load_bearing_assumptions()
    assert [a.id for a in lb] == ["assume:absorption rate ka"]


def test_load_bearing_assumption_forces_qualified_certificate() -> None:
    # The gap -> assumption -> certificate chain: a claim reproduced only because of a
    # load-bearing assumption cannot be reported as an unqualified full reproduction.
    gap = Gap(element="ka", kind=GapKind.PARAMETER, detail="unreported", load_bearing=True)
    assumption = close_gap(gap, chosen="1.2 /h", basis="typical")
    cert = build_certificate(
        paper=PaperIdentity(title="t"),
        engine_pin=PIN,
        assessments=[ClaimAssessment(claim_id="C1", quantity="Cmax", verdict=Verdict.REPRODUCED,
                                     source_location="Fig 1", assumption_qualified=True)],
        assumptions=[assumption],
    )
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED


# --- recipe coverage and adopt-and-verify ------------------------------------------


def test_recipe_must_cover_every_targetable_claim() -> None:
    dossier = Dossier(
        entry="10.1/x",
        claims=(
            DossierClaim(id="C1", quantity="AUC", conditions="", source_location="T2"),
            DossierClaim(id="C2", quantity="Cmax", conditions="", source_location="F1"),
            DossierClaim(id="S1", quantity="schematic", conditions="", source_location="F0",
                         targetable=False),
        ),
    )
    partial = ReconstructionBundle(
        entry="10.1/x", engine_pin=PIN,
        recipe=(RecipeStep(claim_id="C1", protocol="100mg IV", output="AUC", time_span="0-24h"),),
    )
    assert not partial.covers(dossier)
    assert partial.uncovered_claims(dossier) == ("C2",)  # schematic not required

    # Covering C2 with a recorded reason it cannot run also satisfies coverage.
    complete = ReconstructionBundle(
        entry="10.1/x", engine_pin=PIN,
        recipe=(RecipeStep(claim_id="C1", protocol="100mg IV", output="AUC", time_span="0-24h"),),
        non_reconstructable=(NonReconstructable(claim_id="C2", reason="no protocol stated"),),
    )
    assert complete.covers(dossier)


def test_author_supplied_model_is_labelled_and_requires_a_model() -> None:
    art = ModelArtifact(filename="author.xml", detected_format="sbml", validates=True)
    adopted = ReconstructionBundle(
        entry="10.1/x", engine_pin=PIN, model=art, origin=ModelOrigin.AUTHOR_SUPPLIED,
        mismatches=("Eq 2 uses ke=0.1 but Table 1 says 0.12",),
    )
    assert adopted.validate() == []
    assert adopted.to_dict()["origin"] == "author-supplied"
    assert adopted.mismatches  # a dossier mismatch is surfaced, not silently trusted

    # Claiming an author-supplied origin with no model is ill-formed.
    bad = ReconstructionBundle(entry="10.1/x", engine_pin=PIN, origin=ModelOrigin.AUTHOR_SUPPLIED)
    assert bad.validate()


def test_validate_flags_duplicate_assumption_and_recipe_ids() -> None:
    gap = Gap(element="ka", kind=GapKind.PARAMETER, detail="x")
    bundle = ReconstructionBundle(
        entry="10.1/x", engine_pin=PIN,
        assumptions=(close_gap(gap, chosen="1", basis="b"), close_gap(gap, chosen="2", basis="b")),
        recipe=(RecipeStep(claim_id="C1", protocol="p", output="o", time_span="t"),
                RecipeStep(claim_id="C1", protocol="p2", output="o2", time_span="t2")),
    )
    problems = bundle.validate()
    assert any("duplicate assumption id" in p for p in problems)
    assert any("duplicate recipe claim: C1" in p for p in problems)


def test_a_recipe_naming_claims_the_dossier_does_not_state_does_not_cover_it() -> None:
    # Coverage was only ever checked from the dossier's side, so a recipe built against another
    # paper — or a dossier with no targetable claims at all — reported full coverage of nothing.
    from reprolith import Dossier, EnginePin, RecipeStep, ReconstructionBundle

    bundle = ReconstructionBundle(
        entry="10.1/x",
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        recipe=(RecipeStep(claim_id="Cmax-500mg", protocol="500 mg PO", output="C_p",
                           time_span="0-24 h"),),
    )
    empty = Dossier(entry="10.1/x")
    assert bundle.unmatched_steps(empty) == ("Cmax-500mg",)
    assert bundle.covers(empty) is False


def test_a_bundle_distinguishes_no_mismatches_from_never_having_looked() -> None:
    """`"mismatches": []` was published for a comparison that was never run.

    Adopt-and-verify's whole point is to say what the adopted model and the extracted dossier
    disagree about, so "checked and agreed" and "never checked" cannot be the same value on a
    published artifact — and the shipped bundle was the second while reading as the first.
    """
    from dataclasses import replace

    from reprolith import EnginePin, ReconstructionBundle

    unchecked = ReconstructionBundle(entry="X", engine_pin=EnginePin(engine="e", version="1"))
    assert unchecked.mismatches is None
    assert unchecked.to_dict()["mismatches"] is None

    agreed = replace(unchecked, mismatches=())
    assert agreed.to_dict()["mismatches"] == []
