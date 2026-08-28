"""Comparing a shipped archive against the manuscript (catalog-backlog roadmap #4).

:func:`reprolith.archive_mismatches` asks whether the two files an archive ships agree with each
other. This module asks the other question, the one roadmap item 4 leaves open: does the
executable experiment run *the result the paper reports*?

The two can disagree without either file being malformed. The metformin archive is the case that
motivated this: the paper reports a peak plasma concentration after a 1000 mg oral dose, which is
779.9 mg of free base in the model's own units, and the shipped SED-ML scans the dose over
389.2, 778.4 and 1167.6 mg. Every file is valid, the experiment runs, and nothing in it produces
the arm the manuscript reports. A reproducer who adopts the document verbatim reproduces a
neighbouring number and calls it a match.

The manuscript side is a :class:`reprolith.Claim` — the extracted published result, the model
output it reads, and the parameter values it holds at. The archive side is the SED-ML document and
the model it runs. Only what both sides state mechanically is compared; everything else is left
unreported rather than guessed at, because a false accusation against a correct archive costs more
than a missed one (the same rule :func:`reprolith.archive_mismatches` follows for a target it
cannot resolve).

Deliberately **not** compared:

``the run window``
    A claim records its window in the manuscript's units (24 hours); a uniform time course records
    a number and no unit at all. Reading ``outputEndTime="30"`` as 30 hours is an assumption, and
    at the wrong one every archive in existence is a mismatch.

``a quantity the document records that no claim covers``
    A document routinely reports more columns than the paper displays, and Reprolith's own claim
    extraction is known to be partial. Reporting the difference would accuse the archive of what
    is usually a gap in the extraction.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from .certify import Claim
from .omex import _localname
from .sedml import _LEAF_ID


def _number(text: str | None) -> float | None:
    try:
        return float((text or "").strip())
    except ValueError:
        return None


#: The attributes a change writes a *value* into. A change to any other attribute (a name, a
#: `constant` flag) leaves the element's value where it was, so it says nothing about which arm
#: the experiment runs.
_VALUE_ATTRIBUTES = frozenset({"value", "initialConcentration", "initialAmount", "size"})


def _split_attribute(target: str | None) -> tuple[str, str | None]:
    """A target split into the element path and the attribute it selects, if any."""
    path, _, attribute = (target or "").partition("/@")
    return path, attribute or None


def _leaf(target: str | None) -> str | None:
    """The id of the element a target selects, ignoring any attribute it then reads."""
    path, _ = _split_attribute(target)
    match = _LEAF_ID.search(path)
    return match.group(1) if match else None


def _determined_by_math(root: ET.Element) -> set[str]:
    """Ids whose value the model computes, so their ``value`` attribute states nothing.

    SBML makes the attribute inert for a parameter an assignment rule or an initial assignment
    sets — the metformin model carries thirty-two initial assignments — and reading it as "what
    the model runs" is the shape of defect this module exists to catch, one level down: a number
    that is there, is not a check, and can silence a real disagreement by coincidence.
    """
    determined: set[str] = set()
    for element in root.iter():
        tag = _localname(element.tag)
        if tag == "initialAssignment" and element.get("symbol"):
            determined.add(element.get("symbol", ""))
        elif tag == "assignmentRule" and element.get("variable"):
            determined.add(element.get("variable", ""))
    return determined


def _model_index(root: ET.Element) -> tuple[dict[str, int], dict[str, float]]:
    """``(id -> how many elements carry it, id -> its stated value)``.

    The count matters: a manuscript record names an element by a bare id, and SBML lets a kinetic
    law's local parameter reuse a global name. When an id is carried by more than one element
    there is no way to tell which the manuscript meant, so its value is not offered for comparison.
    An id the model's own math determines is left out for the same reason: it has no stated value.
    """
    counts: dict[str, int] = {}
    values: dict[str, float] = {}
    for element in root.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        counts[element_id] = counts.get(element_id, 0) + 1
        value = _number(element.get("value"))
        if value is not None:
            values[element_id] = value
    computed = _determined_by_math(root)
    return counts, {
        name: value
        for name, value in values.items()
        if counts[name] == 1 and name not in computed
    }


def _observed(sedml_root: ET.Element) -> tuple[set[str], bool]:
    """The model elements the experiment records, and whether every one of them could be read.

    A variable is an observation only inside a data generator: one inside a ``setValue`` is an
    input to a modification, the same distinction :func:`reprolith.enumerate_sedml_claims` draws.
    The flag is false when any observation target has no readable element id — absence cannot be
    established from a document whose targets this cannot read.
    """
    observed: set[str] = set()
    readable = True
    for generator in sedml_root.iter():
        if _localname(generator.tag) != "dataGenerator":
            continue
        for variable in generator.iter():
            if _localname(variable.tag) != "variable" or variable.get("symbol"):
                continue  # a symbol is the time axis, not a model element
            leaf = _leaf(variable.get("target"))
            if leaf is None:
                readable = False
            else:
                observed.add(leaf)
    return observed, readable


def _ranges(sedml_root: ET.Element) -> dict[str, tuple[float, ...] | None]:
    """Each range's values, or ``None`` for a range whose values this does not read."""
    ranges: dict[str, tuple[float, ...] | None] = {}
    for element in sedml_root.iter():
        kind = _localname(element.tag)
        if not kind.endswith("Range"):
            continue
        range_id = element.get("id")
        if not range_id:
            continue
        if kind != "vectorRange":
            # A uniform or functional range is a run this does not enumerate. Recorded as
            # unreadable so a claim's value is never called absent from a set never computed.
            ranges[range_id] = None
            continue
        values = [_number(child.text) for child in element if _localname(child.tag) == "value"]
        ranges[range_id] = None if any(v is None for v in values) else tuple(v for v in values if v is not None)
    return ranges


