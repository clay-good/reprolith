"""Writing a COMBINE archive, and reading back exactly what was written.

The reading half of the fast path has tests (``test_omex.py``, ``test_archive_end_to_end.py``).
This is the writing half, and it asks three different questions of the output:

* **Reprolith's own reader accepts it**, and it asserts no more than the reconstruction knows.
  These need no optional extra — the writer and the SED-ML/manifest readers are pure standard
  library.
* **An independent implementation accepts it.** libSEDML for the document and libCombine for the
  archive, behind the ``validate`` extra. This is the question that matters most: the writer's
  first version declared the wrong SED-ML level and every other test in this file passed, because
  it round-tripped through the parser in this same package. A writer validated only by its own
  reader is not validated.
* **A dossier comes back out of it**, which parses the model and so needs libSBML.
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
    members = _members(build_omex_archive(_MODEL, build_experiment_sedml(_MODEL, duration=24.0, steps=240)))
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
    first = build_omex_archive(_MODEL, build_experiment_sedml(_MODEL, duration=24.0, steps=240))
    second = build_omex_archive(_MODEL, build_experiment_sedml(_MODEL, duration=24.0, steps=240))
    assert first == second
    assert first != build_omex_archive(_MODEL, build_experiment_sedml(_MODEL, duration=24.0, steps=241))


def test_the_model_and_the_experiment_cannot_share_a_location() -> None:
    with pytest.raises(ValueError, match="one file per location"):
        build_omex_archive(
            _MODEL, build_experiment_sedml(_MODEL, duration=1.0, steps=10),
            model_location="m.xml", experiment_location="m.xml",
        )


def test_a_model_at_a_nested_location_is_named_relative_to_the_document() -> None:
    """A reader resolves `source` relative to the document, so a nested layout needs the path
    the document would follow, not the one the archive stores."""
    archive = build_omex_archive(
        _MODEL,
        build_experiment_sedml(_MODEL, duration=1.0, steps=10, model_location="../models/m.xml"),
        model_location="models/m.xml",
        experiment_location="experiments/e.sedml",
    )
    members = _members(archive)
    assert set(members) == {"manifest.xml", "models/m.xml", "experiments/e.sedml"}
    assert sedml_model_sources(members["experiments/e.sedml"]) == ("../models/m.xml",)


def test_a_document_pointing_somewhere_the_archive_does_not_store_is_refused() -> None:
    """The mistake the nested case makes easy: a source that resolves to a file that is not there.

    `ingest_omex` refuses such an archive on the way back in. Refusing it on the way out names it
    where it was made, instead of shipping bytes that only fail for whoever opens them.
    """
    with pytest.raises(ValueError, match="the document's source is what a reader follows"):
        build_omex_archive(
            _MODEL,
            build_experiment_sedml(_MODEL, duration=1.0, steps=10, model_location="models/m.xml"),
            model_location="models/m.xml",
            experiment_location="experiments/e.sedml",
        )


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

    model_sbml = build_model_sbml(dossier)
    archive = build_omex_archive(
        model_sbml, build_experiment_sedml(model_sbml, duration=24.0, steps=240)
    )
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

    Skipped on the dependency-free core gate, where no optional extra is installed; the `validate`
    extra puts libSEDML in the extras job, so an independent implementation reads what Reprolith
    writes on every CI run. It was local-only when it caught the level defect, which meant the
    guard that found that bug was not running anywhere it could catch the next one.
    """
    libsedml = pytest.importorskip(
        "libsedml", reason="the optional 'validate' extra (python-libsedml) is not installed"
    )
    document = libsedml.readSedMLFromString(
        build_experiment_sedml(_MODEL, duration=24.0, steps=240)
    )
    assert document.getNumErrors() == 0, document.getErrorLog().toString()
    simulation = document.getSimulation(0)
    assert (simulation.getOutputEndTime(), simulation.getNumberOfSteps()) == (24.0, 240)
    assert document.getModel(0).getLanguage() == "urn:sedml:language:sbml.level-3.version-2"


