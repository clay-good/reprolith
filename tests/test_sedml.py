"""Reading a shipped SED-ML simulation recipe (roadmap #4: adopt-and-verify fast-path).

The parser is pure standard-library XML, so its tests are dependency-free and run in the core CI
job. One test additionally *runs* an adopted recipe under the pinned engine and needs the ``engine``
extra; it skips without it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from reprolith import ReferenceKind, SimulationRecipe, parse_sedml_recipes

_SEDML = (Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml").read_text(
    encoding="utf-8"
)


def test_extracts_the_uniform_time_course_recipes() -> None:
    recipes = parse_sedml_recipes(_SEDML)
    by_task = {r.task_id: r for r in recipes}
    # The recipe is read from the file, not guessed.
    a = by_task["task_fig2a"]
    assert a.model_ref == "kholodenko"
    assert a.duration == 9000.0 and a.steps == 1000
    assert "MAPK_PP" in a.observables  # the reported figure output


def test_a_task_over_a_modified_model_is_skipped_not_run_unmodified() -> None:
    # The shipped SED-ML defines a second model as the first plus thirteen parameter overrides —
    # including the Hill coefficient that makes Figure 2B oscillate at all — and hangs task_fig2b
    # on it. A recipe names one model file and carries no overrides, so emitting one for that task
    # would hand a consumer the *unmodified* model under the modified task's duration and call the
    # result a reproduction of that figure.
    assert "kholodenko_b" in _SEDML and "listOfChanges" in _SEDML
    assert {r.task_id for r in parse_sedml_recipes(_SEDML)} == {"task_fig2a"}


def test_a_parameter_scan_is_not_flattened_into_a_single_default_run() -> None:
    # The metformin SED-ML plots a repeatedTask that scans three doses; every data generator
    # references the scan, not the base task. Folding the scan onto its base task produced one
    # recipe carrying all the scan's observables but none of its doses — a run at the model's
    # default dose, which is not an arm the document plots.
    metformin = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.sedml"
    ).read_text(encoding="utf-8")
    assert "vectorRange" in metformin and "setValue" in metformin
    recipes = parse_sedml_recipes(metformin)
    # Only the plain base task remains runnable, and the scan's observables did not migrate onto it.
    assert [r.task_id for r in recipes] == ["task1"]
    assert recipes[0].duration == 30.0 and recipes[0].steps == 1000
    assert recipes[0].observables == ()


def test_a_pass_through_repeated_task_still_resolves_to_its_subtask() -> None:
    # A repeatedTask that varies nothing is just a wrapper, so its observables belong to the base
    # task — the behaviour that made the fast path work on real files stays.
    sedml = """<?xml version="1.0"?>
    <sedML xmlns="http://sed-ml.org/sed-ml/level1/version4">
      <listOfSimulations>
        <uniformTimeCourse id="s0" outputStartTime="0" outputEndTime="10" numberOfSteps="100"/>
      </listOfSimulations>
      <listOfTasks>
        <task id="t0" modelReference="m" simulationReference="s0"/>
        <repeatedTask id="rt0" resetModel="true">
          <listOfSubTasks><subTask order="1" task="t0"/></listOfSubTasks>
        </repeatedTask>
      </listOfTasks>
      <listOfDataGenerators>
        <dataGenerator id="d0">
          <listOfVariables>
            <variable id="v0" taskReference="rt0"
                      target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S1']"/>
          </listOfVariables>
        </dataGenerator>
      </listOfDataGenerators>
    </sedML>"""
    recipes = parse_sedml_recipes(sedml)
    assert [(r.task_id, r.observables) for r in recipes] == [("t0", ("S1",))]


def test_the_observed_quantity_is_the_leaf_of_the_target_not_an_ancestor() -> None:
    # A target may select its leaf by @name under an ancestor that carries an @id. Taking the last
    # @id anywhere in the path reported the compartment as the observed quantity; a target whose
    # leaf is not selected by @id is dropped instead of being substituted with its container.
    sedml = """<?xml version="1.0"?>
    <sedML xmlns="http://sed-ml.org/sed-ml/level1/version4">
      <listOfSimulations>
        <uniformTimeCourse id="s0" outputStartTime="0" outputEndTime="10" numberOfSteps="100"/>
      </listOfSimulations>
      <listOfTasks><task id="t0" modelReference="m" simulationReference="s0"/></listOfTasks>
      <listOfDataGenerators>
        <dataGenerator id="d0">
          <listOfVariables>
            <variable id="v0" taskReference="t0"
                      target="/sbml:sbml/sbml:model/sbml:listOfCompartments/sbml:compartment[@id='cyt']/sbml:listOfSpecies/sbml:species[@name='S1']"/>
            <variable id="v1" taskReference="t0"
                      target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S2']"/>
          </listOfVariables>
        </dataGenerator>
      </listOfDataGenerators>
    </sedML>"""
    assert parse_sedml_recipes(sedml)[0].observables == ("S2",)


def test_a_set_value_variable_is_not_read_as_an_observable() -> None:
    # Variables inside a setValue are inputs to a modification, never plotted quantities. Scanning
    # every variable in the document put one ahead of the real observable, so a consumer reading
    # observables[0] would have reproduced the wrong quantity.
    sedml = """<?xml version="1.0"?>
    <sedML xmlns="http://sed-ml.org/sed-ml/level1/version4">
      <listOfSimulations>
        <uniformTimeCourse id="s0" outputStartTime="0" outputEndTime="10" numberOfSteps="100"/>
      </listOfSimulations>
      <listOfTasks>
        <task id="t0" modelReference="m" simulationReference="s0"/>
        <repeatedTask id="rt0" range="r0" resetModel="true">
          <listOfRanges><vectorRange id="r0"><value>1</value></vectorRange></listOfRanges>
          <listOfChanges>
            <setValue modelReference="m" range="r0"
                      target="/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='dose']">
              <listOfVariables>
                <variable id="vx" taskReference="t0"
                          target="/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='NOT_PLOTTED']"/>
              </listOfVariables>
            </setValue>
          </listOfChanges>
          <listOfSubTasks><subTask order="1" task="t0"/></listOfSubTasks>
        </repeatedTask>
      </listOfTasks>
      <listOfDataGenerators>
        <dataGenerator id="d0">
          <listOfVariables>
            <variable id="v0" taskReference="t0"
                      target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S1']"/>
          </listOfVariables>
        </dataGenerator>
      </listOfDataGenerators>
    </sedML>"""
    assert parse_sedml_recipes(sedml)[0].observables == ("S1",)


def test_ill_formed_sedml_is_a_clear_error() -> None:
    with pytest.raises(ValueError, match="not parseable SED-ML"):
        parse_sedml_recipes("<sedML><unclosed>")


def test_a_task_without_a_uniform_time_course_is_skipped_not_guessed() -> None:
    # A steady-state task carries no single runnable time course, so no recipe is invented for it.
    sedml = """<?xml version="1.0"?>
    <sedML xmlns="http://sed-ml.org/sed-ml/level1/version4">
      <listOfSimulations><steadyState id="ss0"/></listOfSimulations>
      <listOfTasks><task id="t0" modelReference="m" simulationReference="ss0"/></listOfTasks>
    </sedML>"""
    assert parse_sedml_recipes(sedml) == []


@pytest.mark.skipif(
    importlib.util.find_spec("COPASI") is None,
    reason="the optional 'engine' extra (python-copasi) is not installed",
)
def test_an_adopted_recipe_runs_under_the_pinned_engine() -> None:
    # Adopt-and-verify: the recipe read from the SED-ML drives the simulation directly — no
    # hand-specified species/duration/steps.
    from reprolith import simulate

    model = (Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.xml").read_text(
        encoding="utf-8"
    )
    recipe: SimulationRecipe = next(r for r in parse_sedml_recipes(_SEDML) if r.task_id == "task_fig2a")
    times, values = simulate(
        model, recipe.observables[0], duration=recipe.duration, steps=recipe.steps
    )
    assert len(times) == len(values) == recipe.steps + 1
    assert max(values) > 0  # MAPK_PP is produced over the adopted time course


@pytest.mark.skipif(
    importlib.util.find_spec("COPASI") is None or importlib.util.find_spec("roadrunner") is None,
    reason="needs the 'engine' (COPASI) and 'corroborate' (libRoadRunner) extras",
)
def test_an_adopted_recipe_is_engine_independent_end_to_end() -> None:
    # The full fast-path: read the shipped recipe, then verify it cross-engine — the adopted
    # duration/steps/observable drive both simulators and they agree.
    from reprolith import corroborate_curve

    model = (Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.xml").read_text(
        encoding="utf-8"
    )
    recipe = next(r for r in parse_sedml_recipes(_SEDML) if r.task_id == "task_fig2a")
    result = corroborate_curve(
        model, recipe.observables[0], duration=recipe.duration, steps=recipe.steps
    )
    assert result.stable


def test_a_model_inheriting_changes_one_link_up_is_skipped_too() -> None:
    # A model defined as source="#other" inherits that model's listOfChanges, so a task over it
    # runs at overridden values the recipe cannot name — exactly the case already refused when the
    # changes sit on the model itself, one link further out.
    sedml = """<?xml version="1.0"?>
    <sedML xmlns="http://sed-ml.org/sed-ml/level1/version4">
      <listOfModels>
        <model id="base" source="model.xml" language="urn:sedml:language:sbml"/>
        <model id="A" source="#base" language="urn:sedml:language:sbml">
          <listOfChanges>
            <changeAttribute target="/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='k']"
                             newValue="99"/>
          </listOfChanges>
        </model>
        <model id="B" source="#A" language="urn:sedml:language:sbml"/>
      </listOfModels>
      <listOfSimulations>
        <uniformTimeCourse id="s0" outputStartTime="0" outputEndTime="10" numberOfSteps="100"/>
      </listOfSimulations>
      <listOfTasks>
        <task id="t_base" modelReference="base" simulationReference="s0"/>
        <task id="t_on_A" modelReference="A" simulationReference="s0"/>
        <task id="t_on_B" modelReference="B" simulationReference="s0"/>
      </listOfTasks>
    </sedML>"""
    assert [r.task_id for r in parse_sedml_recipes(sedml)] == ["t_base"]


def test_an_unreadable_time_course_attribute_is_reported_as_unparseable_sedml() -> None:
    """One error type for an unreadable document — on every attribute, not two of the four."""
    import pytest
    from reprolith.sedml import parse_sedml_recipes

    template = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfSimulations>
  <uniformTimeCourse id="s1" initialTime="{initial}" outputStartTime="{start}"
                     outputEndTime="{end}" numberOfSteps="{steps}"/>
 </listOfSimulations>
</sedML>"""
    good = {"initial": "0", "start": "0", "end": "10", "steps": "10"}
    assert parse_sedml_recipes(template.format(**good)) == []  # no tasks, but it parses

    for attribute in ("initial", "start", "end", "steps"):
        with pytest.raises(ValueError, match="not parseable SED-ML"):
            parse_sedml_recipes(template.format(**{**good, attribute: "abc"}))


