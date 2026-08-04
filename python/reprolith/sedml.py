"""Reading a shipped SED-ML simulation recipe (catalog-backlog roadmap #4: adopt-and-verify fast-path).

When a paper ships a SED-ML document alongside its model, the *recipe* — which model to run, for how
long, at what resolution, and which species to observe — is already written down. Reading it turns
reproduction into "adopt the recipe and run" instead of hand-specifying the simulation, the highest
certificate yield per unit effort (spec: ``model-reconstruction`` — adopt-and-verify).

SED-ML is plain XML, so this parser uses only the standard library — the core stays dependency-free.
It extracts the uniform-time-course recipes: a :class:`SimulationRecipe` per task, with the model it
references, its duration and step count, and the species it observes. Non-uniform or repeated tasks
that carry no directly-runnable uniform time course are skipped rather than guessed at.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# A SED-ML variable targets a model element by an XPath ending in ``...[@id='X']`` — a species, but
# also an amount parameter, a compartment, etc. Pull out the leaf element's id.
_ELEMENT_ID = re.compile(r"\[@id=['\"]([^'\"]+)['\"]\]")


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
    amount parameters. A ``repeatedTask`` is resolved to the uniform-time-course subtask it wraps, so
    observables hung on the repeated task attach to the runnable recipe. A task whose simulation is
    not a uniform time course (a plain steady state) is skipped: there is no single runnable
    time-course recipe to adopt, and inventing one would be a guess. Raises ``ValueError`` if the
    text is not parseable SED-ML.
    """
    try:
        root = ET.fromstring(sedml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SED-ML: {exc}") from exc

    simulations: dict[str, tuple[float, int, float]] = {}
    observables: dict[str, list[str]] = {}
    tasks: list[tuple[str, str, str]] = []
    repeated: dict[str, str] = {}  # repeatedTask id -> the base task it wraps

    for element in root.iter():
        name = _localname(element.tag)
        if name == "uniformTimeCourse":
            sim_id = element.get("id")
            end_time, num_steps = element.get("outputEndTime"), element.get("numberOfSteps")
            if sim_id is not None and end_time is not None and num_steps is not None:
                simulations[sim_id] = (
                    float(end_time), int(num_steps), float(element.get("outputStartTime", "0")),
                )
        elif name == "variable":
            task_ref, target = element.get("taskReference"), element.get("target")
            if task_ref and target:
                ids = _ELEMENT_ID.findall(target)
                if ids:
                    observables.setdefault(task_ref, []).append(ids[-1])  # the leaf element
        elif name == "task":
            task_id, model_ref, sim_ref = (
                element.get("id"), element.get("modelReference"), element.get("simulationReference"),
            )
            if task_id and model_ref and sim_ref:
                tasks.append((task_id, model_ref, sim_ref))
        elif name == "repeatedTask":
            repeated_id = element.get("id")
            subtask = next((c for c in element.iter() if _localname(c.tag) == "subTask"), None)
            base_task = subtask.get("task") if subtask is not None else None
            if repeated_id and base_task:
                repeated[repeated_id] = base_task

    # Observables tagged on a repeatedTask belong to the base task it wraps.
    resolved: dict[str, list[str]] = {}
    for task_ref, ids in observables.items():
        resolved.setdefault(repeated.get(task_ref, task_ref), []).extend(ids)

    recipes: list[SimulationRecipe] = []
    for task_id, model_ref, sim_ref in tasks:
        if sim_ref not in simulations:
            continue  # not a uniform time course — nothing single-runnable to adopt
        duration, steps, output_start = simulations[sim_ref]
        species = tuple(dict.fromkeys(resolved.get(task_id, [])))  # unique, document order
        recipes.append(SimulationRecipe(
            task_id=task_id, model_ref=model_ref, duration=duration, steps=steps,
            observables=species, output_start=output_start,
        ))
    return recipes


__all__ = ["SimulationRecipe", "parse_sedml_recipes"]