def _bundle(*steps: object) -> object:
    from reprolith import EnginePin, ReconstructionBundle

    return ReconstructionBundle(
        entry="two_compartment",
        engine_pin=EnginePin(engine="copasi", version="4.46.300", algorithm="deterministic-lsoda"),
        recipe=tuple(steps),  # type: ignore[arg-type]
    )


def _step(**kwargs: object) -> object:
    from reprolith import RecipeStep

    defaults: dict[str, object] = {
        "claim_id": "C1", "protocol": "Table 1", "output": "[central]",
        "time_span": "0-24.0", "steps": 480,
    }
    defaults.update(kwargs)
    return RecipeStep(**defaults)  # type: ignore[arg-type]


def test_a_recipe_step_becomes_a_task_that_runs_the_window_it_records() -> None:
    from reprolith import build_bundle_sedml

    experiment = build_bundle_sedml(_bundle(_step()), _MODEL)  # type: ignore[arg-type]

    assert experiment.expressed == ("C1",)
    assert experiment.unexpressed == ()
    recipes = parse_sedml_recipes(experiment.sedml)
    assert len(recipes) == 1
    assert (recipes[0].duration, recipes[0].steps) == (24.0, 480)
    assert recipes[0].observables == ("central",)


def test_the_override_that_distinguishes_two_claims_is_written_into_the_document() -> None:
    """The point of exporting a bundle rather than a bare run.

    Two claims on one model differ by the values they set. Without the overrides in the file, an
    exported archive runs the same arm twice — the shape that made the shipped metformin bundle's
    two steps identical before `parameter_overrides` existed at all.
    """
    from reprolith import build_bundle_sedml

    experiment = build_bundle_sedml(
        _bundle(
            _step(claim_id="low"),
            _step(claim_id="high", parameter_overrides=(("k", 0.6),)),
        ),  # type: ignore[arg-type]
        _MODEL,
    )

    assert experiment.expressed == ("low", "high")
    root = ET.fromstring(experiment.sedml)
    changes = [e for e in root.iter() if e.tag.endswith("changeAttribute")]
    assert len(changes) == 1
    assert changes[0].get("newValue") == "0.6"
    assert changes[0].get("target").endswith("sbml:parameter[@id='k']/@value")
    # The overridden arm runs a model *derived* from the base one, which is exactly why the recipe
    # parser refuses to adopt it back: an adopted recipe carries no overrides.
    assert [r.task_id for r in parse_sedml_recipes(experiment.sedml)] == ["task1"]


def test_two_claims_run_the_same_way_share_one_simulation() -> None:
    from reprolith import build_bundle_sedml

    experiment = build_bundle_sedml(
        _bundle(_step(claim_id="a"), _step(claim_id="b"),
                _step(claim_id="c", time_span="0-48.0")),  # type: ignore[arg-type]
        _MODEL,
    )
    root = ET.fromstring(experiment.sedml)
    courses = [e for e in root.iter() if e.tag.endswith("uniformTimeCourse")]
    assert [c.get("outputEndTime") for c in courses] == ["24.0", "48.0"]


def test_a_step_the_document_cannot_state_is_listed_not_dropped() -> None:
    """An archive quietly short of a claim reads as a reconstruction that never had one."""
    from reprolith import build_bundle_sedml

    experiment = build_bundle_sedml(
        _bundle(
            _step(claim_id="ok"),
            _step(claim_id="no_count", steps=None),
            _step(claim_id="odd_window", time_span="steady state"),
            _step(claim_id="no_output", output="[effect]"),
            _step(claim_id="ghost_override", parameter_overrides=(("absent", 1.0),)),
        ),  # type: ignore[arg-type]
        _MODEL,
    )

    assert experiment.expressed == ("ok",)
    reasons = dict(line.split(": ", 1) for line in experiment.unexpressed)
    assert set(reasons) == {
        "claim 'no_count'", "claim 'odd_window'", "claim 'no_output'", "claim 'ghost_override'"
    }
    assert "no sample count" in reasons["claim 'no_count'"]
    assert "steady state" in reasons["claim 'odd_window'"]
    assert "no top-level element 'effect'" in reasons["claim 'no_output'"]
    assert "runs the unmodified model" in reasons["claim 'ghost_override'"]


