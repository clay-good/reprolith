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
    sbml = _FIXTURE.read_text()
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

    sbml = _FIXTURE.read_text()
    times, values = simulate(sbml, "C_p", duration=10.0, steps=10)
    # The plasma concentration is produced and finite across the run.
    assert len(values) == 11
    assert all(math.isfinite(v) for v in values)
