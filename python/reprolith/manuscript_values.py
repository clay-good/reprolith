"""Checking a repository's numbers against the paper's own printed tables.

Two halves, and they check different things. :func:`check_claim_values` asks whether a *claim's*
reference value is printed in the table it cites — the curator's transcription against the paper.
:func:`check_parameter_values` asks whether the *model* carries a parameter value the paper prints
— the deposited artifact against the paper. Nothing had ever asked the second question of any model
in this repository.

Every reference value in this repository except two is checked against its generator — COBRApy,
libRoadRunner, CANA, closed-form mathematics. The two that come from a *manuscript* were checked
against nothing, and one of them was a number the paper does not contain: metformin's 500 mg
plasma Cmax was recorded as 6.2 nmol/mL where the paper prints 6.1, cited to a table that gives
5.7. Both correct and incorrect values passed, because they sit inside the same tolerance on the
same simulated peak — so the pipeline could not see it from the inside, and nineteen audit passes
did not.

This is the check that would have. Given the rows of the tables a paper prints, it asks two
mechanical questions of every claim: **is the value you state printed in the table you cite**, and
**does that table exist**. It is deliberately narrow, and what it does *not* do matters as much:

``it never decides which cell is the right one``
    A table prints many numbers, and which one a claim targets is the curator's judgment. This
    asks only whether the number is there at all — the weakest question that would still have
    caught the defect, and the strongest one that cannot accuse a correct claim.

``it never reads the paper``
    The tables come in as data, quoted and committed (``datasets/manuscripts/``, and
    ``scripts/fetch_manuscript_tables.py`` to regenerate). A checker that fetched would be a
    checker that stopped working offline and in CI, and its answer would change with the network.

``it says nothing about a claim citing no table``
    A value read from a figure panel or a sentence is not a defect, and reporting one as unchecked
    is different from reporting it as wrong. Both are returned, in separate lists.
"""

from __future__ import annotations

import decimal
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: A table's label as a claim would cite it: "Table 6", "Table S2", "table 4".
_LABEL = re.compile(r"\btables?\s+([A-Za-z]?\d+[a-z]?)\b", re.IGNORECASE)

#: A number as a paper prints one, including thousands separated by a space or a comma.
_NUMBER = re.compile(r"[-+]?\d[\d  ,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class ValueCheck:
    """What was found for one claim: which table it cited, and whether its value is in it."""

    claim_id: str
    reported: float
    cited: str | None
    #: ``None`` when no table was cited or the cited one is not in the supplied rows — the value
    #: was not checked, which is a different fact from its being absent.
    found: bool | None
    detail: str
    #: How many cells of the cited table print this value; ``None`` where nothing was checked.
    #: A match is evidence, and one match is much better evidence than seven — see
    #: :func:`check_claim_values`.
    occurrences: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "reported": self.reported,
            "cited": self.cited,
            "found": self.found,
            "occurrences": self.occurrences,
            "detail": self.detail,
        }


def _numbers_in(rows: Sequence[Sequence[str]]) -> Counter[str]:
    """Every number a table prints, as it is printed, with separators removed — and how often.

    Counted rather than collected into a set, because *how often* is the difference between two
    strengths of the same "ok". See :func:`check_claim_values`.
    """
    found: Counter[str] = Counter()
    for row in rows:
        for cell in row:
            for match in _NUMBER.finditer(cell):
                found[match.group(0).replace(" ", "").replace(",", "").replace(" ", "")] += 1
    return found


def _cited_label(source_location: str, labels: Mapping[str, Any]) -> str | None:
    """The table label this claim cites, matched against the labels actually supplied."""
    for match in _LABEL.finditer(source_location or ""):
        wanted = f"table {match.group(1)}".casefold()
        for label in labels:
            if label.casefold() == wanted:
                return label
    return None