def test_a_recipe_with_nothing_expressible_is_refused_rather_than_written_empty() -> None:
    from reprolith import build_bundle_sedml

    with pytest.raises(ValueError, match="describe no run"):
        build_bundle_sedml(_bundle(_step(steps=None)), _MODEL)  # type: ignore[arg-type]


def test_a_window_written_with_a_unit_is_still_the_number_the_run_used() -> None:
    """`time_span` is free text: the committed bundles say `0-24.0` and the tests say `0-24 h`.
    The number is in the model's own time unit, which is how the certified run consumed it."""
    from reprolith import build_bundle_sedml

    experiment = build_bundle_sedml(_bundle(_step(time_span="0-24 h")), _MODEL)  # type: ignore[arg-type]
    assert parse_sedml_recipes(experiment.sedml)[0].duration == 24.0


def test_the_published_metformin_bundle_exports_to_a_runnable_archive() -> None:
    """The committed reconstruction, not a fixture: the thing the registry publishes as
    "how to re-run this" becomes a file a simulator can open.

    The 779.9 mg free-base dose is the whole point. It is what separates the 1000 mg claim from
    the 500 mg one, it lived only in Reprolith's JSON, and taken naively (1000 mg straight in) the
    model overshoots the paper by 26%.
    """
    import json
    from pathlib import Path

    from reprolith import build_bundle_sedml, build_omex_archive, bundle_from_dict

    root = Path(__file__).parent.parent
    bundle = bundle_from_dict(
        json.loads(
            (root / "datasets/milestone/bundles/BIOMD0000001028.json").read_text(
                encoding="utf-8"
            )
        )
    )
    model = (
        root / "datasets/worked_examples/Zake2021_metformin_human_single_PO.xml"
    ).read_text(encoding="utf-8")

    experiment = build_bundle_sedml(bundle, model)
    # Every claim without a schedule, in recipe order — counted from the bundle rather than
    # listed here, because this entry's claims went from two to thirty-three.
    assert experiment.expressed == tuple(
        step.claim_id for step in bundle.recipe if not step.schedule
    )
    assert len(experiment.expressed) > 2
    # The entry's validation-arm claims run after a pre-dose, which a uniform time course cannot
    # state. They are listed with the reason rather than written as a plain run — which would ship
    # a document that runs the reported window alone and reproduces a neighbouring arm, the
    # failure this whole worked example is about. Counted from the bundle rather than written
    # here, so adding another such claim does not make this a chore.
    scheduled = [step.claim_id for step in bundle.recipe if step.schedule]
    assert scheduled, "no claim in this bundle has a schedule; this check would pass vacuously"
    assert len(experiment.unexpressed) == len(scheduled)
    assert all("prior administration" in reason for reason in experiment.unexpressed)
    assert all(
        any(claim_id in reason for reason in experiment.unexpressed) for claim_id in scheduled
    )

    # One change per distinct dose arm, and every one of them addresses the dose parameter.
    # Written as a single expected pair, this said "the 779.9 override is in the document"; the
    # entry now has three arms, and what matters is unchanged — each arm's dose is written, and
    # nothing else is.
    changes = [e for e in ET.fromstring(experiment.sedml).iter() if e.tag.endswith("changeAttribute")]
    written = {(c.get("target").rsplit("[@id=", 1)[1], c.get("newValue")) for c in changes}
    expected = {
        ("'Metformin_Dose_in_Lumen_in_mg']/@value", repr(float(value)))
        for step in bundle.recipe if not step.schedule
        for _, value in step.parameter_overrides
    }
    assert written == expected
    assert ("'Metformin_Dose_in_Lumen_in_mg']/@value", "779.9") in written
    # Both arms record the same output, and the recipe's `[mPlasmaVenous]` addresses the species.
    assert archive_mismatches(experiment.sedml, model) == []

    archive = build_omex_archive(model, experiment.sedml)
    assert set(_members(archive)) == {"manifest.xml", "model.xml", "experiment.sedml"}


