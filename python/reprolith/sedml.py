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

from .dossier import DossierClaim
from .oracle import ReferenceKind

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
      A recipe could in principle carry the offset (``output_start`` exists for it), but nothing
      consumes it — the repo's own adopt-and-verify test runs ``(duration, steps)`` verbatim — so
      the task is skipped rather than described in a field every reader ignores.

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
            try:
                initial_time = float(element.get("initialTime", "0"))
                output_start = float(element.get("outputStartTime", "0"))
            except ValueError as unreadable:
                raise ValueError(f"not parseable SED-ML: {unreadable}") from unreadable
            if initial_time != 0.0 or output_start != 0.0:
                continue  # not runnable verbatim as (duration, steps); see the docstring
            if sim_id is not None and end_time is not None and num_steps is not None:
                # Converted below the skip, not above it: hoisting these to share one try meant a
                # simulation this parser deliberately drops was parsed anyway, so one unreadable
                # attribute on a task nobody adopts failed the whole document. Same contract —
                # one error type for an unreadable document — applied where the value is used.
                try:
                    simulations[sim_id] = (float(end_time), int(num_steps), output_start)
                except ValueError as unreadable:
                    raise ValueError(f"not parseable SED-ML: {unreadable}") from unreadable
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


#: SED-ML names the independent variable with this symbol. A data generator built only from it
#: is the plot's axis, not a quantity the document asserts anything about — ``time`` and
#: ``time/60`` are the same axis in different units, and neither is a claim.
_TIME_SYMBOL = "urn:sedml:symbol:time"


@dataclass(frozen=True)
class _Generator:
    """What a SED-ML data generator observes: its label, its task, and whether it is the axis."""

    name: str
    quantity: str
    task_ref: str
    is_time: bool


def _read_generators(root: ET.Element) -> dict[str, _Generator]:
    generators: dict[str, _Generator] = {}
    for element in root.iter():
        if _localname(element.tag) != "dataGenerator":
            continue
        gen_id = element.get("id")
        if not gen_id:
            continue
        quantity, task_ref, symbols, targets = "", "", 0, 0
        for variable in element.iter():
            if _localname(variable.tag) != "variable":
                continue
            task_ref = task_ref or (variable.get("taskReference") or "")
            target = variable.get("target")
            if variable.get("symbol") == _TIME_SYMBOL:
                symbols += 1
            if target:
                targets += 1
                leaf = _LEAF_ID.search(target)
                quantity = quantity or (leaf.group(1) if leaf else target)
        name = element.get("name") or gen_id
        generators[gen_id] = _Generator(
            name=name,
            quantity=quantity or name,
            task_ref=task_ref,
            # Only a generator built from nothing but the time symbol is the axis. One that mixes
            # time with a species (a normalized trace) still asserts something about the species.
            is_time=symbols > 0 and targets == 0,
        )
    return generators


def _read_tasks(root: ET.Element) -> dict[str, tuple[str, str]]:
    tasks: dict[str, tuple[str, str]] = {}
    for element in root.iter():
        if _localname(element.tag) != "task":
            continue
        task_id = element.get("id")
        if task_id:
            tasks[task_id] = (
                element.get("modelReference") or "", element.get("simulationReference") or ""
            )
    return tasks


def _conditions(generator: _Generator, tasks: dict[str, tuple[str, str]]) -> str:
    """The run a claim holds under, named as precisely as the document allows.

    The task is what pins the conditions: it names the model — including a model the document
    defines by overriding another, which is how one document plots two different parameter sets —
    and the simulation. Naming the model matters for exactly that case: Figure 2B of the shipped
    Kholodenko document is the *modified* model, and a claim that said only "task_fig2b" would
    hide that the two figures are not the same model.
    """
    if not generator.task_ref:
        return ""
    model_ref, sim_ref = tasks.get(generator.task_ref, ("", ""))
    if not model_ref and not sim_ref:
        return f"task '{generator.task_ref}'"
    return f"task '{generator.task_ref}', model '{model_ref}', simulation '{sim_ref}'"


