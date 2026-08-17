"""SBML artifact-intake ingestion (spec: paper-ingestion, "Recognizing an existing model").

Needs the optional ``engine`` extra (python-libsbml); the module skips without it. The
real-model test reads a CC0 BioModels fixture (see tests/fixtures/README.md).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed")

from reprolith import (  # noqa: E402
    Dossier,
    Equation,
    Parameter,
    build_model_sbml,
    ingest_sbml,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "BIOMD0000000241.xml"


def test_ingest_round_trips_a_built_model() -> None:
    # Build SBML from a dossier, then ingest it back: the structure is recovered.
    original = Dossier(
        entry="10.1/x",
        state_variables=("A",),
        equations=(Equation(target="A", expression="-(k * A)", source_location="Eq 1"),),
        parameters=(Parameter(name="k", value=0.5, unit="1/h", source_location="Table 1"),),
        initial_conditions=(Parameter(name="A", value=100.0, unit="mg", source_location="M"),),
    )
    sbml = build_model_sbml(original)
    ingested = ingest_sbml(sbml, entry="10.1/x", source_label="built.xml")

    assert ingested.state_variables == ("A",)
    assert {p.name for p in ingested.parameters} == {"k"}
    assert {e.target for e in ingested.equations} == {"A"}
    assert ingested.initial_conditions[0].value == 100.0
    assert ingested.validate() == []


def test_ingests_a_real_biomodels_pkpd_model() -> None:
    sbml = _FIXTURE.read_text(encoding="utf-8")
    dossier = ingest_sbml(sbml, entry="BIOMD0000000241", source_label="BioModels BIOMD0000000241")

    # A real 5-compartment PK/PD model: gut, plasma, peripheral, effect, tolerance.
    assert len(dossier.state_variables) == 5
    assert "X_gut" in dossier.state_variables
    assert len(dossier.parameters) >= 15
    assert dossier.validate() == []
    # Every extracted element cites where it came from (here, the model file).
    for element in (*dossier.parameters, *dossier.initial_conditions):
        assert "BIOMD0000000241" in element.source_location
    # Artifact ingestion carries model structure but no manuscript claims.
    assert dossier.targetable_claims() == ()


def test_real_model_runs_under_the_pin() -> None:
    pytest.importorskip("COPASI", reason="python-copasi not installed")
    from reprolith import simulate

    sbml = _FIXTURE.read_text(encoding="utf-8")
    times, values = simulate(sbml, "C_p", duration=10.0, steps=10)
    # The plasma concentration is produced and finite across the run.
    assert len(values) == 11
    assert all(math.isfinite(v) for v in values)


def test_ingests_parameter_state_variables() -> None:
    # Overgaard2007 ships no species: its states are SBML parameters with rate rules.
    sbml = (Path(__file__).parent / "fixtures" / "BIOMD0000000238.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(sbml, entry="BIOMD0000000238", source_label="BioModels BIOMD0000000238")
    assert set(dossier.state_variables) == {"M", "T", "BR"}
    ics = {p.name for p in dossier.initial_conditions}
    assert {"M", "T", "BR"} <= ics
    # A rate-rule-target is a state variable, not also listed as a constant parameter.
    assert not ({"M", "T", "BR"} & {p.name for p in dossier.parameters})
    assert dossier.validate() == []


# --- the rule kind and the unit convention survive the round trip ------------------

_ASSIGNMENT_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="X" compartment="c" initialAmount="10" hasOnlySubstanceUnits="true"
            boundaryCondition="false" constant="false"/>
   <species id="Y" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
            boundaryCondition="false" constant="false"/>
  </listOfSpecies>
  <listOfParameters><parameter id="k" value="0.5" constant="true"/></listOfParameters>
  <listOfRules>
   <rateRule variable="X"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><apply><minus/><ci>k</ci></apply><ci>X</ci></apply></math></rateRule>
   <assignmentRule variable="Y"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><cn>2</cn><ci>X</ci></apply></math></assignmentRule>
  </listOfRules>
 </model>
</sbml>"""


