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

import re
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

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

    ``model_location`` is the model's path *as the archive stores it*, which is what the document's
    ``source`` must name for :func:`reprolith.ingest_omex` to find it. ``observables`` names the
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
) -> None:
    """One data generator over one variable: the value itself, with no transformation applied."""
    generator = ET.SubElement(parent, "dataGenerator", {"id": generator_id, "name": variable_id})
    variables = ET.SubElement(generator, "listOfVariables")
    attributes = {"id": variable_id, "taskReference": "task"}
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


def _sbml_format(root: ET.Element) -> str:
    """The manifest format URI for an SBML document, at the level and version it declares."""
    level, version = root.get("level"), root.get("version")
    if level and version:
        return f"{_COMBINE_SPECIFICATIONS}sbml.level-{level}.version-{version}"
    return f"{_COMBINE_SPECIFICATIONS}sbml"


def build_omex_archive(
    model_sbml: str,
    *,
    duration: float,
    steps: int,
    model_location: str = "model.xml",
    experiment_location: str = "experiment.sedml",
    observables: tuple[str, ...] | None = None,
) -> bytes:
    """Package a model and its run as a COMBINE archive, returned as bytes.

    The archive holds three files: the model as given, the SED-ML
    :func:`build_experiment_sedml` writes for it, and the ``manifest.xml`` that says what each one
    is. The experiment is marked ``master``, which is how an archive singles out the one simulation
    it describes — :func:`reprolith.ingest_omex` refuses an archive that does not.

    Nothing is written to disk. The bytes are deterministic: members are stored in a fixed order
    with a fixed timestamp, so the same model and run conditions give the same archive every time,
    and two exports can be compared by digest.

    Raises ``ValueError`` for anything :func:`build_experiment_sedml` refuses, and if the model and
    the experiment would be stored at the same location.
    """
    if model_location == experiment_location:
        raise ValueError(
            f"the model and the experiment cannot both be '{model_location}': "
            "an archive stores one file per location"
        )
    sedml = build_experiment_sedml(
        model_sbml,
        duration=duration,
        steps=steps,
        model_location=model_location,
        observables=observables,
    )
    manifest = _manifest(
        model_location=model_location,
        model_format=_sbml_format(_model_root(model_sbml)),
        experiment_location=experiment_location,
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in (
            ("manifest.xml", manifest),
            (model_location, model_sbml),
            (experiment_location, sedml),
        ):
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, text)
    return buffer.getvalue()


def _manifest(*, model_location: str, model_format: str, experiment_location: str) -> str:
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
    ):
        attributes = {"location": location, "format": format_uri}
        if master:
            attributes["master"] = "true"
        ET.SubElement(root, "content", attributes)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


__all__ = ["build_experiment_sedml", "build_omex_archive"]
