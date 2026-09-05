"""Building SBML from a dossier and running it under the pin (bootstrap task 3.1).

Needs the optional ``engine`` extra (python-libsbml to build, python-copasi to run); the whole
module skips without it.
"""

from __future__ import annotations

import math
from contextlib import contextmanager

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import (  # noqa: E402
    Dossier,
    EnginePin,
    Equation,
    ModelArtifact,
    ModelOrigin,
    Parameter,
    ReconstructionBundle,
    build_model_sbml,
    compare_sbml_to_dossier,
    simulate,
)

# A hand-built one-compartment dossier: dA/dt = -(k*A), A(0)=100, k=0.5.
_ONE_COMPARTMENT = Dossier(
    entry="10.1/onecomp",
    state_variables=("A",),
    equations=(Equation(target="A", expression="-(k * A)", source_location="Eq 1"),),
    parameters=(Parameter(name="k", value=0.5, unit="1/h", source_location="Table 1"),),
    initial_conditions=(Parameter(name="A", value=100.0, unit="mg", source_location="Methods"),),
)


def test_dossier_builds_valid_sbml() -> None:
    sbml = build_model_sbml(_ONE_COMPARTMENT)
    assert "<sbml" in sbml and 'id="A"' in sbml and "rateRule" in sbml


def test_built_bundle_validates_and_runs_under_the_pin() -> None:
    # Build the model from the dossier, package it as a bundle, and confirm it both validates
    # and runs under the pinned engine to the model's known analytic output.
    sbml = build_model_sbml(_ONE_COMPARTMENT)
    bundle = ReconstructionBundle(
        entry="10.1/onecomp",
        engine_pin=EnginePin(engine="copasi", version="4.46", algorithm="deterministic-lsoda"),
        model=ModelArtifact(filename="onecomp.xml", detected_format="sbml", validates=True),
        source_dossier="10.1/onecomp",
    )
    assert bundle.validate() == []

    times, values = simulate(sbml, "A", duration=10.0, steps=10)
    for t, v in zip(times, values):
        assert abs(v - 100.0 * math.exp(-0.5 * t)) / (100.0 * math.exp(-0.5 * t)) < 1e-4


def test_missing_initial_condition_blocks_the_build() -> None:
    no_ic = Dossier(
        entry="10.1/x",
        state_variables=("A",),
        equations=(Equation(target="A", expression="-(k * A)", source_location="Eq 1"),),
        parameters=(Parameter(name="k", value=0.5, unit="1/h", source_location="Table 1"),),
    )
    with pytest.raises(ValueError, match="initial condition"):
        build_model_sbml(no_ic)


@pytest.mark.parametrize(
    "state,parameter",
    [("C max", "k"), ("A", "k rate"), ("1x", "k"), ("A", "half-life")],
)
def test_a_name_sbml_cannot_hold_blocks_the_build(state: str, parameter: str) -> None:
    """libSBML rejects an invalid identifier by returning a code, not by raising.

    Ignored, a state variable called "C max" was emitted as a `<species>` with no `id` and a
    `<rateRule>` with no `variable` — a document libSBML itself reports as free of fatal errors,
    describing a different model from the dossier. This writer feeds `build_omex_archive`, so that
    document is what an author receives. A bad *parameter* name did fail, but only incidentally,
    when the rate law referencing it would not parse, under a message about MathML that never
    named the parameter.

    Refused rather than sanitized: these names appear inside the dossier's own expressions, so
    renaming one here would leave every expression referring to a symbol the model no longer
    declares.
    """
    dossier = Dossier(
        entry="10.1/x",
        state_variables=(state,),
        equations=(
            Equation(target=state, expression=f"0 - {parameter}", source_location="Eq 1"),
        ),
        parameters=(Parameter(name=parameter, value=0.5, unit="1/h", source_location="T1"),),
        initial_conditions=(
            Parameter(name=state, value=100.0, unit="mg", source_location="Methods"),
        ),
    )
    with pytest.raises(ValueError, match="not usable as SBML identifiers"):
        build_model_sbml(dossier)