def check_claim_values(
    claims: Sequence[Mapping[str, Any]], tables: Mapping[str, Mapping[str, Any]]
) -> tuple[ValueCheck, ...]:
    """Check each claim's reported value against the rows of the table it cites.

    ``claims`` are claims-file records (``claim_id``, ``reported``, ``source_location``);
    ``tables`` maps a table's label as the paper prints it — ``"Table 6"`` — to a mapping with a
    ``rows`` list of cell lists, which is the shape ``datasets/manuscripts/`` stores.

    A value is matched **as the paper prints it**, not numerically: a paper printing ``6.1`` and a
    claim stating ``6.10`` are the same number and the same claim, so both spellings are tried, but
    a claim stating ``6.13`` is not matched to ``6.1`` by rounding. Rounding here would accept the
    value a paper *would have* printed rather than the one it did, which is the accusation this
    exists to make.
    """
    results: list[ValueCheck] = []
    for record in claims:
        claim_id = str(record.get("claim_id") or "")
        reported = record.get("reported")
        source = str(record.get("source_location") or "")
        if reported is None:
            results.append(ValueCheck(
                claim_id, float("nan"), None, None,
                "no reported value to check (an unfilled claims template)",
            ))
            continue
        value = float(reported)
        label = _cited_label(source, tables)
        if label is None:
            cited = _LABEL.search(source)
            results.append(ValueCheck(
                claim_id, value, cited.group(0) if cited else None, None,
                (
                    f"cites {cited.group(0)!r}, which was not supplied"
                    if cited
                    else "cites no table, so its value was not checked here"
                ),
            ))
            continue
        rows = tables[label].get("rows") or ()
        if not rows:
            # A table supplied with no rows prints nothing, and treating that as "the value is
            # absent" turns a malformed input into an accusation against every claim citing it —
            # the one outcome this module exists to avoid.
            results.append(ValueCheck(
                claim_id, value, label, None,
                f"{label} was supplied with no rows, so nothing in it could be compared",
            ))
            continue
        printed = _numbers_in(rows)
        spellings = {repr(value).rstrip("0").rstrip("."), f"{value:g}", str(value)}
        if value == int(value):
            spellings.add(str(int(value)))
        # How often, not merely whether. A match is evidence that the claim reads the cell it
        # cites, and its strength is exactly how distinctive the number is: 71.8 appears once in
        # the metformin paper's Table 6, and 1.9 appears seven times, so the second is evidence
        # only that the table contains that number somewhere. Both used to report the same "ok".
        # Measured over the committed corpus: 27 of 33 claim values are unique in their table.
        # This never turns a match into a miss — it says what the match is worth.
        occurrences = sum(printed[spelling] for spelling in spellings if spelling in printed)
        hit = occurrences > 0
        others = occurrences - 1
        strength = (
            "" if others < 1
            else ", but so is 1 other cell — the match is not unique" if others == 1
            else f", but so are {others} other cells — the match is not unique"
        )
        results.append(ValueCheck(
            claim_id, value, label, hit,
            (
                f"{value:g} is printed in {label}{strength}"
                if hit
                else f"{value:g} is not printed in {label}, which the claim cites"
            ),
            occurrences=occurrences,
        ))
    return tuple(results)


