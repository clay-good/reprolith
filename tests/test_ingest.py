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
    # The gap is real and load-bearing for anything rebuilt from the dossier alone — but the
    # shipped model still carries the reactions, so adopt-and-verify closes it and this gap does
    # not make the paper harder. What must never happen again is the gap going unrecorded.
    assert reaction_gaps[0].carried_by_artifact
    # The difficulty is `high` all the same, and for a different gap: none of this model's eight
    # extracted values states a unit, and a unit the artifact never states is not closed by
    # adopting the artifact. That gap used to be flagged as carried and discounted away.
    units = [g for g in dossier.gaps if g.element == "units"]
    assert len(units) == 1 and not units[0].carried_by_artifact
    assert estimate_difficulty(dossier) == "high"


def test_an_unstated_unit_is_recorded_as_missing_rather_than_called_dimensionless() -> None:
    """`Parameter` says an unstated unit is a gap, not a value; intake was filling one in.

    Eighty-one of the shipped metformin dossier's parameters state no unit in the artifact —
    blood flows, a glomerular filtration rate, transporter maxima — and every one was recorded as
    `dimensionless` at `quoted` confidence. Dimensionless is a physical claim, not an absence.
    """
    from reprolith import GapKind, ingest_sbml
    from reprolith.ingest import UNSTATED_UNIT

    metformin = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.xml"
    )
    dossier = ingest_sbml(metformin.read_text(encoding="utf-8"), entry="BIOMD0000001028")
    assert any(p.unit == UNSTATED_UNIT for p in dossier.parameters)
    assert not any(p.unit == "dimensionless" for p in dossier.parameters if p.unit == UNSTATED_UNIT)
    unit_gaps = [g for g in dossier.gaps if g.kind is GapKind.UNIT and g.element == "units"]
    assert len(unit_gaps) == 1 and unit_gaps[0].load_bearing

    # And a model whose compartments are not unit-sized says so, because reconstruction builds one
    # compartment of size 1 and every concentration in a 1799 mL liver would be out by that volume.
    volumes = [g for g in dossier.gaps if g.element == "compartment volumes"]
    assert len(volumes) == 1 and volumes[0].load_bearing


def test_a_dynamic_species_with_no_stated_initial_value_is_a_gap() -> None:
    """It was dropped in silence, so the dossier carried a rate rule for a variable it never declared."""
    sbml = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="Gut" compartment="c" hasOnlySubstanceUnits="true"
            boundaryCondition="false" constant="false"/>
   <species id="Plasma" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
            boundaryCondition="false" constant="false"/>
  </listOfSpecies>
 </model></sbml>"""
    dossier = ingest_sbml(sbml, entry="x", source_label="s")
    assert dossier.state_variables == ("Plasma",)  # never fabricated
    gap = next(g for g in dossier.gaps if g.element == "initial values")
    assert gap.load_bearing and not gap.carried_by_artifact
    assert "Gut" in gap.detail


def test_package_content_this_path_cannot_read_is_a_gap_but_layout_is_not() -> None:
    """The repo's own SBML-qual model used to ingest to an empty dossier that rated `low`."""
    from pathlib import Path

    from reprolith.dossier import estimate_difficulty

    qual = Path(__file__).parent.parent / "datasets" / "logical" / "worked_example" / "model.xml"
    dossier = ingest_sbml(qual.read_text(encoding="utf-8"), entry="toggle", source_label="s")
    gap = next(g for g in dossier.gaps if g.element == "package content")
    assert "qual" in gap.detail and gap.load_bearing
    assert estimate_difficulty(dossier) == "high"
    # A model declaring only `layout` describes how to draw itself; that is not a gap in its
    # dynamics, and recording it would be a gap that cries wolf.
    metformin = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.xml"
    )
    shipped = ingest_sbml(metformin.read_text(encoding="utf-8"), entry="m", source_label="s")
    assert not [g for g in shipped.gaps if g.element == "package content"]