def test_a_skipped_simulation_cannot_fail_the_whole_document() -> None:
    """A time course this parser deliberately drops must not be parsed for values nobody uses.

    Hoisting the conversions above the skip so they could share one `try` meant an unreadable
    attribute on a task no recipe describes failed the entire document.
    """
    from reprolith.sedml import parse_sedml_recipes

    document = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfModels><model id="m1" language="urn:sedml:language:sbml" source="m.xml"/></listOfModels>
 <listOfSimulations>
  <uniformTimeCourse id="skipme" initialTime="5" outputStartTime="5"
                     outputEndTime="not-a-number" numberOfSteps="10"/>
  <uniformTimeCourse id="good" initialTime="0" outputStartTime="0"
                     outputEndTime="10" numberOfSteps="100"/>
 </listOfSimulations>
 <listOfTasks><task id="t1" modelReference="m1" simulationReference="good"/></listOfTasks>
</sedML>"""
    recipes = parse_sedml_recipes(document)
    assert [(r.task_id, r.duration, r.steps) for r in recipes] == [("t1", 10.0, 100)]


# --- 2.2 enumerating the claims a document stakes ------------------------------------


def test_claim_enumeration_matches_a_manual_read_of_the_shipped_document() -> None:
    """The manual read of the BioModels SED-ML for Kholodenko: two figures, two curves each.

    Figure 2A plots MAPK_PP and MAPK from the unmodified model; Figure 2B plots the same two
    quantities from the model the document modifies. Everything else the document emits is a
    report, and no report is a published result: two of them restate the plots, and the third
    dumps every symbol in the model.
    """
    from reprolith import enumerate_sedml_claims

    claims = enumerate_sedml_claims(_SEDML)
    targetable = [c for c in claims if c.targetable]

    assert [(c.quantity, c.source_location.split(",")[0]) for c in targetable] == [
        ("MAPK_PP", "SED-ML plot2D 'plot_0' (Figure 2A)"),
        ("MAPK", "SED-ML plot2D 'plot_0' (Figure 2A)"),
        ("MAPK_PP", "SED-ML plot2D 'plot_1' (Figure 2B)"),
        ("MAPK", "SED-ML plot2D 'plot_1' (Figure 2B)"),
    ]
    # Figure 2B is a different model from Figure 2A, and the claim says which it holds under.
    assert targetable[0].conditions == "task 'task_fig2a', model 'kholodenko', simulation 'sim0'"
    assert targetable[2].conditions == "task 'task_fig2b', model 'kholodenko_b', simulation 'sim1'"
    # The document says what to plot, never what the paper's figure showed: no reference values.
    assert all(c.reference_kind is ReferenceKind.DIGITIZED_FIGURE for c in targetable)
    assert all(c.reference_data == () for c in targetable)

    # Nothing is dropped: the seventeen columns of the auto-generated report that no curve plots
    # are retained as non-targetable — reaction fluxes and the compartment volume included.
    retained = [c for c in claims if not c.targetable]
    assert [c.quantity for c in retained] == [
        "MKKK", "MKKK_P", "MKK", "MKK_P", "MKK_PP", "MAPK_P", "uVol",
        *[f"J{i}" for i in range(10)],
    ]
    assert all("report" in c.source_location for c in retained)


def test_claims_are_uniquely_identified_and_validate_inside_a_dossier() -> None:
    from reprolith import Dossier, enumerate_sedml_claims

    claims = enumerate_sedml_claims(_SEDML)
    assert len({c.id for c in claims}) == len(claims)
    assert Dossier(entry="BIOMD0000000010", claims=claims).validate() == []


def test_the_time_axis_is_not_a_claim_and_a_plotted_column_is_not_repeated() -> None:
    """Time is what a curve is plotted against; a report column a curve plots is that curve."""
    from reprolith import enumerate_sedml_claims

    document = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfTasks><task id="t1" modelReference="m1" simulationReference="s1"/></listOfTasks>
 <listOfDataGenerators>
  <dataGenerator id="g_time" name="t/60">
   <listOfVariables><variable id="v" symbol="urn:sedml:symbol:time" taskReference="t1"/></listOfVariables>
  </dataGenerator>
  <dataGenerator id="g_S1">
   <listOfVariables><variable id="w" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S1']" taskReference="t1"/></listOfVariables>
  </dataGenerator>
 </listOfDataGenerators>
 <listOfOutputs>
  <plot2D id="p1" name="Figure 1">
   <listOfCurves><curve id="c1" name="S1" xDataReference="g_time" yDataReference="g_S1"/></listOfCurves>
  </plot2D>
  <report id="r1">
   <listOfDataSets>
    <dataSet id="d_time" label="Time" dataReference="g_time"/>
    <dataSet id="d_S1" label="S1" dataReference="g_S1"/>
   </listOfDataSets>
  </report>
 </listOfOutputs>
</sedML>"""
    assert [(c.id, c.targetable) for c in enumerate_sedml_claims(document)] == [("c1", True)]