def test_an_independent_sedml_library_reads_the_exported_bundle_without_error() -> None:
    import json
    from pathlib import Path

    from reprolith import build_bundle_sedml, bundle_from_dict

    libsedml = pytest.importorskip(
        "libsedml", reason="the optional 'validate' extra (python-libsedml) is not installed"
    )
    root = Path(__file__).parent.parent
    bundle = bundle_from_dict(
        json.loads(
            (root / "datasets/milestone/bundles/BIOMD0000001028.json").read_text(
                encoding="utf-8"
            )
        )
    )
    model = (
        root / "datasets/worked_examples/Zake2021_metformin_human_single_PO.xml"
    ).read_text(encoding="utf-8")

    document = libsedml.readSedMLFromString(build_bundle_sedml(bundle, model).sedml)
    assert document.getNumErrors() == 0, document.getErrorLog().toString()
    # One task and one model per *distinct run*, not per claim: thirty-three claims over three
    # dose arms is three modified models plus the base one, and four tasks. Written per claim it
    # was thirty of each, telling a reproducer to integrate the same model ten times to read ten
    # of its species.
    arms = {step.parameter_overrides for step in bundle.recipe if not step.schedule}
    assert document.getNumTasks() == len(arms)
    assert document.getNumModels() == len(arms)


def test_the_exported_document_reproduces_the_published_number_when_run() -> None:
    """The loop closed with the engine in it: export the bundle, read the recipe back out of the
    exported file, run it, and get the certificate's own 500 mg answer (6.07 vs a reported 6.2).

    Only the unmodified arm can be checked this way, and that is not a gap in the export: an
    adopted recipe carries no overrides by design, so the 1000 mg arm's `changeAttribute` is
    verified by reading the document, not by adopting it.
    """
    import json
    from pathlib import Path

    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    from reprolith import build_bundle_sedml, bundle_from_dict, simulate

    root = Path(__file__).parent.parent
    bundle = bundle_from_dict(
        json.loads(
            (root / "datasets/milestone/bundles/BIOMD0000001028.json").read_text(
                encoding="utf-8"
            )
        )
    )
    model = (
        root / "datasets/worked_examples/Zake2021_metformin_human_single_PO.xml"
    ).read_text(encoding="utf-8")

    recipe = parse_sedml_recipes(build_bundle_sedml(bundle, model).sedml)
    assert [r.task_id for r in recipe] == ["task1"]  # the 500 mg arm; the other carries overrides
    _, values = simulate(
        model, recipe[0].observables[0], duration=recipe[0].duration, steps=recipe[0].steps
    )
    assert max(values) == pytest.approx(6.07, abs=0.02)


def test_the_published_worked_example_archive_is_what_the_export_produces_today() -> None:
    """A committed binary is only honest if it is checkable. The bytes are deterministic, so this
    regenerates the published archive and compares — a drifted artifact fails rather than sitting
    there looking current."""
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    try:
        from export_worked_example_archive import ARCHIVE, export
    finally:
        sys.path.pop(0)

    archive, expressed, unexpressed = export()
    assert expressed[:2] == ("Cmax-500mg", "Cmax-1000mg")
    # The pre-dose arms are named, not written: see the test above for why. Every claim of the
    # entry is accounted for, one way or the other — a claim in neither list would be dropped.
    claims = json.loads(
        (Path(__file__).parent.parent / "datasets/pkpd_claims.json").read_text(encoding="utf-8")
    )["entries"]["BIOMD0000001028"]["claims"]
    assert len(expressed) + len(unexpressed) == len(claims)
    assert ARCHIVE.read_bytes() == archive, (
        "datasets/worked_examples/metformin_reconstruction.omex is stale; regenerate it with "
        "python scripts/export_worked_example_archive.py"
    )


