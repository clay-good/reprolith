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
    Parameter,
    ReconstructionBundle,
    build_model_sbml,
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