def test_the_models_own_id_is_still_sanitised_rather_than_refused() -> None:
    """A DOI is not an identifier and no expression refers to it, so it is cleaned, not rejected.

    The refusal above must not swallow this: every dossier in the corpus is keyed by a DOI with
    slashes and dots in it, and refusing those would block the whole corpus from being built.
    """
    sbml = build_model_sbml(_ONE_COMPARTMENT)
    assert "10.1/onecomp" not in sbml
    # `_sid` prefixes what would otherwise start with a digit, so "10.1/onecomp" becomes this.
    assert 'id="m_10_1_onecomp"' in sbml


def test_unparseable_expression_is_rejected() -> None:
    bad = Dossier(
        entry="10.1/x",
        state_variables=("A",),
        equations=(Equation(target="A", expression="-(k * ", source_location="Eq 1"),),
        parameters=(Parameter(name="k", value=0.5, unit="1/h", source_location="Table 1"),),
        initial_conditions=(Parameter(name="A", value=100.0, unit="mg", source_location="M"),),
    )
    with pytest.raises(ValueError):
        build_model_sbml(bad)


# --- 3.4 adopt-and-verify: label the model and surface dossier mismatches ----------


def test_adopted_model_matching_the_dossier_has_no_mismatch() -> None:
    sbml = build_model_sbml(_ONE_COMPARTMENT)  # a model consistent with the dossier
    assert compare_sbml_to_dossier(sbml, _ONE_COMPARTMENT) == []


def test_injected_mismatch_is_reported_and_model_is_labelled() -> None:
    # The manuscript's dossier says k=0.5, but the shipped model was built with k=0.12:
    # adopt-and-verify must surface the discrepancy, not silently trust the artifact.
    shipped = build_model_sbml(
        Dossier(
            entry="10.1/onecomp",
            state_variables=("A",),
            equations=(Equation(target="A", expression="-(k * A)", source_location="Eq 1"),),
            parameters=(Parameter(name="k", value=0.12, unit="1/h", source_location="model file"),),
            initial_conditions=(Parameter(name="A", value=100.0, unit="mg", source_location="M"),),
        )
    )
    mismatches = compare_sbml_to_dossier(shipped, _ONE_COMPARTMENT)
    assert any("parameter k" in m and "0.5" in m and "0.12" in m for m in mismatches)

    bundle = ReconstructionBundle(
        entry="10.1/onecomp",
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        model=ModelArtifact(filename="author.xml", detected_format="sbml", validates=True),
        origin=ModelOrigin.AUTHOR_SUPPLIED,
        mismatches=tuple(mismatches),
    )
    assert bundle.validate() == []
    assert bundle.to_dict()["origin"] == "author-supplied"  # labelled as author-supplied
    assert bundle.mismatches  # and the mismatch travels with the bundle


