"""Writing the claims file the author-facing check needs, from the files the author has.

:func:`reprolith.archive_report` makes one check nothing in an archive can make on itself: does
the shipped experiment run *the result the paper reports*? It is the check that catches the
metformin archive scanning a dose the paper never claims, and it is the only one that needs an
input the files do not carry — a claims file, which the author writes by hand
(:doc:`docs/author-check`).

Nothing in the repository helped write one. That is the gap this closes: given the model, and the
simulation document if there is one, this emits the file with everything mechanically derivable
already filled in and the two things only the author knows left blank.

**It never invents a reported value.** ``reported`` comes out ``null`` and ``source_location``
empty, on every stub, always. A template that guessed a number from the model would hand the check
the model's own output as the paper's claim, and the comparison would pass by construction —
which is the exact failure the check exists to catch, moved one file upstream.

**The model alone yields no stubs.** A model states what *can* be read; it says nothing about what
the paper showed. Only the SED-ML document's **plots** are a statement that a curve is a displayed
result — the same line :func:`reprolith.enumerate_sedml_claims` draws — so stubs come from plots
and from nowhere else. Without a document the template still carries the two lists an author needs
to write stubs by hand: the outputs a claim can read, and the parameters a claim can set.

Three things are reported rather than guessed at:

``a curve plotting more than one model element``
    A normalized or summed trace is an expression; a claim reads one output. The stub is emitted
    with no output named and the elements listed.

``a curve plotting values the document ships``
    Those are the paper's own recorded points, not a result the model owes. Not a stub.

``a parameter the model's own math determines``
    An ``initialAssignment`` or ``assignmentRule`` makes the ``value`` attribute inert, and an
    override aimed at such a parameter is refused downstream. Those are listed apart from the
    parameters a claim can actually set, so a template never invites an override that cannot hold.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any

from .export import (
    _elements_by_id,
    _model_root,
    _packages_no_time_course_describes,
    what_a_package_means,
)
from .manuscript import _determined_by_math, _leaf
from .omex import _localname
from .sedml import _read_generators

#: What each ``listOf…`` container means for a claim that reads a time course. A species or a
#: parameter appears in the engine's time series and can be read; a compartment volume or a
#: reaction flux does not, so a curve plotting one is flagged rather than offered as a stub.
_READABLE_CONTAINERS = {"listOfSpecies": "species", "listOfParameters": "parameter"}

_FILL_IN = (
    "Delete the claims your paper does not report, then fill in 'reported' (the number your paper "
    "prints) and 'source_location' (where in the paper it is) on the ones that are left, and pass "
    "this file to: reprolith archive-check --claims. A stub left blank is refused rather than "
    "checked — a claim with no reported value has nothing to compare against."
)


def _element_kind(element_id: str, index: Mapping[str, tuple[str, str]]) -> str | None:
    """What the model declares this id as — ``species``, ``parameter``, or the element name."""
    entry = index.get(element_id)
    if entry is None:
        return None
    container, element = entry
    return _READABLE_CONTAINERS.get(container, element)


def _stub(claim_id: str, quantity: str, species: str) -> dict[str, Any]:
    """One claim record with the derivable fields filled and the author's two left blank."""
    return {
        "claim_id": claim_id,
        "quantity": quantity,
        "species": species,
        # Never a number. See the module docstring: a guessed reference is the check passing
        # against the model's own output.
        "reported": None,
        "source_location": "",
        # A plot is a trajectory and a claim is a scalar, so the metric cannot be read off the
        # document — this is the default the claims file uses, not something derived.
        "metric": "cmax",
        "parameter_overrides": {},
    }