@dataclass(frozen=True)
class ParameterCheck:
    """What was found for one parameter: what the paper prints, and what the model carries."""

    parameter: str
    reported: float
    #: The value the model declares. ``None`` when it declares no such parameter, or declares one
    #: with no value.
    carried: float | None
    #: ``True`` agrees at the precision the paper printed, ``False`` disagrees, ``None`` not
    #: comparable — which is a different fact from disagreeing, and is never folded into it.
    agrees: bool | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "reported": self.reported,
            "carried": self.carried,
            "agrees": self.agrees,
            "detail": self.detail,
        }


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _declared_parameters(model_sbml: str) -> tuple[dict[str, float | None], set[str]]:
    """The model's own parameters by id, and the ids whose declared value is inert.

    Dependency-free on purpose: this module runs on the core gate, where libSBML is not installed.

    The second half is the point. A parameter an ``initialAssignment`` or an ``assignment``/``rate``
    rule sets does not run at the number in its ``value`` attribute, and this repository has been
    caught three times over reading such an attribute as if it were live. Comparing one against a
    paper would produce the most confident wrong answer available: agreement with a number that
    never reaches the integrator.

    Only the model's own ``listOfParameters`` is read. A parameter local to a reaction is scoped to
    that reaction and is not what a paper's parameter table names.
    """
    try:
        root = ET.fromstring(model_sbml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SBML: {exc}") from exc
    model = next(
        (c for c in root.iter() if _localname(c.tag) == "model"),
        None,
    )
    if model is None:
        raise ValueError("the SBML document contains no model element")
    values: dict[str, float | None] = {}
    overridden: set[str] = set()
    for container in model:
        name = _localname(container.tag)
        if name == "listOfParameters":
            for parameter in container:
                if _localname(parameter.tag) != "parameter":
                    continue
                identifier = parameter.get("id")
                if not identifier:
                    continue
                raw = parameter.get("value")
                try:
                    values[identifier] = None if raw is None else float(raw)
                except ValueError:
                    values[identifier] = None
        elif name == "listOfInitialAssignments":
            overridden.update(
                assignment.get("symbol") or "" for assignment in container
            )
        elif name == "listOfRules":
            overridden.update(rule.get("variable") or "" for rule in container)
    overridden.discard("")
    return values, overridden


def _printed_decimals(value: float) -> int:
    """How many decimal places a paper printed, read off the value as it was transcribed."""
    exponent = decimal.Decimal(repr(float(value))).as_tuple().exponent
    return -int(exponent) if isinstance(exponent, int) and exponent < 0 else 0


def check_parameter_values(
    model_sbml: str, parameters: Sequence[Mapping[str, Any]]
) -> tuple[ParameterCheck, ...]:
    """Check a model's declared parameter values against the ones a paper's table prints.

    ``parameters`` are records naming the model parameter and the value the paper reports for it
    (``parameter``, ``reported``, and a ``source_location`` this does not read). Which model
    parameter a paper's row names is a curator's judgment and is never guessed here: rows are
    paired with ids in a committed file, the way reference values are.

    **Agreement is at the precision the paper printed, and no finer.** A paper printing ``0.7`` for
    a model carrying ``0.73`` agrees — it cannot distinguish ``0.73`` from ``0.749``, and demanding
    equality would accuse a correct deposition of a mismatch its own source cannot support. The
    consequence travels with the answer: this establishes that the model is consistent with the
    printed value, not that it holds the value the authors fitted.
    """
    values, overridden = _declared_parameters(model_sbml)
    results: list[ParameterCheck] = []
    for record in parameters:
        identifier = str(record.get("parameter") or "")
        raw = record.get("reported")
        if raw is None:
            results.append(ParameterCheck(
                identifier, math.nan, None, None,
                "no reported value to check (an unfilled row)",
            ))
            continue
        reported = float(raw)
        if identifier not in values:
            results.append(ParameterCheck(
                identifier, reported, None, False,
                f"the model declares no parameter {identifier!r}",
            ))
            continue
        if identifier in overridden:
            results.append(ParameterCheck(
                identifier, reported, values[identifier], None,
                f"{identifier} is set by an initialAssignment or a rule, so the number in its "
                "value attribute is not what runs and comparing it would answer about the wrong "
                "quantity",
            ))
            continue
        carried = values[identifier]
        if carried is None:
            results.append(ParameterCheck(
                identifier, reported, None, None,
                f"{identifier} declares no value, so there is nothing to compare",
            ))
            continue
        places = _printed_decimals(reported)
        rounded = round(carried, places)
        agrees = math.isclose(rounded, reported, rel_tol=0.0, abs_tol=1e-9)
        results.append(ParameterCheck(
            identifier, reported, carried, agrees,
            (
                f"the model carries {carried:g}, which is {reported:g} at the "
                f"{places} decimal place(s) the paper prints"
                if agrees
                else f"the model carries {carried:g}, which is {rounded:g} at the "
                f"{places} decimal place(s) the paper prints, not {reported:g}"
            ),
        ))
    return tuple(results)


def parameters_the_paper_does_not_state(
    model_sbml: str, records: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """The model's own settable parameters that no supplied record pairs with a reported value.

    :func:`check_parameter_values` answers "does the model carry what the paper says?" for every
    parameter the paper *does* report, and says nothing at all about the ones it does not. That is
    a floor that cannot see what it never counted, and the number it hides is the one this project
    exists to surface: a parameter the paper omits is a value a reproducer rebuilding from the
    paper has to take from the author's file, or guess. On the shipped metformin model, ten of the
    sixteen settable parameters are reported and six are not.

    Only *settable* parameters are counted. A parameter an ``initialAssignment`` or a rule
    determines does not run at the number in its ``value`` attribute, so a paper is not omitting
    anything by leaving it out — asking an author to publish it would be asking them to publish an
    inert attribute. That is the same distinction :func:`_declared_parameters` draws for the
    comparison itself, drawn once and used by both.

    Reported, never judged. A model has parameters no paper would print, and which of these belong
    in a paper is the author's call — the same call :func:`check_claim_values` leaves to a curator
    about which table cell a claim reads.

    Raises ``ValueError`` if the model is not parseable SBML.
    """
    declared, determined = _declared_parameters(model_sbml)
    paired = {str(record.get("parameter") or "") for record in records}
    return tuple(
        sorted(name for name in declared if name not in determined and name not in paired)
    )


def disagreeing_parameters(checks: Sequence[ParameterCheck]) -> tuple[ParameterCheck, ...]:
    """The checks that came back false — a value the model does not carry.

    Only ``False``, never ``None``, for the reason :func:`unsupported_claims` gives: a parameter
    whose declared value is inert was not compared, and reporting it beside one that genuinely
    disagrees would turn "not checked" into "wrong".
    """
    return tuple(check for check in checks if check.agrees is False)


def unsupported_claims(checks: Sequence[ValueCheck]) -> tuple[ValueCheck, ...]:
    """The checks that came back false — a value the cited table does not print.

    Only ``False``, never ``None``: a claim whose table was not supplied is unchecked, and folding
    the two together would report an absence of evidence as evidence of absence, which is the
    mistake this module's own docstring refuses everywhere else.
    """
    return tuple(check for check in checks if check.found is False)


__all__ = [
    "ParameterCheck",
    "ValueCheck",
    "check_claim_values",
    "check_parameter_values",
    "disagreeing_parameters",
    "parameters_the_paper_does_not_state",
    "unsupported_claims",
]