def test_adopt_and_verify_compares_what_it_says_it_compared() -> None:
    """"No disagreement" has to mean the values were compared — three paths where it did not.

    An initial condition held as a parameter plus a rate rule (the PK/PD idiom this ingester
    supports on purpose), an initial condition naming nothing in the model at all, and a dossier
    parameter whose counterpart is a compartment all returned agreement without a comparison.
    """
    from reprolith.dossier import Dossier, Parameter
    from reprolith.sbml import compare_sbml_to_dossier

    sbml = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfParameters>
   <parameter id="A" value="1" constant="false"/>
   <parameter id="ke" value="0.5" constant="true"/>
  </listOfParameters>
  <listOfRules>
   <rateRule variable="A"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><apply><minus/><ci>ke</ci></apply><ci>A</ci></apply></math></rateRule>
  </listOfRules>
 </model></sbml>"""
    dossier = Dossier(
        entry="x",
        parameters=(Parameter(name="c", value=42.0, unit="L", source_location="Table 1"),),
        initial_conditions=(
            Parameter(name="A", value=100.0, unit="mg", source_location="Table 1"),
            Parameter(name="Z", value=1.0, unit="mg", source_location="Table 1"),
        ),
    )
    mismatches = compare_sbml_to_dossier(sbml, dossier)
    assert any("parameter c" in m and "42.0" in m for m in mismatches)      # a compartment size
    assert any("initial condition A" in m and "100.0" in m for m in mismatches)  # parameter-held IC
    assert any("initial condition Z" in m and "not present" in m for m in mismatches)


def test_a_state_variable_the_dossier_lost_entirely_is_reported() -> None:
    """The reverse sweep read `needed` off the dossier, so what the dossier lost was invisible.

    A lost state variable takes its equation with it, so its name was never in the set of things
    the dossier's own equations depend on — and the comparison reported nothing, which
    `ReconstructionBundle.mismatches` publishes as "checked and agreed" over half a model. The set
    comes off the model's rules now.
    """
    from dataclasses import replace

    from reprolith.ingest import ingest_sbml
    from reprolith.sbml import compare_sbml_to_dossier

    model = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="X" compartment="c" initialAmount="10" hasOnlySubstanceUnits="true"
            substanceUnits="mole" boundaryCondition="false" constant="false"/>
   <species id="Y" compartment="c" initialAmount="7" hasOnlySubstanceUnits="true"
            substanceUnits="mole" boundaryCondition="false" constant="false"/>
  </listOfSpecies>
  <listOfRules>
   <rateRule variable="X"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><minus/><ci>X</ci></apply></math></rateRule>
   <rateRule variable="Y"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><minus/><ci>Y</ci></apply></math></rateRule>
  </listOfRules>
 </model>
</sbml>"""
    dossier = ingest_sbml(model, entry="e", source_label="m.xml")
    assert compare_sbml_to_dossier(model, dossier) == []

    lost = replace(
        dossier,
        state_variables=tuple(v for v in dossier.state_variables if v != "Y"),
        equations=tuple(e for e in dossier.equations if e.target != "Y"),
        initial_conditions=tuple(i for i in dossier.initial_conditions if i.name != "Y"),
    )
    assert [m for m in compare_sbml_to_dossier(model, lost) if "Y" in m]


def test_an_unset_parameter_is_not_a_value_the_model_states() -> None:
    """libSBML hands back a default for an unset parameter — 0.0 in L2, NaN in L3.

    The sweep read it as a stated value, so a faithful dossier of a standard model whose parameter
    is initialised by an `initialAssignment` was reported as disagreeing with it, at `nan`.
    """
    from reprolith.ingest import ingest_sbml
    from reprolith.sbml import compare_sbml_to_dossier

    model = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
  <listOfParameters>
   <parameter id="P" constant="false"/>
   <parameter id="k" value="0.5" constant="true"/>
  </listOfParameters>
  <listOfInitialAssignments>
   <initialAssignment symbol="P"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <cn>3</cn></math></initialAssignment>
  </listOfInitialAssignments>
  <listOfRules>
   <rateRule variable="P"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><apply><minus/><ci>k</ci></apply><ci>P</ci></apply></math></rateRule>
  </listOfRules>
 </model>
</sbml>"""
    dossier = ingest_sbml(model, entry="e", source_label="m.xml")
    assert not [m for m in compare_sbml_to_dossier(model, dossier) if "does not state" in m]


def test_a_name_the_model_holds_at_two_values_is_not_reported_as_agreeing() -> None:
    """`setdefault` kept the first local parameter of a name, so agreement was decided by reaction order.

    SBML Level 2 models routinely reuse `k1`/`Km`/`Vmax` across reactions at different values. A
    dossier stating the *second* was compared against the first and reported as agreeing — and
    `ReconstructionBundle.mismatches` documents an empty list as "checked and agreed".
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.dossier import Dossier, ExtractionConfidence, Parameter
    from reprolith.sbml import compare_sbml_to_dossier

    two_valued = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4"><model id="m">
 <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
 <listOfSpecies><species id="A" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"/></listOfSpecies>
 <listOfReactions>
  <reaction id="R1" reversible="false">
   <listOfReactants><speciesReference species="A"/></listOfReactants>
   <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k1</ci><ci>A</ci></apply></math>
    <listOfParameters><parameter id="k1" value="0.1"/></listOfParameters></kineticLaw>
  </reaction>
  <reaction id="R2" reversible="false">
   <listOfReactants><speciesReference species="A"/></listOfReactants>
   <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k1</ci><ci>A</ci></apply></math>
    <listOfParameters><parameter id="k1" value="999.0"/></listOfParameters></kineticLaw>
  </reaction>
 </listOfReactions></model></sbml>"""

    for stated in (0.1, 999.0):
        dossier = Dossier(entry="X", parameters=(Parameter(
            name="k1", value=stated, unit="second", source_location="Table 1",
            confidence=ExtractionConfidence.QUOTED,
        ),))
        problems = compare_sbml_to_dossier(two_valued, dossier)
        assert problems, f"a model holding k1 at two values cannot agree with a single stated {stated}"
        assert "several values" in problems[0]


@contextmanager
def _naming(label: str):
    """Put the case's name in the failure when one of these stops being refused."""
    try:
        yield
    except AssertionError as exc:  # pragma: no cover - only on a regression
        raise AssertionError(f"{label} was ingested rather than refused") from exc


