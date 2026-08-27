"""Writing a COMBINE archive, and reading back exactly what was written.

The reading half of the fast path has tests (``test_omex.py``, ``test_archive_end_to_end.py``).
This is the writing half: what Reprolith emits must be what Reprolith's own reader accepts, and it
must not assert more than the reconstruction knows. Most of these need no optional extra — the
writer and the SED-ML/manifest readers are pure standard library. The one that needs libSBML is
the full round trip, because turning an archive back into a dossier parses the model.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

import pytest
from reprolith import (
    archive_mismatches,
    build_experiment_sedml,
    build_omex_archive,
    enumerate_sedml_claims,
    parse_sedml_recipes,
    sedml_model_sources,
)

# A two-compartment model in the shape `build_model_sbml` emits: species with initial amounts,
# constant parameters, and one rate rule per state variable. Hand-written so the writer's tests
# run without the SBML extra.
_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="two_compartment">
    <listOfCompartments>
      <compartment id="c" size="1" constant="true"/>
    </listOfCompartments>
    <listOfSpecies>
      <species id="central" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
      <species id="peripheral" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="k" value="0.3" constant="true"/>
    </listOfParameters>
  </model>
</sbml>
"""


def _members(archive: bytes) -> dict[str, str]:
    with zipfile.ZipFile(BytesIO(archive)) as zf:
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


def test_the_exported_recipe_is_the_run_that_was_asked_for() -> None:
    """The point of writing SED-ML at all: `simulate(duration, steps)` survives the round trip."""
    sedml = build_experiment_sedml(_MODEL, duration=24.0, steps=240)

    recipes = parse_sedml_recipes(sedml)
    assert len(recipes) == 1
    assert (recipes[0].duration, recipes[0].steps) == (24.0, 240)
    assert recipes[0].observables == ("central", "peripheral")
    assert recipes[0].output_start == 0.0
    assert sedml_model_sources(sedml) == ("model.xml",)


def test_the_exported_document_manufactures_no_published_results() -> None:
    """A report, not a plot — see the module docstring in `reprolith.export`.

    Emitting the observables as plot curves would read back, through Reprolith's own claim reader,
    as the paper having published one figure per state variable. It published no such thing: the
    export knows how to run the model, not which of its outputs anyone displayed.
    """
    sedml = build_experiment_sedml(_MODEL, duration=24.0, steps=240)

    claims = enumerate_sedml_claims(sedml)
    assert [c.quantity for c in claims] == ["central", "peripheral"]
    assert not any(c.targetable for c in claims)


def test_the_experiment_and_the_model_it_ships_with_agree() -> None:
    """Every target the writer emits resolves in the model, by nesting, not by a flat id search."""
    sedml = build_experiment_sedml(_MODEL, duration=1.0, steps=10)
    assert archive_mismatches(sedml, _MODEL) == []


def test_an_observable_the_model_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="no top-level element named: effect"):
        build_experiment_sedml(_MODEL, duration=1.0, steps=10, observables=("central", "effect"))


def test_a_parameter_can_be_recorded_as_well_as_a_species() -> None:
    """Observables are not species-only: a model whose parameter carries an assignment rule
    records that parameter, and the target must address it through `listOfParameters`."""
    sedml = build_experiment_sedml(_MODEL, duration=1.0, steps=10, observables=("central", "k"))
    assert archive_mismatches(sedml, _MODEL) == []
    assert parse_sedml_recipes(sedml)[0].observables == ("central", "k")


@pytest.mark.parametrize(
    ("duration", "steps"), [(0.0, 10), (-1.0, 10), (24.0, 0), (24.0, -5)]
)
def test_a_run_that_is_not_a_run_is_refused(duration: float, steps: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        build_experiment_sedml(_MODEL, duration=duration, steps=steps)


def test_the_archive_holds_the_three_files_a_reader_needs() -> None:
    members = _members(build_omex_archive(_MODEL, duration=24.0, steps=240))
    assert set(members) == {"manifest.xml", "model.xml", "experiment.sedml"}
    assert members["model.xml"] == _MODEL

    manifest = ET.fromstring(members["manifest.xml"])
    listed = {
        element.get("location"): (element.get("format"), element.get("master"))
        for element in manifest
    }
    spec = "http://identifiers.org/combine.specifications/"
    # The level and version come from the model itself, not from a constant that can drift.
    assert listed["./model.xml"] == (f"{spec}sbml.level-3.version-2", None)
    assert listed["./experiment.sedml"] == (f"{spec}sed-ml.level-1.version-4", "true")


def test_the_same_reconstruction_exports_the_same_bytes() -> None:
    """Nondeterministic bytes cannot be digested, and every artifact here travels by digest."""
    first = build_omex_archive(_MODEL, duration=24.0, steps=240)
    second = build_omex_archive(_MODEL, duration=24.0, steps=240)
    assert first == second
    assert first != build_omex_archive(_MODEL, duration=24.0, steps=241)


def test_the_model_and_the_experiment_cannot_share_a_location() -> None:
    with pytest.raises(ValueError, match="one file per location"):
        build_omex_archive(
            _MODEL, duration=1.0, steps=10, model_location="m.xml", experiment_location="m.xml"
        )


def test_a_model_at_a_nested_location_is_still_found_by_the_document() -> None:
    archive = build_omex_archive(
        _MODEL, duration=1.0, steps=10, model_location="models/m.xml",
        experiment_location="experiments/e.sedml",
    )
    members = _members(archive)
    assert set(members) == {"manifest.xml", "models/m.xml", "experiments/e.sedml"}
    # The source is the location as the archive stores it; `ingest_omex` resolves it relative to
    # the document, which is what the nested case exists to check.
    assert sedml_model_sources(members["experiments/e.sedml"]) == ("models/m.xml",)


def test_something_that_is_not_sbml_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="not parseable SBML"):
        build_experiment_sedml("<sbml", duration=1.0, steps=10)
    with pytest.raises(ValueError, match="root element is 'sedML'"):
        build_experiment_sedml("<sedML/>", duration=1.0, steps=10)