_BOUNDARY_STATE_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="S" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
            substanceUnits="mole" boundaryCondition="false" constant="false"/>
   <species id="Input" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"
            substanceUnits="mole" boundaryCondition="true" constant="false"/>
  </listOfSpecies>
  <listOfUnitDefinitions>
   <unitDefinition id="per_second">
    <listOfUnits><unit kind="second" exponent="-1" scale="0" multiplier="1"/></listOfUnits>
   </unitDefinition>
  </listOfUnitDefinitions>
  <listOfParameters>
   <parameter id="k" value="0.5" units="per_second" constant="true"/>
  </listOfParameters>
  <listOfRules>
   <rateRule variable="S"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><ci>k</ci><ci>Input</ci></apply></math></rateRule>
   <rateRule variable="Input"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><apply><minus/><ci>k</ci></apply><ci>Input</ci></apply></math></rateRule>
  </listOfRules>
 </model>
</sbml>"""


_CONSTANT_SPECIES_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="S" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
            boundaryCondition="false" constant="false"/>
   <species id="Fixed" compartment="c" initialAmount="7" hasOnlySubstanceUnits="true"
            boundaryCondition="false" constant="true"/>
  </listOfSpecies>
  <listOfParameters><parameter id="k" value="0.5" constant="true"/></listOfParameters>
  <listOfRules>
   <rateRule variable="S"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><ci>k</ci><ci>Fixed</ci></apply></math></rateRule>
  </listOfRules>
 </model>
</sbml>"""


def test_a_boundary_species_with_its_own_rate_rule_is_a_gap_not_a_silence() -> None:
    """`constant` or `boundaryCondition` was read as "a fixed input", which two shapes are not.

    A boundary species carrying its own rate rule is a state variable by any other name. Skipping
    it dropped half this model's state from the dossier while every honesty surface read clean: no
    gap, difficulty "low" (documented as "a valid shipped model and no gaps"), and adopt-and-verify
    — which never rebuilds, so never reaches `build_model_sbml`'s way-out check — reporting
    agreement. The way-in check now names what the dossier does not carry.
    """
    from reprolith.dossier import estimate_difficulty
    from reprolith.ingest import ingest_sbml
    from reprolith.sbml import compare_sbml_to_dossier

    dossier = ingest_sbml(_BOUNDARY_STATE_MODEL, entry="e", source_label="m.xml")
    assert dossier.state_variables == ("S",)
    gap = next(g for g in dossier.gaps if g.element == "undeclared model elements")
    assert "Input" in gap.detail and gap.load_bearing
    # Every unit here is stated, so this is the new gap doing the work and not the units gap:
    # delete the check and this test goes back to passing for the wrong reason.
    assert not [g for g in dossier.gaps if g.element == "units"]
    # `estimate_difficulty` still says "low", and that is correct rather than a hole: the gap is
    # `carried_by_artifact`, and adopt-and-verify runs the author's own file, where `Input` is
    # still in force. The surface that must not stay silent is the one adopt-and-verify actually
    # reads — the model/dossier comparison — and it no longer does.
    assert estimate_difficulty(dossier) == "low"
    assert [m for m in compare_sbml_to_dossier(_BOUNDARY_STATE_MODEL, dossier) if "Input" in m]


def test_a_constant_species_a_rule_reads_is_a_gap_not_a_silence() -> None:
    """The sibling shape: a value the rules depend on that leaves the dossier without a trace."""
    from reprolith.ingest import ingest_sbml

    dossier = ingest_sbml(_CONSTANT_SPECIES_MODEL, entry="e", source_label="m.xml")
    gap = next(g for g in dossier.gaps if g.element == "undeclared model elements")
    assert "Fixed" in gap.detail and gap.load_bearing


def test_a_fully_declared_model_reports_no_undeclared_element_gap() -> None:
    """The check must not cry wolf: every shipped model resolves, and so must this one."""
    from reprolith.ingest import ingest_sbml

    dossier = ingest_sbml(_ASSIGNMENT_MODEL, entry="e", source_label="m.xml")
    assert not [g for g in dossier.gaps if g.element == "undeclared model elements"]


