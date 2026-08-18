"""Building SBML from a dossier and running it under the pin (bootstrap task 3.1).

Needs the optional ``engine`` extra (python-libsbml to build, python-copasi to run); the whole
module skips without it.
"""

from __future__ import annotations

import math

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