def test_the_stochastic_ingester_refuses_what_it_says_it_refuses() -> None:
    """Three well-formed files walked past the guards written for exactly their hazard.

    A Level 2 `stoichiometryMath` (the `constant` attribute is Level 3, so the guard never fired)
    was read as stoichiometry 1 — 500 molecules under libRoadRunner against 100 here. A model-level
    `substanceUnits="mole"` is the default for a species that omits the attribute, so a model
    declaring itself in moles ran as a 100-molecule SSA. And only the *model's* conversionFactor was
    refused, not a species', which rescales that species' contribution to every reaction's extent.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.sbml import ingest_stochastic_sbml

    stoichiometry_math = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4"><model id="m">
 <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
 <listOfSpecies>
  <species id="A" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"/>
  <species id="B" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"/>
 </listOfSpecies>
 <listOfParameters><parameter id="n" value="5"/></listOfParameters>
 <listOfReactions><reaction id="r" reversible="false">
  <listOfReactants><speciesReference species="A" stoichiometry="1"/></listOfReactants>
  <listOfProducts><speciesReference species="B">
   <stoichiometryMath><math xmlns="http://www.w3.org/1998/Math/MathML"><ci>n</ci></math></stoichiometryMath>
  </speciesReference></listOfProducts>
  <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k</ci><ci>A</ci></apply></math>
   <listOfParameters><parameter id="k" value="1"/></listOfParameters></kineticLaw>
 </reaction></listOfReactions></model></sbml>"""

    model_level_moles = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
<model id="m" substanceUnits="mole" timeUnits="second" extentUnits="mole">
 <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
 <listOfSpecies><species id="A" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"
   boundaryCondition="false" constant="false"/></listOfSpecies>
 <listOfReactions><reaction id="r" reversible="false">
  <listOfReactants><speciesReference species="A" stoichiometry="1" constant="true"/></listOfReactants>
  <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k</ci><ci>A</ci></apply></math>
   <listOfLocalParameters><localParameter id="k" value="1"/></listOfLocalParameters></kineticLaw>
 </reaction></listOfReactions></model></sbml>"""

    species_conversion_factor = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2"><model id="m">
 <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
 <listOfParameters><parameter id="cf" value="10" constant="true"/></listOfParameters>
 <listOfSpecies>
  <species id="A" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"
    boundaryCondition="false" constant="false"/>
  <species id="B" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
    boundaryCondition="false" constant="false" conversionFactor="cf"/>
 </listOfSpecies>
 <listOfReactions><reaction id="r" reversible="false">
  <listOfReactants><speciesReference species="A" stoichiometry="1" constant="true"/></listOfReactants>
  <listOfProducts><speciesReference species="B" stoichiometry="1" constant="true"/></listOfProducts>
  <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k</ci><ci>A</ci></apply></math>
   <listOfLocalParameters><localParameter id="k" value="1"/></listOfLocalParameters></kineticLaw>
 </reaction></listOfReactions></model></sbml>"""

    # The expected refusal is named per case. `match=r".+"` accepted any ValueError, and each of
    # these fixtures originally declared its rate constant at model scope — so the mass-action
    # reader refused all three before any guard under test was reached, and the test passed against
    # a package with every one of these fixes reverted.
    for label, sbml, expected in (
        ("stoichiometryMath", stoichiometry_math, "non-constant stoichiometry"),
        ("model-level substance units", model_level_moles, "declares substance units"),
        ("species conversionFactor", species_conversion_factor, "species conversionFactor"),
    ):
        with pytest.raises(ValueError, match=expected), _naming(label):
            ingest_stochastic_sbml(sbml)