def _concentration_model(size: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="{size}" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="X" compartment="c" initialConcentration="4" hasOnlySubstanceUnits="false"
            boundaryCondition="false" constant="false"/>
  </listOfSpecies>
  <listOfParameters><parameter id="k" value="0.5" constant="true"/></listOfParameters>
  <listOfRules>
   <rateRule variable="X"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><apply><minus/><ci>k</ci></apply><ci>X</ci></apply></math></rateRule>
  </listOfRules>
 </model>
</sbml>"""


def test_an_assignment_rule_is_not_rebuilt_as_a_rate_rule() -> None:
    # Y = 2X is an observable, not a state that grows at 2X: rebuilding it as a rate rule
    # would run a different model than the artifact describes.
    from reprolith.dossier import EquationKind

    dossier = ingest_sbml(_ASSIGNMENT_MODEL, entry="10.1/x")
    kinds = {e.target: e.kind for e in dossier.equations}
    assert kinds == {"X": EquationKind.RATE, "Y": EquationKind.ASSIGNMENT}

    rebuilt = build_model_sbml(dossier)
    assert '<assignmentRule variable="Y">' in rebuilt
    assert '<rateRule variable="X">' in rebuilt
    assert '<rateRule variable="Y">' not in rebuilt


def test_a_concentration_in_a_unit_compartment_is_the_amount_it_states() -> None:
    dossier = ingest_sbml(_concentration_model("1"), entry="10.1/x")
    assert [(p.name, p.value) for p in dossier.initial_conditions] == [("X", 4.0)]


def test_a_concentration_in_a_non_unit_compartment_is_refused() -> None:
    # Reconstruction is amount-based in a unit compartment; reading 4 mM in a 2 L compartment
    # as an amount of 4 would silently rebuild a different model.
    with pytest.raises(ValueError, match="unit compartment"):
        ingest_sbml(_concentration_model("2"), entry="10.1/x")


def test_constructs_the_dossier_cannot_represent_are_recorded_as_load_bearing_gaps() -> None:
    """An event is the most common PK/PD construct there is, and it was dropped without a trace.

    Rules become equations on this path, so most of a model survives — but an event (a dose), an
    initial assignment (an override of the values just recorded), and a conversion factor (a
    rescaling of every amount) do not. They are recorded rather than refused because the artifact
    itself stays runnable: adopt-and-verify uses the author's own file. It is the dossier that
    cannot carry them, and a reconstruction built from one now carries the gap into its certificate.
    """
    pytest.importorskip("libsbml")
    from reprolith import ingest_sbml

    shipped = Path(__file__).parent.parent / "datasets" / "worked_examples"
    metformin = (shipped / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(metformin, entry="BIOMD0000001028")
    kinds = {gap.kind.value for gap in dossier.gaps}
    assert "dosing" in kinds  # the oral dose is an event
    assert "initial-condition" in kinds  # 32 initial assignments override the stated values
    assert all(gap.load_bearing for gap in dossier.gaps)


def test_a_reaction_network_is_recorded_as_a_gap_not_read_past() -> None:
    """The dossier's own dynamics are the largest thing this path does not carry.

    Rules become equations, so the ingester looked complete on a rule-based PK/PD model — but a
    reaction-based model's laws of motion live in its reactions, and none of them were read or
    recorded. A ten-reaction cascade produced eight state variables, zero equations, and zero
    gaps, which `estimate_difficulty` then published as "low: a valid shipped model and no gaps".
    """
    from reprolith import GapKind, estimate_difficulty, ingest_sbml

    mapk = (Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.xml")
    dossier = ingest_sbml(mapk.read_text(encoding="utf-8"), entry="BIOMD0000000010")
    assert dossier.state_variables  # it does record the states
    reaction_gaps = [g for g in dossier.gaps if g.element == "reaction network"]
    assert len(reaction_gaps) == 1
    assert reaction_gaps[0].kind is GapKind.EQUATION and reaction_gaps[0].load_bearing
    # And a dossier missing every law of motion is no longer advertised as the easy case.
    assert estimate_difficulty(dossier) != "low"