def test_a_report_only_document_abstains_rather_than_inventing_targets() -> None:
    """Nothing in a report says which of its columns the paper published, so none is a target."""
    from reprolith import enumerate_sedml_claims

    document = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfTasks><task id="t1" modelReference="m1" simulationReference="s1"/></listOfTasks>
 <listOfDataGenerators>
  <dataGenerator id="g_S1">
   <listOfVariables><variable id="w" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S1']" taskReference="t1"/></listOfVariables>
  </dataGenerator>
 </listOfDataGenerators>
 <listOfOutputs>
  <report id="r1" name="Table 1">
   <listOfDataSets><dataSet id="d_S1" label="S1" dataReference="g_S1"/></listOfDataSets>
  </report>
 </listOfOutputs>
</sedML>"""
    claims = enumerate_sedml_claims(document)
    assert [(c.id, c.targetable) for c in claims] == [("d_S1", False)]
    assert claims[0].source_location == "SED-ML report 'r1' (Table 1), dataSet 'd_S1'"


def test_a_plot3d_surface_is_a_claim_about_its_dependent_quantity() -> None:
    """A surface's z is the quantity; reading its y would report the second axis as the result."""
    from reprolith import enumerate_sedml_claims

    document = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfTasks><task id="t1" modelReference="m1" simulationReference="s1"/></listOfTasks>
 <listOfDataGenerators>
  <dataGenerator id="g_x"><listOfVariables><variable id="a" symbol="urn:sedml:symbol:time" taskReference="t1"/></listOfVariables></dataGenerator>
  <dataGenerator id="g_y"><listOfVariables><variable id="b" target="/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='k']" taskReference="t1"/></listOfVariables></dataGenerator>
  <dataGenerator id="g_z"><listOfVariables><variable id="c" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S1']" taskReference="t1"/></listOfVariables></dataGenerator>
 </listOfDataGenerators>
 <listOfOutputs>
  <plot3D id="p3" name="Figure 4">
   <listOfSurfaces>
    <surface id="s1" xDataReference="g_x" yDataReference="g_y" zDataReference="g_z"/>
   </listOfSurfaces>
  </plot3D>
 </listOfOutputs>