def test_a_level_2_species_defaults_to_the_models_own_substance_definition() -> None:
    """Level 2 has no model-level `substanceUnits`; its default is the predefined `substance` unit.

    A model may redefine that, and four of the six committed Level 2 kinetic models do — as scaled
    moles. Reading only the species attribute returned '' there and let a model whose amounts are
    nanomoles through the guard whose whole purpose is catching amounts that are not counts.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.sbml import ingest_stochastic_sbml

    def model(kind: str, scale: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4"><model id="m">
 <listOfUnitDefinitions><unitDefinition id="substance">
   <listOfUnits><unit kind="{kind}" scale="{scale}"/></listOfUnits>
 </unitDefinition></listOfUnitDefinitions>
 <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
 <listOfSpecies>
  <species id="A" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"/>
  <species id="B" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"/>
 </listOfSpecies>
 <listOfReactions><reaction id="r" reversible="false">
  <listOfReactants><speciesReference species="A"/></listOfReactants>
  <listOfProducts><speciesReference species="B"/></listOfProducts>
  <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k</ci><ci>A</ci></apply></math>
   <listOfParameters><parameter id="k" value="1"/></listOfParameters></kineticLaw>
 </reaction></listOfReactions></model></sbml>"""

    # Scaled moles are amounts, not counts, however the model spells them.
    for scale in ("-9", "-3", "0"):
        with pytest.raises(ValueError, match="substance units"):
            ingest_stochastic_sbml(model("mole", scale))
    # Genuine molecule counts still ingest.
    names, _, initial = ingest_stochastic_sbml(model("item", "0"))
    assert list(initial) == [100, 0]


def test_a_rule_determined_name_is_reported_rather_than_passed_over() -> None:
    """A rule-determined parameter has no stated value to compare — which is not silence.

    Restoring those names to the comparison dictionaries put their inert `value` attributes back
    into the comparison, so a dossier stating one agreed with it and the check fell silent exactly
    where it had just been taught to speak. And reading only the locals for a reused name published
    "model 9.0" for a model whose global is 5.0 — the dossier's own number, live in another
    reaction — naming a value the model does not hold.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from pathlib import Path

    from reprolith.dossier import Dossier, ExtractionConfidence, Parameter
    from reprolith.sbml import compare_sbml_to_dossier

    def stated(name: str, value: float) -> Parameter:
        return Parameter(name=name, value=value, unit="second", source_location="Table 1",
                         confidence=ExtractionConfidence.QUOTED)

    committed = (Path(__file__).parent.parent / "datasets" / "kinetic"
                 / "BIOMD0000000058.xml").read_text(encoding="utf-8")
    problems = compare_sbml_to_dossier(
        committed, Dossier(entry="X", parameters=(stated("Phi1_c1", 0.0),))
    )
    assert problems and "a rule determines it" in problems[0], problems

    global_and_local = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4"><model id="m">
 <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
 <listOfSpecies><species id="A" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"/></listOfSpecies>
 <listOfParameters><parameter id="Vmax" value="5.0"/></listOfParameters>
 <listOfReactions>
  <reaction id="R1" reversible="false"><listOfReactants><speciesReference species="A"/></listOfReactants>
   <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>Vmax</ci><ci>A</ci></apply></math>
    <listOfParameters><parameter id="Vmax" value="9.0"/></listOfParameters></kineticLaw></reaction>
  <reaction id="R2" reversible="false"><listOfReactants><speciesReference species="A"/></listOfReactants>
   <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>Vmax</ci><ci>A</ci></apply></math>
   </kineticLaw></reaction>
 </listOfReactions></model></sbml>"""
    reported = compare_sbml_to_dossier(
        global_and_local, Dossier(entry="Y", parameters=(stated("Vmax", 5.0),))
    )
    assert reported and "several values" in reported[0], reported
    assert "5.0" in reported[0], "the global the dossier agrees with must appear"