def _plot_stubs(
    sedml_root: ET.Element, index: Mapping[str, tuple[str, str]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """One stub per plotted curve, and a note for every curve no stub could be written for."""
    generators = _read_generators(sedml_root)
    elements = {
        element.get("id", ""): element
        for element in sedml_root.iter()
        if _localname(element.tag) == "dataGenerator"
    }
    stubs: list[dict[str, Any]] = []
    notes: list[str] = []
    seen: set[str] = set()

    for output in sedml_root.iter():
        kind = _localname(output.tag)
        if kind not in ("plot2D", "plot3D"):
            continue
        plot_id = output.get("id") or kind
        marks = (c for c in output.iter() if _localname(c.tag) in ("curve", "surface"))
        for position, curve in enumerate(marks):
            ref = curve.get("zDataReference") or curve.get("yDataReference") or ""
            generator = generators.get(ref)
            if generator is None or generator.is_time:
                continue  # the axis, or a reference this document does not define
            curve_id = curve.get("id") or f"{plot_id}_{_localname(curve.tag)}{position}"
            if generator.data_sources:
                notes.append(
                    f"curve '{curve_id}' of plot '{plot_id}' plots values the document ships "
                    f"('{', '.join(generator.data_sources)}') — your own recorded points, not a "
                    "result the model owes, so it is not a claim"
                )
                continue
            targets = [
                _leaf(variable.get("target"))
                for variable in elements.get(ref, ET.Element("dataGenerator")).iter()
                if _localname(variable.tag) == "variable" and not variable.get("symbol")
            ]
            # The plot legend, then the generator's own name, then the bare symbol: a template
            # is filled in by a person, and the legend is the words their figure already uses.
            # :func:`reprolith.enumerate_sedml_claims` prefers the symbol because a dossier claim
            # is matched mechanically; here the reader is the author.
            quantity = curve.get("name") or generator.name or generator.quantity or curve_id
            claim_id = curve_id if curve_id not in seen else f"{curve_id}_{position}"
            seen.add(claim_id)
            resolved = [t for t in targets if t is not None]
            if len(targets) != 1 or not resolved:
                notes.append(
                    f"curve '{curve_id}' of plot '{plot_id}' plots an expression over "
                    f"{len(targets)} model element(s)"
                    + (f" ({', '.join(sorted(resolved))})" if resolved else "")
                    + " — a claim reads one output, so name it yourself"
                )
                stubs.append(_stub(claim_id, quantity, ""))
                continue
            element_id = resolved[0]
            declared = _element_kind(element_id, index)
            if declared is None:
                notes.append(
                    f"curve '{curve_id}' plots '{element_id}', which this model does not declare "
                    "as an addressable element — check the document names the model you gave"
                )
            elif declared not in _READABLE_CONTAINERS.values():
                notes.append(
                    f"curve '{curve_id}' plots '{element_id}', which the model declares as a "
                    f"{declared}; a time course reads species and parameters, so this one is "
                    "left for you to redirect"
                )
            # A stub the check cannot read is left with its output blank rather than carrying the
            # id anyway: a blank is what `unfilled_claims` reports, and an id that resolves to a
            # reaction would instead pass the template check and fail at read time, one step
            # further from the note that explains it.
            readable = declared in _READABLE_CONTAINERS.values()
            stubs.append(_stub(claim_id, quantity, element_id if readable else ""))
    return stubs, notes


def _readable_outputs(root: ET.Element) -> list[dict[str, str]]:
    """Every model element a claim's ``species`` field can name, with what the model calls it."""
    model = next((c for c in root if _localname(c.tag) == "model"), None)
    outputs: list[dict[str, str]] = []
    for container in model if model is not None else ():
        container_name = _localname(container.tag)
        if container_name not in _READABLE_CONTAINERS:
            continue
        for element in container:
            element_id = element.get("id")
            if not element_id:
                continue
            outputs.append({
                "id": element_id,
                "name": element.get("name") or "",
                "declared": _READABLE_CONTAINERS[container_name],
            })
    return sorted(outputs, key=lambda o: o["id"])


def _settable_parameters(root: ET.Element) -> tuple[list[dict[str, Any]], list[str]]:
    """``(parameters a claim can set, ids the model's own math determines)``.

    The second list is not a subset of the first, it is what was withheld from it. Offering an
    ``initialAssignment``-determined parameter as an override invites a value the model overwrites
    on its way in, which is refused downstream and would look like a claims-file error rather than
    what it is.
    """
    model = next((c for c in root if _localname(c.tag) == "model"), None)
    computed = _determined_by_math(root)
    settable: list[dict[str, Any]] = []
    withheld: list[str] = []
    for container in model if model is not None else ():
        if _localname(container.tag) != "listOfParameters":
            continue
        for element in container:
            element_id = element.get("id")
            if not element_id:
                continue
            if element_id in computed:
                withheld.append(element_id)
                continue
            settable.append({
                "id": element_id,
                "name": element.get("name") or "",
                "model_value": element.get("value"),
            })
    return sorted(settable, key=lambda p: p["id"]), sorted(withheld)


def claims_template(
    model_sbml: str, *, sedml: str | None = None, accession: str | None = None
) -> dict[str, Any]:
    """A claims file for this model, with everything derivable filled in and the rest blank.

    ``model_sbml`` is the model the paper ships; ``sedml`` its simulation document, when there is
    one — without it there are no claim stubs, only the two lists needed to write them, because a
    model states what can be read and never what was published. ``accession`` wraps the result in
    the ``entries`` shape ``datasets/pkpd_claims.json`` uses, which is what ``--accession`` reads.

    A model whose SBML package means it is not run as a uniform time course yields no stubs and
    says so: the claims file's ``metric`` and ``parameter_overrides`` describe a run nobody
    performs on such a model. Raises ``ValueError`` if either text is unparseable.
    """
    root = _model_root(model_sbml)
    index = _elements_by_id(root)
    withheld = [
        f"this model uses the SBML '{package}' package, so it is {what_a_package_means(package)}; "
        "a claims file describes a time-course result, so no claim was written for it"
        for package in _packages_no_time_course_describes(root)
    ]

    stubs: list[dict[str, Any]] = []
    notes: list[str] = []
    if sedml is not None and not withheld:
        try:
            sedml_root = ET.fromstring(sedml)
        except ET.ParseError as exc:
            raise ValueError(f"not parseable SED-ML: {exc}") from exc
        stubs, notes = _plot_stubs(sedml_root, index)
        if not stubs:
            notes.append(
                "this document plots nothing, so it states no displayed result — write your "
                "claims from the outputs listed below"
            )
    elif not withheld:
        notes.append(
            "no simulation document was given, so no claim was written: a model says what can be "
            "read, never what your paper showed. Write one stub per published number, or pass "
            "--sedml to start from the curves your document plots"
        )

    settable, model_determines = _settable_parameters(root)
    body: dict[str, Any] = {
        "description": _FILL_IN,
        "claims": stubs,
        "readable_outputs": _readable_outputs(root),
        "settable_parameters": settable,
        "model_determines": model_determines,
        "notes": notes,
    }
    if withheld:
        body["withheld"] = withheld
    if accession is not None:
        return {"description": _FILL_IN, "entries": {accession: body}}
    return body


def unfilled_claims(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Which claim records are still carrying a template's blanks, named one per line.

    A template passed to the check unfilled is the ordinary mistake, and it used to surface as a
    ``TypeError`` on ``float(None)`` from inside the loader. Each blank is named with the claim it
    is on, so the message says which line to go and write.
    """
    unfilled: list[str] = []
    for position, record in enumerate(records):
        claim_id = str(record.get("claim_id") or f"claim {position + 1}")
        if record.get("reported") is None:
            unfilled.append(f"{claim_id}: 'reported' is blank — the number your paper prints")
        if not str(record.get("source_location") or "").strip():
            unfilled.append(
                f"{claim_id}: 'source_location' is blank — where in the paper the number is"
            )
        if not str(record.get("species") or "").strip():
            unfilled.append(
                f"{claim_id}: 'species' is blank — the model output the number is read from"
            )
    return tuple(unfilled)


__all__ = ["claims_template", "unfilled_claims"]
