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
    # The shipped SED-ML describes two figure tasks; the recipe is read from the file, not guessed.
    assert set(by_task) == {"task_fig2a", "task_fig2b"}

    a = by_task["task_fig2a"]
    assert a.model_ref == "kholodenko"
    assert a.duration == 9000.0 and a.steps == 1000
    assert "MAPK_PP" in a.observables  # the reported figure output

    b = by_task["task_fig2b"]
    assert b.duration == 12000.0 and b.steps == 1000
    assert b.observables == ("MAPK_PP", "MAPK")


def test_reads_a_pk_pd_recipe_with_repeated_task_and_parameter_observables() -> None:
    # The fast-path is cross-class: the metformin PK/PD SED-ML observes amount *parameters* (not
    # species) and wraps its time course in a repeatedTask. The parser resolves the repeatedTask to
    # its base task and reads the parameter observables — real-world SED-ML variety, not the simple case.
    metformin = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.sedml"
    ).read_text(encoding="utf-8")
    recipes = parse_sedml_recipes(metformin)
    assert len(recipes) == 1
    recipe = recipes[0]
    assert recipe.duration == 30.0 and recipe.steps == 1000
    # Observables are amount parameters resolved from the repeatedTask onto the runnable base task.
    assert "mgArterialPlasma" in recipe.observables
    assert len(recipe.observables) > 100


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