def _scanned_values(element: ET.Element, ranges: dict[str, tuple[float, ...] | None]) -> tuple[float, ...] | None:
    """The values a ``setValue`` takes, or ``None`` when they are not readable.

    Only the two forms that state their values are read: the whole of a range (``<ci>range0</ci>``),
    and a literal number. A ``setValue`` computing an expression *of* a range takes values this
    would have to evaluate, and guessing them is how a correct archive gets accused.
    """
    maths = [child for child in element if _localname(child.tag) == "math"]
    if len(maths) != 1:
        return None
    terms = list(maths[0])
    if len(terms) != 1:
        return None
    term, text = terms[0], (terms[0].text or "").strip()
    if _localname(term.tag) == "cn":
        value = _number(text)
        return None if value is None else (value,)
    if _localname(term.tag) == "ci" and text == (element.get("range") or ""):
        return ranges.get(text)
    return None


def _values_run_for(sedml_root: ET.Element, parameter: str) -> tuple[float, ...] | None:
    """Every value the experiment sets ``parameter`` to, or ``None`` when one is unreadable."""
    ranges = _ranges(sedml_root)
    values: list[float] = []
    for element in sedml_root.iter():
        kind = _localname(element.tag)
        if kind not in ("changeAttribute", "setValue", "computeChange", "changeXML", "removeXML"):
            continue
        if _leaf(element.get("target")) != parameter:
            continue
        if kind == "changeAttribute":
            _, attribute = _split_attribute(element.get("target"))
            if attribute is not None and attribute not in _VALUE_ATTRIBUTES:
                continue  # it changes something other than the value this claim holds at
            value = _number(element.get("newValue"))
            if value is None:
                return None
            values.append(value)
        elif kind == "setValue":
            scanned = _scanned_values(element, ranges)
            if scanned is None:
                return None
            values.extend(scanned)
        else:
            return None  # a change whose effect on the value this does not compute
    return tuple(values)


def _format(values: Sequence[float]) -> str:
    return ", ".join(f"{value:g}" for value in values)


def manuscript_mismatches(
    sedml: str, sbml: str, claims: Sequence[Claim], *, rel_tol: float = 1e-9
) -> list[str]:
    """Report where a shipped archive does not run what the manuscript's claims report.

    ``claims`` are the manuscript-extracted claims for the same paper (spec: ``paper-ingestion``).
    Returns one line per disagreement, empty when the archive and the manuscript agree — the same
    shape :func:`reprolith.archive_mismatches` and :func:`reprolith.compare_sbml_to_dossier` use.
    Three things are checked, all of them mechanical:

    * the output a claim reads is not an element of the model the archive ships;
    * that element is in the model, but the experiment never records it, so running the document
      produces no column the claim could be read from;
    * the parameter values the claim holds at are not among the values the experiment runs — the
      model's own stated value, a ``changeAttribute``, and a scan whose values the document lists.

    A comparison that cannot be made is not made: an id carried by more than one model element, a
    target with no readable element id, a range this does not enumerate, and a change whose effect
    it does not compute all suppress the check that would have used them, because failing to read
    a document is not evidence that it disagrees. See the module docstring for what is out of
    scope by design (the run window, and outputs no claim covers).

    Raises ``ValueError`` if either document is not parseable XML.
    """
    try:
        sedml_root = ET.fromstring(sedml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SED-ML: {exc}") from exc
    try:
        model_root = ET.fromstring(sbml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SBML: {exc}") from exc

    counts, stated = _model_index(model_root)
    computed = _determined_by_math(model_root)
    observed, observations_readable = _observed(sedml_root)

    problems: list[str] = []
    for claim in claims:
        where = f"the manuscript's claim {claim.claim_id!r}"
        if claim.species not in counts:
            problems.append(
                f"{where} reads {claim.species!r}, which the archive's model does not declare"
            )
        elif observations_readable and claim.species not in observed:
            problems.append(
                f"{where} reads {claim.species!r}, which the archive's experiment never records"
            )
        for parameter, value in claim.parameter_overrides:
            if parameter not in counts:
                problems.append(
                    f"{where} sets {parameter!r} to {value:g}, and the archive's model does not "
                    f"declare it"
                )
                continue
            if parameter in computed:
                # The model computes it, so what it runs at is not readable from the file. Naming
                # a mismatch here would rest on the same inert attribute the check distrusts.
                continue
            run = _values_run_for(sedml_root, parameter)
            if run is None:
                continue
            candidates = list(run) + ([stated[parameter]] if parameter in stated else [])
            if any(math.isclose(value, candidate, rel_tol=rel_tol) for candidate in candidates):
                continue
            if not candidates:
                continue  # nothing states a value for it: unknown, not a disagreement
            detail = (
                f"the model states {stated[parameter]:g}" if parameter in stated else "the model states no value"
            )
            if run:
                detail += f" and the experiment runs it at {_format(run)}"
            problems.append(
                f"{where} sets {parameter!r} to {value:g}, which the archive never runs: {detail}"
            )
    return problems


__all__ = ["manuscript_mismatches"]
