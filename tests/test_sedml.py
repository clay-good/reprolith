"""Reading a shipped SED-ML simulation recipe (roadmap #4: adopt-and-verify fast-path).

The parser is pure standard-library XML, so its tests are dependency-free and run in the core CI
job. One test additionally *runs* an adopted recipe under the pinned engine and needs the ``engine``
extra; it skips without it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from reprolith import SimulationRecipe, parse_sedml_recipes

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
