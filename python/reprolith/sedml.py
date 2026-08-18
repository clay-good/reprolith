"""Reading a shipped SED-ML simulation recipe (catalog-backlog roadmap #4: adopt-and-verify fast-path).

When a paper ships a SED-ML document alongside its model, the *recipe* — which model to run, for how
long, at what resolution, and which species to observe — is already written down. Reading it turns
reproduction into "adopt the recipe and run" instead of hand-specifying the simulation, the highest
certificate yield per unit effort (spec: ``model-reconstruction`` — adopt-and-verify).

SED-ML is plain XML, so this parser uses only the standard library — the core stays dependency-free.
It extracts the uniform-time-course recipes: a :class:`SimulationRecipe` per task, with the model it
references, its duration and step count, and the species it observes. Anything the recipe cannot
state faithfully — a task over a model the document modifies, or a parameter scan — is skipped
rather than guessed at, because a recipe that silently drops a modification describes a different
run from the one the document specifies.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# A SED-ML variable targets a model element by an XPath whose LAST step selects the element, as in
# ``.../species[@id='S1']``. Match that final step only: an ancestor step can carry an ``@id`` too
# (``compartment[@id='cyt']/listOfSpecies/species[@name='S1']``), and taking the last ``@id``
# anywhere in the path would report the compartment as the observed quantity.
_LEAF_ID = re.compile(r"/[^/\[]+\[@id=['\"]([^'\"]+)['\"]\]\s*$")


@dataclass(frozen=True)
class SimulationRecipe:
    """A runnable simulation recipe read from a SED-ML task: what to run and what to observe."""

    task_id: str
    model_ref: str
    duration: float
    steps: int
    observables: tuple[str, ...]
    output_start: float = 0.0


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_sedml_recipes(sedml: str) -> list[SimulationRecipe]:
    """Extract the uniform-time-course simulation recipes from a SED-ML document.

    Returns one :class:`SimulationRecipe` per task that resolves to a ``uniformTimeCourse``
    simulation, in document order. Observables are the model elements the SED-ML plots — species or
    amount parameters — read from the data generators.

    Three kinds of task are skipped rather than turned into a recipe that misdescribes them, because
    a recipe is adopted and run verbatim:

    * a task whose simulation is not a uniform time course (a plain steady state), which has no
      single runnable time course to adopt;
    * a task over a model the document *modifies* (``source="#other"`` with ``listOfChanges``) —
      the recipe names one model file, so adopting it would run the unmodified model while the
      document's own figure depends on the overrides;
    * a ``repeatedTask`` that scans a range or applies a ``setValue`` — the document describes
      several runs at several parameter values, and folding them into one run at the model's
      default value reproduces an arm the document never plotted;
    * a time course whose ``initialTime`` or ``outputStartTime`` is not zero. ``numberOfSteps``
      spans ``[outputStartTime, outputEndTime]``, not ``[0, outputEndTime]``, and a recipe is
      adopted and run verbatim as ``simulate(duration=recipe.duration, steps=recipe.steps)`` —
      so pairing the document's step count with its end time silently changed the sampling
      interval. Measured on a document sampling ``t = 40…60`` in 20 intervals: the recipe said
      dt = 3.0 where the document said dt = 1.0, and a model reproducing its reference *exactly*
      linted `failed` at a normalized distance of 4.07. ``initialTime`` was never read at all.
      Neither is expressible in one ``(duration, steps)`` pair, so the task is skipped rather than
      described wrongly.

    A ``repeatedTask`` that merely wraps a subtask without changing anything still resolves to that
    subtask, so its observables attach to the runnable recipe. Raises ``ValueError`` if the text is
    not parseable SED-ML.
    """
    try:
        root = ET.fromstring(sedml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SED-ML: {exc}") from exc

    simulations: dict[str, tuple[float, int, float]] = {}
    observables: dict[str, list[str]] = {}
    tasks: list[tuple[str, str, str]] = []
    repeated: dict[str, str] = {}  # repeatedTask id -> the base task it wraps, if it changes nothing
    modified_models: set[str] = set()  # models the document defines by overriding another

    derived_from: dict[str, str | None] = {}
    for element in root.iter():
        name = _localname(element.tag)
        if name == "uniformTimeCourse":
            sim_id = element.get("id")
            end_time, num_steps = element.get("outputEndTime"), element.get("numberOfSteps")
            initial_time = float(element.get("initialTime", "0"))
            output_start = float(element.get("outputStartTime", "0"))
            if initial_time != 0.0 or output_start != 0.0:
                continue  # not runnable verbatim as (duration, steps); see the docstring
            if sim_id is not None and end_time is not None and num_steps is not None:
                simulations[sim_id] = (float(end_time), int(num_steps), output_start)
        elif name == "model":
            model_id = element.get("id")
            source = element.get("source", "")
            changes = any(_localname(c.tag) == "listOfChanges" and len(c) for c in element)
            if model_id and changes:
                modified_models.add(model_id)
            if model_id:
                # A model deriving from another (source="#other") inherits that model's changes,
                # so a change one link up is still a change to what this task runs. Recorded here
                # and resolved after the whole document is read, because a derived model may be
                # declared before the one it derives from.
                derived_from[model_id] = source[1:] if source.startswith("#") else None
        elif name == "dataGenerator":
            # Only a data generator's variables are plotted quantities. Scanning every `variable`
            # in the document would also pick up the ones inside a setValue or computeChange, which
            # are inputs to a modification, not outputs — and they would sort ahead of the real
            # observables, so a consumer reading observables[0] would get the wrong quantity.
            for variable in element.iter():
                if _localname(variable.tag) != "variable":
                    continue
                task_ref, target = variable.get("taskReference"), variable.get("target")
                if not task_ref or not target:
                    continue
                leaf = _LEAF_ID.search(target)
                if leaf:
                    observables.setdefault(task_ref, []).append(leaf.group(1))
        elif name == "task":
            task_id, model_ref, sim_ref = (
                element.get("id"), element.get("modelReference"), element.get("simulationReference"),
            )
            if task_id and model_ref and sim_ref:
                tasks.append((task_id, model_ref, sim_ref))
        elif name == "repeatedTask":
            repeated_id = element.get("id")
            subtasks = [c for c in element.iter() if _localname(c.tag) == "subTask"]
            scans = any(
                _localname(c.tag) in ("listOfRanges", "listOfChanges") and len(c) for c in element
            )
            # One plain subtask and nothing varied is a wrapper; anything else is several runs, or
            # runs at values this parser does not carry, so it resolves to no runnable recipe.
            if repeated_id and len(subtasks) == 1 and not scans:
                base_task = subtasks[0].get("task")
                if base_task:
                    repeated[repeated_id] = base_task

    # Observables tagged on a pass-through repeatedTask belong to the base task it wraps. Those
    # tagged on a scanning repeatedTask stay with it, so they never migrate onto a single run.
    resolved: dict[str, list[str]] = {}
    for task_ref, ids in observables.items():
        resolved.setdefault(repeated.get(task_ref, task_ref), []).extend(ids)

    def carries_overrides(model_id: str) -> bool:
        """True when this model, or any model it derives from, is defined by overriding another."""
        seen: set[str] = set()
        current: str | None = model_id
        while current is not None and current not in seen:
            if current in modified_models:
                return True
            seen.add(current)
            current = derived_from.get(current)
        return False

    recipes: list[SimulationRecipe] = []
    for task_id, model_ref, sim_ref in tasks:
        if sim_ref not in simulations:
            continue  # not a uniform time course — nothing single-runnable to adopt
        if carries_overrides(model_ref):
            continue  # the recipe cannot name the overrides, so it cannot describe this run
        duration, steps, output_start = simulations[sim_ref]
        species = tuple(dict.fromkeys(resolved.get(task_id, [])))  # unique, document order
        recipes.append(SimulationRecipe(
            task_id=task_id, model_ref=model_ref, duration=duration, steps=steps,
            observables=species, output_start=output_start,
        ))
    return recipes


__all__ = ["SimulationRecipe", "parse_sedml_recipes"]