def enumerate_sedml_claims(sedml: str) -> tuple[DossierClaim, ...]:
    """Enumerate the published results a SED-ML document stakes, as dossier claims.

    A SED-ML document's **plots** are the document's own statement of which curves are shown
    results, so each ``curve`` (and each ``surface`` of a ``plot3D``) becomes one targetable
    claim: the quantity it plots, the task it holds under, and the plot and curve it came from
    as its source location. This is the artifact-declared path to claims, distinct from reading
    them out of manuscript prose, which is not built (see ``docs/findings-note.md``).

    Two things are deliberately *not* claims:

    * **The time axis.** A data generator built only from ``urn:sedml:symbol:time`` is what the
      curve is plotted against, not something the document asserts.
    * **A report's data sets.** A ``report`` is an export format — "write these columns" — not a
      statement that the paper published the value. In the SED-ML BioModels ships for the
      Kholodenko model, one report restates a plot verbatim and another dumps every symbol in the
      model, reaction fluxes and compartment volume included. Reading those as claims would
      manufacture seventeen results the paper never staked. A report data set that no curve plots
      is therefore retained with ``targetable`` false rather than dropped, so a reviewer can
      promote it as a tracked revision; one that a curve *does* plot is the claim already
      enumerated from that curve, and is not repeated.

    A document that ships only reports therefore yields no targetable claims. That is an
    abstention, not a wrong answer: nothing in it says which of its columns the paper published.

    Every claim is marked ``digitized-figure`` with no reference data, because a SED-ML document
    says what to plot, never what values the paper's figure showed. The oracle abstains on a
    claim with no reference rather than inventing one. Reference values shipped through a
    ``dataDescription`` are not read yet, so a document carrying real experimental data is
    currently marked figure-referenced like any other.

    Raises ``ValueError`` if the text is not parseable SED-ML.
    """
    try:
        root = ET.fromstring(sedml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SED-ML: {exc}") from exc

    generators = _read_generators(root)
    tasks = _read_tasks(root)
    claims: list[DossierClaim] = []
    plotted: set[str] = set()

    for output in root.iter():
        kind = _localname(output.tag)
        if kind not in ("plot2D", "plot3D"):
            continue
        plot_id = output.get("id") or kind
        plot_name = output.get("name")
        where = f"SED-ML {kind} '{plot_id}'" + (f" ({plot_name})" if plot_name else "")
        marks = (c for c in output.iter() if _localname(c.tag) in ("curve", "surface"))
        for index, curve in enumerate(marks):
            # The dependent quantity is z on a surface and y on a curve; x is the axis.
            ref = curve.get("zDataReference") or curve.get("yDataReference")
            generator = generators.get(ref or "")
            if generator is None or generator.is_time:
                continue
            plotted.add(ref or "")
            curve_id = curve.get("id") or f"{plot_id}_{_localname(curve.tag)}{index}"
            claims.append(DossierClaim(
                id=curve_id,
                quantity=curve.get("name") or generator.quantity,
                conditions=_conditions(generator, tasks),
                source_location=f"{where}, {_localname(curve.tag)} '{curve_id}'",
                reference_kind=ReferenceKind.DIGITIZED_FIGURE,
            ))

    for output in root.iter():
        if _localname(output.tag) != "report":
            continue
        report_id = output.get("id") or "report"
        report_name = output.get("name")
        where = f"SED-ML report '{report_id}'" + (f" ({report_name})" if report_name else "")
        columns = (d for d in output.iter() if _localname(d.tag) == "dataSet")
        for index, data_set in enumerate(columns):
            ref = data_set.get("dataReference") or ""
            generator = generators.get(ref)
            if generator is None or generator.is_time or ref in plotted:
                continue
            set_id = data_set.get("id") or f"{report_id}_dataSet{index}"
            claims.append(DossierClaim(
                id=set_id,
                quantity=data_set.get("label") or generator.quantity,
                conditions=_conditions(generator, tasks),
                source_location=f"{where}, dataSet '{set_id}'",
                targetable=False,
            ))

    return tuple(claims)


__all__ = ["SimulationRecipe", "enumerate_sedml_claims", "parse_sedml_recipes"]