</sedML>"""
    claim = enumerate_sedml_claims(document)[0]
    assert (claim.id, claim.quantity, claim.targetable) == ("s1", "S1", True)
    assert claim.source_location == "SED-ML plot3D 'p3' (Figure 4), surface 's1'"


def test_unparseable_sedml_is_rejected_by_the_claim_reader_too() -> None:
    from reprolith import enumerate_sedml_claims

    with pytest.raises(ValueError, match="not parseable SED-ML"):
        enumerate_sedml_claims("<sedML>")


def test_a_curve_mixing_time_with_a_species_is_still_a_claim_about_the_species() -> None:
    """Only a generator built from nothing but time is the axis; S1/t asserts something about S1."""
    from reprolith import enumerate_sedml_claims

    document = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfTasks><task id="t1" modelReference="m1" simulationReference="s1"/></listOfTasks>
 <listOfDataGenerators>
  <dataGenerator id="g_x"><listOfVariables><variable id="a" symbol="urn:sedml:symbol:time" taskReference="t1"/></listOfVariables></dataGenerator>
  <dataGenerator id="g_rate" name="S1 per unit time">
   <listOfVariables>
    <variable id="b" symbol="urn:sedml:symbol:time" taskReference="t1"/>
    <variable id="c" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='S1']" taskReference="t1"/>
   </listOfVariables>
  </dataGenerator>
 </listOfDataGenerators>
 <listOfOutputs>
  <plot2D id="p1"><listOfCurves>
   <curve id="c1" xDataReference="g_x" yDataReference="g_rate"/>
  </listOfCurves></plot2D>
 </listOfOutputs>
</sedML>"""
    claim = enumerate_sedml_claims(document)[0]
    assert (claim.id, claim.quantity) == ("c1", "S1")


