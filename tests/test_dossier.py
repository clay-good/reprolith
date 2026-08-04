"""The dossier shape and its ingestion honesty invariants (task 0.2 shape; 2.1-2.3)."""

from __future__ import annotations

import pytest
from reprolith import (
    Dossier,
    DossierClaim,
    Equation,
    ExtractionConfidence,
    Gap,
    GapKind,
    ModelArtifact,
    Parameter,
    ReferenceKind,
)

# --- 0.2 an empty example validates against its shape ------------------------------


def test_empty_dossier_is_valid() -> None:
    d = Dossier(entry="10.1/x")
    assert d.validate() == []
    assert d.to_dict()["entry"] == "10.1/x"
    assert d.targetable_claims() == () and d.load_bearing_gaps() == ()


# --- 2.3 a missing element is a gap, not a guessed value ---------------------------


def test_parameter_requires_a_value_a_unit_and_a_source() -> None:
    # A parameter is by construction an extracted value; there is no way to express a
    # missing one as a parameter.
    ok = Parameter(name="CL", value=5.0, unit="L/h", source_location="Table 1")
    assert ok.value == 5.0
    with pytest.raises(ValueError):
        Parameter(name="CL", value=5.0, unit="  ", source_location="Table 1")  # unstated unit
    with pytest.raises(ValueError):
        Parameter(name="CL", value=5.0, unit="L/h", source_location="")  # no provenance


def test_missing_parameter_is_recorded_as_a_gap_not_a_value() -> None:
    # The paper omits clearance: it appears in gaps, and never as a parameter with a guess.
    d = Dossier(
        entry="10.1/x",
        parameters=(Parameter(name="V", value=10.0, unit="L", source_location="Table 1"),),
        gaps=(Gap(element="clearance (CL)", kind=GapKind.PARAMETER,
                  detail="not reported in text or tables", load_bearing=True),),
    )
    assert [p.name for p in d.parameters] == ["V"]  # no fabricated CL
    assert d.gaps[0].element == "clearance (CL)"
    assert d.load_bearing_gaps() == (d.gaps[0],)


def test_extraction_confidence_is_recorded() -> None:
    interpreted = Parameter(name="ka", value=1.2, unit="1/h", source_location="Fig 2 caption",
                            confidence=ExtractionConfidence.INTERPRETED)
    assert interpreted.to_dict()["confidence"] == "interpreted"


# --- 2.2 claims are first-class, targetable, and reference-typed -------------------


def test_targetable_and_non_targetable_claims_are_both_kept() -> None:
    d = Dossier(
        entry="10.1/x",
        claims=(
            DossierClaim(id="C1", quantity="AUC", conditions="100mg IV", source_location="Table 2",
                         reference_kind=ReferenceKind.NUMERIC, reference_data=(1.0, 2.0, 3.0)),
            DossierClaim(id="C2", quantity="C(t)", conditions="100mg IV", source_location="Fig 3",
                         reference_kind=ReferenceKind.DIGITIZED_FIGURE),
            DossierClaim(id="S1", quantity="schematic", conditions="", source_location="Fig 1",
                         targetable=False),
        ),
    )
    assert {c.id for c in d.targetable_claims()} == {"C1", "C2"}  # schematic excluded, not dropped
    assert len(d.claims) == 3
    # The reference kind travels so the oracle knows what to compare against.
    assert d.claims[0].to_dict()["reference_kind"] == "numeric"
    assert d.claims[1].to_dict()["reference_kind"] == "digitized-figure"


def test_claim_requires_an_id_and_a_source() -> None:
    with pytest.raises(ValueError):
        DossierClaim(id="", quantity="AUC", conditions="", source_location="Table 2")
    with pytest.raises(ValueError):
        DossierClaim(id="C1", quantity="AUC", conditions="", source_location="")


# --- structural validation ---------------------------------------------------------


def test_validate_flags_duplicate_identifiers() -> None:
    d = Dossier(
        entry="10.1/x",
        parameters=(
            Parameter(name="V", value=10.0, unit="L", source_location="Table 1"),
            Parameter(name="V", value=12.0, unit="L", source_location="Table 3"),
        ),
        claims=(
            DossierClaim(id="C1", quantity="AUC", conditions="", source_location="Table 2"),
            DossierClaim(id="C1", quantity="Cmax", conditions="", source_location="Table 2"),
        ),
    )
    problems = d.validate()
    assert any("duplicate parameter name: V" in p for p in problems)
    assert any("duplicate claim id: C1" in p for p in problems)


def test_full_dossier_round_trips_through_to_dict() -> None:
    d = Dossier(
        entry="10.1/x",
        state_variables=("A_gut", "A_central"),
        equations=(Equation(target="A_central", expression="ka*A_gut - ke*A_central",
                            source_location="Eq 1"),),
        parameters=(Parameter(name="ke", value=0.1, unit="1/h", source_location="Table 1"),),
        initial_conditions=(Parameter(name="A_gut", value=100.0, unit="mg", source_location="Methods"),),
        artifacts=(ModelArtifact(filename="model.xml", detected_format="sbml", validates=True),),
    )
    assert d.validate() == []
    out = d.to_dict()
    assert out["state_variables"] == ["A_gut", "A_central"]
    assert out["artifacts"][0]["detected_format"] == "sbml"
    assert out["initial_conditions"][0]["name"] == "A_gut"


# --- difficulty estimate from observable signals (spec: model-catalog) --------------


def test_difficulty_estimate_from_signals() -> None:
    from reprolith import estimate_difficulty

    base = dict(entry="x", state_variables=("A",),
                equations=(Equation(target="A", expression="-A", source_location="e"),))

    # A valid shipped model and no gaps: adopt-and-verify, low difficulty.
    low = Dossier(**base, artifacts=(ModelArtifact(filename="m.xml", detected_format="sbml", validates=True),))
    assert estimate_difficulty(low) == "low"

    # A load-bearing gap makes it high regardless of the model.
    high = Dossier(**base, artifacts=(ModelArtifact(filename="m.xml", detected_format="sbml", validates=True),),
                   gaps=(Gap(element="CL", kind=GapKind.PARAMETER, detail="x", load_bearing=True),))
    assert estimate_difficulty(high) == "high"

    # A non-load-bearing gap with a model is medium.
    medium = Dossier(**base, artifacts=(ModelArtifact(filename="m.xml", detected_format="sbml", validates=True),),
                     gaps=(Gap(element="unit", kind=GapKind.UNIT, detail="x"),))
    assert estimate_difficulty(medium) == "medium"

    # No model structure at all is high.
    assert estimate_difficulty(Dossier(entry="x")) == "high"