def test_a_model_element_the_dossier_never_states_is_a_mismatch_not_a_silence() -> None:
    """`compare_sbml_to_dossier` walked dossier -> model only, so what the dossier lost was invisible.

    Adopt-and-verify never rebuilds, so it never reaches `build_model_sbml`'s way-out refusal; its
    one check was this comparison, which reported `[]` for a dossier carrying half a model — and
    `ReconstructionBundle.mismatches` publishes `[]` as "checked and agreed".
    """
    from reprolith.ingest import ingest_sbml
    from reprolith.sbml import compare_sbml_to_dossier

    for model in (_BOUNDARY_STATE_MODEL, _CONSTANT_SPECIES_MODEL):
        dossier = ingest_sbml(model, entry="e", source_label="m.xml")
        assert [m for m in compare_sbml_to_dossier(model, dossier) if "does not state" in m]
    # …and it stays quiet on a model the dossier fully carries.
    fully_stated = ingest_sbml(_ASSIGNMENT_MODEL, entry="e", source_label="m.xml")
    assert compare_sbml_to_dossier(_ASSIGNMENT_MODEL, fully_stated) == []


def test_a_model_level_substance_unit_is_read_as_stated() -> None:
    """SBML L3 defaults a species' substance unit from the model; reading only the species
    attribute called a stated unit absent, and published a load-bearing gap whose own text
    asserted something false about the artifact."""
    from reprolith.ingest import ingest_sbml

    model = _ASSIGNMENT_MODEL.replace('<model id="m">', '<model id="m" substanceUnits="mole">')
    dossier = ingest_sbml(model, entry="e", source_label="m.xml")
    assert all(ic.unit == "mole" for ic in dossier.initial_conditions)
    # The species no longer appear in the units gap; `k`, which really does state none, still does.
    units_gap = next(g for g in dossier.gaps if g.element == "units")
    assert "X" not in units_gap.detail and "Y" not in units_gap.detail


def test_a_unit_exponent_covers_the_whole_prefixed_factor() -> None:
    """SBML defines a factor as `(multiplier * 10^scale * kind)^exponent`, not `multiplier * 10^scale * kind^exponent`.

    Rendered the second way, the metformin model's blood flows read as 3.6e5 mL/s where the file
    states mL per 360000 s — wrong by 1.3e11 and in a committed artifact — and a second-order rate
    constant came out 1e6 the other way. That is worse than the bare `unit_2` it replaced, because
    it reads as resolved.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    import libsbml
    from reprolith.ingest import _render_unit_definition

    root = Path(__file__).parent.parent / "datasets"
    for path in (root / "worked_examples" / "Zake2021_metformin_human_single_PO.xml",
                 root / "kinetic" / "BIOMD0000000051.xml"):
        model = libsbml.readSBMLFromString(path.read_text(encoding="utf-8")).getModel()
        for i in range(model.getNumUnitDefinitions()):
            definition = model.getUnitDefinition(i)
            rendered = _render_unit_definition(definition)
            for j in range(definition.getNumUnits()):
                unit = definition.getUnit(j)
                if unit.getExponent() != 1 and (
                    unit.getScale() != 0 or unit.getMultiplier() != 1.0
                ):
                    kind = libsbml.UnitKind_toString(unit.getKind())
                    assert f"{kind})^{unit.getExponent()}" in rendered, (
                        f"{definition.getId()} renders as {rendered!r}, which reads as the "
                        "reciprocal of what the file says"
                    )


def test_a_value_an_assignment_rule_determines_is_not_recorded_as_a_stated_one() -> None:
    """SBML makes a rule-determined parameter's `value` attribute inert, and models ship anything.

    BIOMD0000000058 declares eight such parameters at 0 that the model runs between 0.5 and 21, and
    BIOMD0000000051 carries seven time-varying cofactor pools as if clamped. Recorded as `quoted`,
    the dossier asserted a number the model never holds — and `compare_sbml_to_dossier` compared it
    against the same inert attribute and published "no disagreement" over every one of them.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.ingest import ingest_sbml
    from reprolith.sbml import compare_sbml_to_dossier

    path = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000058.xml"
    sbml = path.read_text(encoding="utf-8")
    dossier = ingest_sbml(sbml, entry="BIOMD0000000058")

    stated = {p.name for p in dossier.parameters}
    assignment_targets = {e.target for e in dossier.equations if e.kind.value == "assignment"}
    assert assignment_targets, "this model is only a fixture while it has assignment rules"
    assert not (stated & assignment_targets), (
        f"{sorted(stated & assignment_targets)} are determined by a rule, not stated"
    )
    # The rules themselves are still carried, so nothing was lost — only the false value.
    assert "Phi1_c1" in assignment_targets
    # And the check no longer reports agreement on values neither side compared.
    assert compare_sbml_to_dossier(sbml, dossier) == []