@pytest.mark.parametrize("location", ["../escape.xml", "/abs.xml", "./model.xml", ""])
def test_a_member_name_that_is_not_inside_the_archive_is_refused(location: str) -> None:
    """A zip member name is stored verbatim, so where `../x.xml` lands is the extractor's
    decision — not one an exported artifact gets to make on someone else's machine."""
    with pytest.raises(ValueError, match="plain relative path inside the archive"):
        build_omex_archive(
            _MODEL,
            build_experiment_sedml(_MODEL, duration=1.0, steps=10),
            model_location=location,
        )


@pytest.mark.parametrize(
    ("fixture", "package"),
    [
        ("datasets/constraint_based/e_coli_core.xml", "fbc"),
        ("tests/fixtures/toggle_qual.xml", "qual"),
    ],
)
def test_a_model_no_time_course_describes_is_refused(fixture: str, package: str) -> None:
    """Reprolith certifies six classes and only two of them are integrated trajectories.

    An FBA model is solved at steady state and a logical one advances in discrete update steps.
    Neither is run as a uniform time course — and a document that wrote one for them would be
    perfectly valid SED-ML describing a run nobody performs, which is worse than a refusal.
    """
    from pathlib import Path

    model = (Path(__file__).parent.parent / fixture).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match=f"the SBML '{package}' package"):
        build_experiment_sedml(model, duration=1.0, steps=10)


def test_a_model_that_only_annotates_itself_is_still_exportable() -> None:
    """The guard names the packages that change what a *run* is. `layout` is not one of them, and
    refusing it would reject an ordinary BioModels export for carrying diagram coordinates."""
    annotated = _MODEL.replace(
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core"',
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core"'
        ' xmlns:layout="http://www.sbml.org/sbml/level3/version1/layout/version1"'
        ' layout:required="false"',
    )
    assert parse_sedml_recipes(build_experiment_sedml(annotated, duration=1.0, steps=10))


def test_an_independent_archive_library_reads_what_the_packager_wrote() -> None:
    """The manifest is a written artifact, and until this test nothing but `ingest_omex` had ever
    read one back. The SED-ML level defect is what that shape of gap produces: a file that is
    correct against its author's own reader and wrong against the specification.

    Skipped where the `validate` extra is absent; the extras job installs it.
    """
    libcombine = pytest.importorskip(
        "libcombine", reason="the optional 'validate' extra (python-libcombine) is not installed"
    )
    import tempfile
    from pathlib import Path

    archive = build_omex_archive(_MODEL, build_experiment_sedml(_MODEL, duration=24.0, steps=240))
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / "written.omex"
        path.write_bytes(archive)
        combine = libcombine.CombineArchive()
        try:
            assert combine.initializeFromArchive(str(path)), "libCombine cannot open the archive"
            entries = {
                combine.getEntry(i).getLocation(): (
                    combine.getEntry(i).getFormat(), combine.getEntry(i).getMaster()
                )
                for i in range(combine.getNumEntries())
            }
            spec = "http://identifiers.org/combine.specifications/"
            assert entries == {
                "./manifest.xml": (f"{spec}omex-manifest", False),
                "./model.xml": (f"{spec}sbml.level-3.version-2", False),
                "./experiment.sedml": (f"{spec}sed-ml.level-1.version-4", True),
            }
            # An archive that does not single out one experiment is one `ingest_omex` refuses, so
            # the writer has to produce one an independent reader agrees is singled out.
            assert combine.getMasterFile().getLocation() == "./experiment.sedml"
            extracted = Path(workspace) / "out"
            assert combine.extractTo(str(extracted))
            assert (extracted / "model.xml").read_text(encoding="utf-8") == _MODEL
        finally:
            combine.cleanUp()
