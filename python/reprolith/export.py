"""Writing a COMBINE archive: the reconstruction as a file another tool can run.

Reprolith *reads* a shipped archive (:func:`reprolith.ingest_omex`) and *builds* SBML from a
dossier (:func:`reprolith.build_model_sbml`). What it could not do was hand the result back in
the same standard form it accepts: a certificate travelled as Reprolith's own JSON, and the model
as a bare SBML string with the run conditions written down nowhere a simulator can read. Anyone
re-running a reproduction had to reconstruct "for how long, at what resolution, recording what"
from prose (spec: ``certificate-publication`` — standard, runnable artifacts).

This module closes that: :func:`build_experiment_sedml` writes the run as a SED-ML document, and
:func:`build_omex_archive` packages model and document as an OMEX archive with the manifest that
says what each file is. Both use only the standard library, and neither touches the filesystem —
the archive is returned as bytes for the caller to write where it wants.

**The exported document reports; it does not plot.** SED-ML has two ways to name the quantities a
run records: a ``plot``, and a ``report``. Reprolith reads a *paper's* plots as the paper's own
statement of which curves it published (:func:`reprolith.enumerate_sedml_claims`), and reads a
report as an export format — "write these columns" — that asserts nothing about what was
published. An exported reproduction is the second thing. It says how to run the model and which
variables to record; it does not know which of them a paper displayed, and emitting a plot would
make a document that, read back by Reprolith's own reader, manufactures one published result per
state variable. Which results a paper staked lives in the dossier's claims and the certificate,
which SED-ML has no vocabulary for. So: a report, and re-ingesting an exported archive yields
structure and no targetable claims — an honest silence, not an invented checklist.

Archives are written deterministically — fixed member order, fixed timestamps — so the same model
and run conditions produce byte-identical bytes, and an archive can be digested like any other
artifact this repository publishes.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from types import MappingProxyType

from .reconstruction import RecipeStep, ReconstructionBundle
from .sedml import sedml_model_sources

#: The COMBINE specifications namespace the manifest names each format by, as
#: :mod:`reprolith.omex` reads them back.
_COMBINE_SPECIFICATIONS = "http://identifiers.org/combine.specifications/"

#: The SED-ML dialect written here: L1V4, which is what BioModels ships and what the parser in
#: :mod:`reprolith.sedml` reads. The choice is load-bearing, not cosmetic — a uniform time course
#: says how finely to sample with ``numberOfSteps`` only from L1V4 onward (L1V3 spells it
#: ``numberOfPoints``), and the parser reads ``numberOfSteps``. Declaring L1V3 over a
#: ``numberOfSteps`` attribute writes a document that fails schema validation and whose sampling a
#: strict reader cannot see: libSEDML rejected exactly that before this was fixed.
_SEDML_NAMESPACE = "http://sed-ml.org/sed-ml/level1/version4"
_SEDML_LEVEL, _SEDML_VERSION = 1, 4

_MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"

#: SED-ML names the independent variable with this symbol; the report's first column is it.
_TIME_SYMBOL = "urn:sedml:symbol:time"

#: A deterministic ODE solver, so an exported run says which kind of solver it expects rather than
#: leaving it to the reader. KISAO:0000019 is CVODE — the algorithm Reprolith's own pinned engine
#: integrates with. It is a statement of the method, not a pin: the *pin* (engine and version) is
#: the certificate's, and a document cannot carry it.
_CVODE = "KISAO:0000019"

#: Zip entries are stamped with this fixed date so the same inputs give the same bytes. 1980-01-01
#: is the earliest a zip can represent.
_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

#: A SED-ML identifier: the SBML ``SId`` production, which SED-ML adopts.
_SID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


#: SBML packages that change what *running* the model means, mapped to what they make it. A model
#: declaring one of these is not run as a time course at all, so writing it a ``uniformTimeCourse``
#: would describe a run nobody performs — and the document would look perfectly valid doing it.
#: Packages that only annotate (``layout``, ``render``, ``distrib``, ``comp``) are not here: they
#: leave the run a time course.
_NOT_A_TIME_COURSE = {
    "fbc": "a constraint-based model, solved at steady state rather than integrated",
    "qual": "a qualitative (logical) model, advanced in discrete update steps",
    "spatial": "a spatially-resolved model, not a single well-mixed trajectory",
    "multi": "a multi-component species model, whose species are not the ones a course records",
}

#: The namespace an SBML Level 3 package declares, e.g.
#: ``http://www.sbml.org/sbml/level3/version1/fbc/version2``.
_PACKAGE_NAMESPACE = re.compile(
    r"^http://www\.sbml\.org/sbml/level\d+/version\d+/([a-z]+)/version\d+$"
)


def packages_no_time_course_describes(model_sbml: str) -> tuple[str, ...]:
    """The SBML packages this model declares that mean it is not run as a uniform time course.

    ``fbc``, ``qual``, ``spatial`` and ``multi``: a constraint-based model is solved at steady
    state, a logical one advances in discrete update steps. Empty for a model a time course does
    describe, including one carrying packages that only annotate (``layout``, ``comp``).

    Namespace *declarations* are not visible through ElementTree, so this reads the namespaces the
    document actually uses — on any element or attribute — which is what a package's presence
    amounts to in practice: an fbc model carries ``fbc:required`` on its root and an fbc objective
    inside its model. Raises ``ValueError`` if the text is not parseable XML.
    """
    return _packages_no_time_course_describes(_model_root(model_sbml))


def _packages_no_time_course_describes(root: ET.Element) -> tuple[str, ...]:
    used = {_namespace(root.tag)}
    for element in root.iter():
        used.add(_namespace(element.tag))
        used.update(_namespace(key) for key in element.attrib if key.startswith("{"))
    found = []
    for namespace in sorted(used):
        match = _PACKAGE_NAMESPACE.match(namespace)
        package = match.group(1) if match else ""
        if package in _NOT_A_TIME_COURSE and package not in found:
            found.append(package)
    return tuple(found)


def what_a_package_means(package: str) -> str:
    """How a model carrying this package is actually run, in a phrase."""
    return _NOT_A_TIME_COURSE[package]


def _refuse_a_model_no_time_course_describes(root: ET.Element) -> None:
    """Refuse a model whose SBML package means it is not run as a uniform time course."""
    for package in _packages_no_time_course_describes(root):
        raise ValueError(
            f"the model uses the SBML '{package}' package, so it is "
            f"{_NOT_A_TIME_COURSE[package]}; a uniform time course would describe a run "
            "nobody performs, and would look valid doing it"
        )


def _model_root(model_sbml: str) -> ET.Element:
    try:
        root = ET.fromstring(model_sbml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SBML: {exc}") from exc
    if _localname(root.tag) != "sbml":
        raise ValueError(
            f"not an SBML document: its root element is '{_localname(root.tag)}', not 'sbml'"
        )
    return root


def _elements_by_id(root: ET.Element) -> dict[str, tuple[str, str]]:
    """Each identified model element as ``id -> (containing list name, element name)``.

    Only the direct children of the model's ``listOf…`` containers are indexed, because that is
    what a SED-ML target addresses by nesting: ``/sbml:sbml/sbml:model/sbml:listOfSpecies/
    sbml:species[@id='S']``. An id deeper in the tree — a local parameter inside a reaction — is
    reachable only through the reaction that contains it and is not addressable by this shape.
    """
    model = next((c for c in root if _localname(c.tag) == "model"), None)
    if model is None:
        raise ValueError("the SBML document contains no model element")
    found: dict[str, tuple[str, str]] = {}
    for container in model:
        container_name = _localname(container.tag)
        if not container_name.startswith("listOf"):
            continue
        for element in container:
            element_id = element.get("id")
            if element_id and element_id not in found:
                found[element_id] = (container_name, _localname(element.tag))
    return found


def _species_ids(root: ET.Element) -> tuple[str, ...]:
    model = next((c for c in root if _localname(c.tag) == "model"), None)
    if model is None:
        return ()
    return tuple(
        element.get("id", "")
        for container in model
        if _localname(container.tag) == "listOfSpecies"
        for element in container
        if element.get("id")
    )


def _target(element_id: str, index: dict[str, tuple[str, str]]) -> str:
    container, element = index[element_id]
    return (
        f"/sbml:sbml/sbml:model/sbml:{container}/sbml:{element}[@id='{element_id}']"
    )


def build_experiment_sedml(
    model_sbml: str,
    *,
    duration: float,
    steps: int,
    model_location: str = "model.xml",
    observables: tuple[str, ...] | None = None,
) -> str:
    """Write the run of ``model_sbml`` as a SED-ML document: how long, how finely, recording what.

    ``duration`` and ``steps`` are the run verbatim — the same pair
    :func:`reprolith.parse_sedml_recipes` reads back out of a document and Reprolith's engines take
    as ``simulate(duration=…, steps=…)``. The time course starts at zero, because a document whose
    output starts later is one the recipe parser deliberately refuses to adopt, and exporting one
    would write a document Reprolith itself will not read.

    ``model_location`` is the model's path *as the document names it*, and a reader resolves it
    relative to the document — so a model stored at ``models/m.xml`` beside an experiment at
    ``experiments/e.sedml`` is ``../models/m.xml`` here. :func:`build_omex_archive` checks the two
    agree rather than shipping an archive whose experiment runs a file that is not in it. ``observables`` names the
    model elements to record; by default every species, in model order. Each named observable must
    be a top-level identified element of the model — a species, a parameter, a compartment — and
    one that is not is refused rather than written, because a document observing an element the
    model does not have plots a column that cannot exist (the same mismatch
    :func:`reprolith.archive_mismatches` reports when reading an archive).

    The observables become a ``report``, not a ``plot``, and the module docstring says why: this
    document records columns, it does not assert published results.

    Raises ``ValueError`` if the model is not parseable SBML, if the run is not a positive duration
    over a positive number of steps, or if an observable names nothing in the model.
    """
    if not (duration > 0):
        raise ValueError(f"a run needs a positive duration; got {duration}")
    if steps <= 0:
        raise ValueError(f"a run needs a positive number of steps; got {steps}")

    root = _model_root(model_sbml)
    _refuse_a_model_no_time_course_describes(root)
    index = _elements_by_id(root)
    recorded = _species_ids(root) if observables is None else tuple(observables)
    if not recorded:
        raise ValueError(
            "the model declares no species and no observables were named, so the document would "
            "record nothing but time"
        )
    unknown = [name for name in recorded if name not in index]
    if unknown:
        raise ValueError(
            "the model has no top-level element named: " + ", ".join(sorted(unknown))
            + ". A document observing an element the model does not have records a column that "
            "cannot exist."
        )
    unusable = [name for name in recorded if not _SID.match(name)]
    if unusable:
        # An SBML id is an SId already, so this can only fire on a hand-passed observable.
        raise ValueError(
            "not usable as a SED-ML identifier: " + ", ".join(sorted(unusable))
        )

    sbml_namespace = _namespace(root.tag)
    attributes = {
        "xmlns": _SEDML_NAMESPACE,
        "xmlns:sbml": sbml_namespace,
        "level": str(_SEDML_LEVEL),
        "version": str(_SEDML_VERSION),
    }
    document = ET.Element("sedML", attributes)

    models = ET.SubElement(document, "listOfModels")
    ET.SubElement(models, "model", {
        "id": "model", "language": _model_language(root), "source": model_location,
    })

    simulations = ET.SubElement(document, "listOfSimulations")
    course = ET.SubElement(simulations, "uniformTimeCourse", {
        "id": "simulation",
        "initialTime": "0",
        "outputStartTime": "0",
        "outputEndTime": repr(float(duration)),
        "numberOfSteps": str(int(steps)),
    })
    ET.SubElement(course, "algorithm", {"kisaoID": _CVODE})

    tasks = ET.SubElement(document, "listOfTasks")
    ET.SubElement(tasks, "task", {
        "id": "task", "modelReference": "model", "simulationReference": "simulation",
    })

    generators = ET.SubElement(document, "listOfDataGenerators")
    _add_generator(generators, generator_id="time_generator", variable_id="time", symbol=_TIME_SYMBOL)
    for name in recorded:
        _add_generator(
            generators,
            generator_id=f"{name}_generator",
            variable_id=name,
            target=_target(name, index),
        )

    outputs = ET.SubElement(document, "listOfOutputs")
    report = ET.SubElement(outputs, "report", {
        "id": "recorded", "name": "the columns this run records",
    })
    columns = ET.SubElement(report, "listOfDataSets")
    ET.SubElement(columns, "dataSet", {
        "id": "time_column", "label": "time", "dataReference": "time_generator",
    })
    for name in recorded:
        ET.SubElement(columns, "dataSet", {
            "id": f"{name}_column", "label": name, "dataReference": f"{name}_generator",
        })

    ET.indent(document, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        document, encoding="unicode"
    ) + "\n"


def _add_generator(
    parent: ET.Element,
    *,
    generator_id: str,
    variable_id: str,
    target: str | None = None,
    symbol: str | None = None,
    task: str = "task",
) -> None:
    """One data generator over one variable: the value itself, with no transformation applied."""
    generator = ET.SubElement(parent, "dataGenerator", {"id": generator_id, "name": variable_id})
    variables = ET.SubElement(generator, "listOfVariables")
    attributes = {"id": variable_id, "taskReference": task}
    if target is not None:
        attributes["target"] = target
    if symbol is not None:
        attributes["symbol"] = symbol
    ET.SubElement(variables, "variable", attributes)
    math = ET.SubElement(generator, "math", {"xmlns": _MATHML_NAMESPACE})
    ET.SubElement(math, "ci").text = f" {variable_id} "


def _model_language(root: ET.Element) -> str:
    """The SED-ML language URN for an SBML model, at the level and version it declares."""
    level, version = root.get("level"), root.get("version")
    if level and version:
        return f"urn:sedml:language:sbml.level-{level}.version-{version}"
    return "urn:sedml:language:sbml"


@dataclass(frozen=True)
class ExportedExperiment:
    """A SED-ML document written from a reconstruction recipe, and what it could not express."""

    sedml: str
    #: The claim ids that became a task in the document, in recipe order.
    expressed: tuple[str, ...]
    #: One line per recipe step the document could not state, naming the step and the reason —
    #: the same shape :func:`reprolith.archive_mismatches` reports a disagreement in. A step that
    #: cannot be written is listed here rather than dropped, because an archive silently short of
    #: a claim reads as a reconstruction that never had one.
    unexpressed: tuple[str, ...]


#: A recipe's ``time_span`` is a record of the window that was run, written as free text: the
#: committed bundles say ``0-24.0`` and the tests say ``0-24 h``. Only a window starting at zero is
#: expressible — a uniform time course that starts later is one this repository's own recipe parser
#: refuses to adopt — and the trailing unit, when there is one, is prose: the number is in the
#: model's own time unit, which is how the certified run used it.
_TIME_SPAN = re.compile(r"^\s*0(?:\.0*)?\s*-\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*[A-Za-z]*\s*$")

#: A recipe's ``output`` is written in the concentration notation the certificate prints,
#: ``[species]``. SED-ML addresses the species itself; whether a tool reads it as an amount or a
#: concentration is the tool's business, and the same is true of the engines this repository runs.
_BRACKETED = re.compile(r"^\[(.+)\]$")


def _output_id(output: str) -> str:
    match = _BRACKETED.match(output.strip())
    return (match.group(1) if match else output).strip()


def build_bundle_sedml(
    bundle: ReconstructionBundle,
    model_sbml: str,
    *,
    model_location: str = "model.xml",
) -> ExportedExperiment:
    """Write a published reconstruction's recipe as a SED-ML document.

    A :class:`reprolith.ReconstructionBundle` is Reprolith's own answer to "how do I re-run this":
    per claim, a window, a sample count, the output to read, and the parameter values that claim
    sets. All of that is expressible in SED-ML, and until it was, the one part that distinguishes
    two claims on one model — the **overrides** — lived only in Reprolith's JSON. In the published
    metformin bundle that is the 779.9 mg free-base dose, without which both claims run the 500 mg
    arm; writing it as a ``changeAttribute`` puts it in a file any simulator can act on.

    Each step becomes a task over the base model, or over a model derived from it by the step's
    overrides, and a ``report`` recording time and the step's output. Simulations are shared by
    window and sample count, so two claims run the same way name the same one. Identifiers are
    generated (``task1``, ``report1``), never built from the claim id — a claim id is free text and
    ``Cmax-500mg`` is not a valid SED-ML identifier — and each element carries the claim id it came
    from as its ``name``.

    A step the document cannot state is **listed, not dropped**: its reason goes in
    :attr:`ExportedExperiment.unexpressed`. That covers a step with no sample count, a window that
    is not a number starting at zero, an output the model does not have, and an override naming a
    parameter the model does not declare — which is the "override that overrides nothing" failure
    :func:`reprolith.archive_mismatches` exists to catch, and writing one would ship an archive
    that quietly runs the unmodified model.

    Not checked here: whether an override that *does* name a model parameter takes effect — one
    fixed by a rule, or shadowed by a kinetic law's own local parameter, is written as given. That
    check needs the model's math read, not its element names, and certification already applies it
    to every override before a bundle can carry one.

    Raises ``ValueError`` if the model is not parseable SBML, or if no step at all is expressible,
    since an experiment with no task describes no run.
    """
    root = _model_root(model_sbml)
    _refuse_a_model_no_time_course_describes(root)
    index = _elements_by_id(root)
    parameters = {name for name, (container, _) in index.items() if container == "listOfParameters"}

    document = ET.Element("sedML", {
        "xmlns": _SEDML_NAMESPACE,
        "xmlns:sbml": _namespace(root.tag),
        "level": str(_SEDML_LEVEL),
        "version": str(_SEDML_VERSION),
    })
    models = ET.SubElement(document, "listOfModels")
    ET.SubElement(models, "model", {
        "id": "model", "language": _model_language(root), "source": model_location,
    })
    simulations = ET.SubElement(document, "listOfSimulations")
    tasks = ET.SubElement(document, "listOfTasks")
    generators = ET.SubElement(document, "listOfDataGenerators")
    outputs = ET.SubElement(document, "listOfOutputs")

    expressed: list[str] = []
    unexpressed: list[str] = []
    known_runs: dict[tuple[float, int], str] = {}

    for step in bundle.recipe:
        plan, reason = _plan(step, index=index, parameters=parameters)
        if plan is None:
            unexpressed.append(f"claim '{step.claim_id}': {reason}")
            continue
        duration, count = plan.duration, plan.steps
        ordinal = len(expressed) + 1

        run = known_runs.get((duration, count))
        if run is None:
            run = f"simulation{len(known_runs) + 1}"
            known_runs[(duration, count)] = run
            course = ET.SubElement(simulations, "uniformTimeCourse", {
                "id": run,
                "initialTime": "0",
                "outputStartTime": "0",
                "outputEndTime": repr(duration),
                "numberOfSteps": str(count),
            })
            ET.SubElement(course, "algorithm", {"kisaoID": _CVODE})

        model_ref = "model"
        if step.parameter_overrides:
            model_ref = f"model{ordinal}"
            derived = ET.SubElement(models, "model", {
                "id": model_ref,
                "name": step.claim_id,
                "language": _model_language(root),
                "source": "#model",
            })
            changes = ET.SubElement(derived, "listOfChanges")
            for name, value in step.parameter_overrides:
                ET.SubElement(changes, "changeAttribute", {
                    "target": _target(name, index) + "/@value",
                    "newValue": repr(float(value)),
                })

        task = f"task{ordinal}"
        ET.SubElement(tasks, "task", {
            "id": task, "name": step.claim_id,
            "modelReference": model_ref, "simulationReference": run,
        })

        output_id = plan.output
        _add_generator(
            generators, generator_id=f"time{ordinal}", variable_id="time",
            symbol=_TIME_SYMBOL, task=task,
        )
        _add_generator(
            generators, generator_id=f"output{ordinal}", variable_id=output_id,
            target=_target(output_id, index), task=task,
        )
        report = ET.SubElement(outputs, "report", {
            "id": f"report{ordinal}",
            "name": f"{step.claim_id}: {step.protocol}" if step.protocol else step.claim_id,
        })
        columns = ET.SubElement(report, "listOfDataSets")
        ET.SubElement(columns, "dataSet", {
            "id": f"time{ordinal}_column", "label": "time", "dataReference": f"time{ordinal}",
        })
        ET.SubElement(columns, "dataSet", {
            "id": f"output{ordinal}_column", "label": output_id,
            "dataReference": f"output{ordinal}",
        })
        expressed.append(step.claim_id)

    if not expressed:
        raise ValueError(
            f"no recipe step of '{bundle.entry}' is expressible as a simulation experiment, so "
            "the document would describe no run: " + "; ".join(unexpressed or ["the recipe is empty"])
        )

    ET.indent(document, space="  ")
    sedml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        document, encoding="unicode"
    ) + "\n"
    return ExportedExperiment(
        sedml=sedml, expressed=tuple(expressed), unexpressed=tuple(unexpressed)
    )


@dataclass(frozen=True)
class _Runnable:
    """A recipe step reduced to what a uniform time course needs: how long, how finely, what."""

    duration: float
    steps: int
    output: str


def _plan(
    step: RecipeStep,
    *,
    index: dict[str, tuple[str, str]],
    parameters: set[str],
) -> tuple[_Runnable | None, str]:
    """This step as a runnable plan, or why it cannot be written. Exactly one of the two is set.

    The two answers come from one function on purpose: a version that only reported *whether* a
    step was expressible left the caller to re-derive the window and the output it had just
    validated, and a re-derivation that disagrees with its own check is how a step gets dropped
    with no reason recorded.
    """
    if step.schedule[:-1]:
        # A prior administration is a second run of the model started from where the first ended,
        # and a uniform time course cannot say that. Written as one anyway, the document would run
        # the reported window alone — a neighbouring arm that produces a plausible number and
        # flags nothing, which is the failure `archive_mismatches` and `manuscript_mismatches`
        # both exist to catch. Listed rather than dropped, and rather than guessed at.
        return None, (
            f"the claim runs after {len(step.schedule) - 1} prior administration(s) — the model "
            "restarted from the state each one ended in — and a uniform time course cannot state "
            "a run that begins from another run's end"
        )
    if step.steps is None or step.steps <= 0:
        return None, (
            f"the recipe states no sample count, so how finely to sample "
            f"'{step.time_span}' is not written down"
        )
    span = _TIME_SPAN.match(step.time_span)
    if span is None:
        return None, (
            f"the window '{step.time_span}' is not a numeric span starting at zero, and a "
            "uniform time course that starts later is not adoptable as (duration, steps)"
        )
    duration = float(span.group(1))
    if duration <= 0.0:
        return None, f"the window '{step.time_span}' does not advance, so there is nothing to run"
    output_id = _output_id(step.output)
    if output_id not in index:
        return None, f"the model has no top-level element '{output_id}' to record"
    missing = sorted(name for name, _ in step.parameter_overrides if name not in parameters)
    if missing:
        return None, (
            "the model declares no parameter named " + ", ".join(missing)
            + "; an override aimed at a parameter that is not there runs the unmodified model"
        )
    return _Runnable(duration=duration, steps=int(step.steps), output=output_id), ""


def _sbml_format(root: ET.Element) -> str:
    """The manifest format URI for an SBML document, at the level and version it declares."""
    level, version = root.get("level"), root.get("version")
    if level and version:
        return f"{_COMBINE_SPECIFICATIONS}sbml.level-{level}.version-{version}"
    return f"{_COMBINE_SPECIFICATIONS}sbml"


def build_omex_archive(
    model_sbml: str,
    experiment_sedml: str,
    *,
    model_location: str = "model.xml",
    experiment_location: str = "experiment.sedml",
    data_files: Mapping[str, str] = MappingProxyType({}),
) -> bytes:
    """Package a model and its experiment as a COMBINE archive, returned as bytes.

    The archive holds three files: the model as given, the SED-ML document as given — from
    :func:`build_experiment_sedml` for a plain run, or :func:`build_bundle_sedml` for a published
    reconstruction's recipe — and the ``manifest.xml`` that says what each one is. The experiment
    is marked ``master``, which is how an archive singles out the one simulation it describes;
    :func:`reprolith.ingest_omex` refuses an archive that does not.

    ``model_location`` must be the location the *document* names as its model source, since that is
    what a reader resolves. Nothing is written to disk. The bytes are deterministic: members are
    stored in a fixed order with a fixed timestamp, so the same model and experiment give the same
    archive every time, and two exports can be compared by digest.

    ``data_files`` are the data files the document's ``dataDescription`` elements name — the
    paper's own recorded values — keyed by the ``source`` the document writes and stored where
    that source resolves to, so a reader follows the same path it would in the author's own
    directory. They are listed in the manifest as ``text/csv``, the one data format the reader
    reads; a source that resolves outside the archive, or onto the model or the experiment, is
    refused for the same reason their own locations are.

    Raises ``ValueError`` if the model is not parseable SBML, or if the model and the experiment
    would be stored at the same location.
    """
    if model_location == experiment_location:
        raise ValueError(
            f"the model and the experiment cannot both be '{model_location}': "
            "an archive stores one file per location"
        )
    # A member name is written into the zip verbatim, so a location that climbs out of the archive
    # root — or one an extractor would resolve to a different name than the manifest lists — is
    # refused. Whoever unpacks it decides where `../x.xml` lands, and that is not a decision an
    # exported artifact gets to make on their machine.
    for role, location in (("model", model_location), ("experiment", experiment_location)):
        if not location or posixpath.normpath(location) != location or location.startswith(("/", "..")):
            raise ValueError(
                f"the {role} location {location!r} is not a plain relative path inside the "
                "archive; an archive member name is stored verbatim, and a path that climbs out "
                "of the root is unpacked wherever the extractor decides"
            )
    # The document's `source` is resolved relative to the document, and that is the only thing a
    # reader follows to find the model. A caller that moved the model without telling the writer
    # would ship an archive whose experiment runs a file the archive does not contain — which
    # `ingest_omex` refuses, so refusing it here names the mistake where it was made.
    base = posixpath.dirname(experiment_location)
    named = {
        posixpath.normpath(posixpath.join(base, source))
        for source in sedml_model_sources(experiment_sedml)
    }
    if named != {posixpath.normpath(model_location)}:
        raise ValueError(
            f"the experiment runs {sorted(named) or ['no model']}, but the archive stores the "
            f"model at '{model_location}'; the document's source is what a reader follows"
        )
    stored_data: dict[str, str] = {}
    for source, text in data_files.items():
        location = posixpath.normpath(posixpath.join(base, source))
        if not source or location != posixpath.normpath(location) or location.startswith(("/", "..")):
            raise ValueError(
                f"the data source {source!r} resolves to {location!r}, which is not a plain "
                "relative path inside the archive"
            )
        if location in (model_location, experiment_location):
            raise ValueError(
                f"the data source {source!r} resolves onto '{location}'; an archive stores one "
                "file per location"
            )
        stored_data[location] = text

    manifest = _manifest(
        model_location=model_location,
        model_format=_sbml_format(_model_root(model_sbml)),
        experiment_location=experiment_location,
        data_locations=tuple(sorted(stored_data)),
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in (
            ("manifest.xml", manifest),
            (model_location, model_sbml),
            (experiment_location, experiment_sedml),
            *sorted(stored_data.items()),
        ):
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, text)
    return buffer.getvalue()


def _manifest(
    *,
    model_location: str,
    model_format: str,
    experiment_location: str,
    data_locations: tuple[str, ...] = (),
) -> str:
    """The archive's manifest: the archive itself, the manifest, the model, and the experiment."""
    root = ET.Element("omexManifest", {"xmlns": f"{_COMBINE_SPECIFICATIONS}omex-manifest"})
    for location, format_uri, master in (
        (".", f"{_COMBINE_SPECIFICATIONS}omex", False),
        ("./manifest.xml", f"{_COMBINE_SPECIFICATIONS}omex-manifest", False),
        (f"./{model_location}", model_format, False),
        (
            f"./{experiment_location}",
            f"{_COMBINE_SPECIFICATIONS}sed-ml.level-{_SEDML_LEVEL}.version-{_SEDML_VERSION}",
            True,
        ),
        # A data file is named by media type, not by a COMBINE specification URI: the manifest
        # says what each file *is*, and a CSV of recorded values is not a specification.
        *((f"./{location}", "text/csv", False) for location in data_locations),
    ):
        attributes = {"location": location, "format": format_uri}
        if master:
            attributes["master"] = "true"
        ET.SubElement(root, "content", attributes)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


__all__ = [
    "ExportedExperiment",
    "build_bundle_sedml",
    "build_experiment_sedml",
    "build_omex_archive",
    "packages_no_time_course_describes",
    "what_a_package_means",
]