def test_a_dossier_exports_to_an_archive_that_ingests_back_to_the_same_model() -> None:
    """The whole loop: dossier → SBML → archive → dossier, with the structure intact.

    This is what "standard, runnable artifacts" has to mean — an archive Reprolith writes is one
    Reprolith reads, on the same terms as one a paper ships. Claims are the deliberate asymmetry:
    the exported document reports columns rather than plotting results, so what comes back has the
    model's structure and no targetable claims.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith import (
        Dossier,
        Equation,
        ExtractionConfidence,
        Parameter,
        build_model_sbml,
        ingest_omex,
    )

    dossier = Dossier(
        entry="two_compartment",
        state_variables=("central", "peripheral"),
        equations=(
            Equation(target="central", expression="-k * central",
                     source_location="Eq 1"),
            Equation(target="peripheral", expression="k * central",
                     source_location="Eq 2"),
        ),
        parameters=(
            Parameter(name="k", value=0.3, unit="1/h", source_location="Table 1",
                      confidence=ExtractionConfidence.QUOTED),
        ),
        initial_conditions=(
            Parameter(name="central", value=100.0, unit="mg", source_location="Methods",
                      confidence=ExtractionConfidence.QUOTED),
            Parameter(name="peripheral", value=0.0, unit="mg", source_location="Methods",
                      confidence=ExtractionConfidence.QUOTED),
        ),
    )

    archive = build_omex_archive(build_model_sbml(dossier), duration=24.0, steps=240)
    reingested = ingest_omex(archive, entry="two_compartment")

    assert set(reingested.state_variables) == {"central", "peripheral"}
    assert {p.name: p.value for p in reingested.initial_conditions} == {
        "central": 100.0, "peripheral": 0.0
    }
    assert {p.name: p.value for p in reingested.parameters} == {"k": 0.3}
    assert reingested.targetable_claims() == ()
    assert {a.filename for a in reingested.artifacts} == {"model.xml", "experiment.sedml"}
    # An archive that disagrees with itself is recorded as a load-bearing gap; ours must not.
    assert not [g for g in reingested.gaps if "the experiment" in g.detail]


def test_the_document_declares_the_dialect_its_sampling_attribute_belongs_to() -> None:
    """L1V3 spells the sample count `numberOfPoints`; `numberOfSteps` arrives in L1V4.

    Declaring the earlier dialect over the later attribute writes a document that reads *here* —
    Reprolith's parser looks for `numberOfSteps` — and fails validation everywhere else, with its
    sampling invisible to a strict reader. libSEDML rejected exactly that before this was fixed.
    """
    root = ET.fromstring(build_experiment_sedml(_MODEL, duration=24.0, steps=240))
    assert root.tag.startswith("{http://sed-ml.org/sed-ml/level1/version4}")
    assert (root.get("level"), root.get("version")) == ("1", "4")
    course = next(e for e in root.iter() if e.tag.endswith("uniformTimeCourse"))
    assert course.get("numberOfSteps") == "240"


def test_an_independent_sedml_library_reads_the_document_without_error() -> None:
    """The writer's own reader agreeing with it proves nothing about the standard.

    Skipped where libSEDML is not installed, which includes the required-checks gate: it is not a
    dependency of Reprolith, and the core stays dependency-free.
    """
    libsedml = pytest.importorskip(
        "libsedml", reason="python-libsedml is not installed; this check is local-only"
    )
    document = libsedml.readSedMLFromString(
        build_experiment_sedml(_MODEL, duration=24.0, steps=240)
    )
    assert document.getNumErrors() == 0, document.getErrorLog().toString()
    simulation = document.getSimulation(0)
    assert (simulation.getOutputEndTime(), simulation.getNumberOfSteps()) == (24.0, 240)
    assert document.getModel(0).getLanguage() == "urn:sedml:language:sbml.level-3.version-2"