def test_a_curve_from_a_scanning_task_says_so_in_its_conditions() -> None:
    """The metformin document's 81 plotted curves are all arms of one range scan.

    Named only as `task 'task2'`, a claim from a scan is indistinguishable from a claim from a
    single run — and the scan is precisely why no recipe is adopted for it. The repeated task
    also inherits the model and simulation of the task it wraps, which is what it runs.
    """
    from reprolith import enumerate_sedml_claims

    document = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
 <listOfTasks>
  <task id="t1" modelReference="m1" simulationReference="s1"/>
  <repeatedTask id="scan" range="doses" resetModel="true">
   <listOfRanges><vectorRange id="doses"><value>500</value><value>1000</value></vectorRange></listOfRanges>
   <listOfSubTasks><subTask order="1" task="t1"/></listOfSubTasks>
  </repeatedTask>
 </listOfTasks>
 <listOfDataGenerators>
  <dataGenerator id="g_x"><listOfVariables><variable id="a" symbol="urn:sedml:symbol:time" taskReference="scan"/></listOfVariables></dataGenerator>
  <dataGenerator id="g_C"><listOfVariables><variable id="b" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='C']" taskReference="scan"/></listOfVariables></dataGenerator>
 </listOfDataGenerators>
 <listOfOutputs>
  <plot2D id="p1" name="Figure 3"><listOfCurves>
   <curve id="c1" name="C" xDataReference="g_x" yDataReference="g_C"/>
  </listOfCurves></plot2D>
 </listOfOutputs>
</sedML>"""
    claim = enumerate_sedml_claims(document)[0]
    assert claim.conditions == (
        "task 'scan' (repeated over range 'doses'), model 'm1', simulation 's1'"
    )


def test_the_shipped_metformin_document_enumerates_as_a_scan() -> None:
    """A second real document, from a different tool: every plotted curve is one scan arm."""
    from reprolith import enumerate_sedml_claims

    metformin = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.sedml"
    ).read_text(encoding="utf-8")
    claims = enumerate_sedml_claims(metformin)
    targetable = [c for c in claims if c.targetable]

    assert len(targetable) == 81
    assert all("repeated over range 'range0'" in c.conditions for c in targetable)
    assert all(c.reference_kind is ReferenceKind.DIGITIZED_FIGURE for c in targetable)
    assert len({c.id for c in claims}) == len(claims)


def test_the_published_worked_example_pair_agrees_with_itself() -> None:
    """The repository publishes a model and a document side by side; they must still match.

    Nothing else checks the pair Reprolith ships as its own walkable example, so an edit to
    either file could rename a species out from under 81 plotted curves and no gate would say so.
    """
    from reprolith.omex import archive_mismatches

    examples = Path(__file__).parent.parent / "datasets" / "worked_examples"
    sedml = (examples / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8")
    sbml = (examples / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")

    assert archive_mismatches(sedml, sbml) == []
