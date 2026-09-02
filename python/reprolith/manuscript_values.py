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

# The unit vocabulary, from the module that resolves units on the artifact path: one spelling of
# "unstated", and one Level 2 default table, so the two readers cannot drift apart on either.
from .ingest import _L2_PREDEFINED_UNITS, UNSTATED_UNIT

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
    #: The unit the model declares for this quantity, resolved through its ``unitDefinition`` —
    #: ``"unstated"`` when the model names none. Two numbers agreeing says nothing until this is
    #: the unit the paper printed, and a model in millilitres agreeing with a paper in litres is
    #: the most confident wrong answer this check can give.
    units: str = UNSTATED_UNIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "reported": self.reported,
            "carried": self.carried,
            "agrees": self.agrees,
            "detail": self.detail,
            "units": self.units,
        }


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


#: The base unit kinds SBML names without a definition. `litre` means litre; `unit_0` does not.
#: Level 2 also accepts the US spellings, and its `Celsius`.
_BASE_UNIT_KINDS = frozenset({
    "ampere", "avogadro", "becquerel", "candela", "celsius", "coulomb", "dimensionless", "farad",
    "gram", "gray", "henry", "hertz", "item", "joule", "katal", "kelvin", "kilogram", "liter",
    "litre", "lumen", "lux", "meter", "metre", "mole", "newton", "ohm", "pascal", "radian",
    "second", "siemens", "sievert", "steradian", "tesla", "volt", "watt", "weber",
})

#: The SI prefixes a paper writes a unit with, as the power of ten SBML states instead. Deca and
#: hecto are left out: nothing in this domain is written in them, and every entry here is a way for
#: two spellings of the same quantity to be read as different ones. Micro appears twice because
#: two characters are in use for it — the micro sign and Greek mu — and a file saved from either
#: keyboard is the same unit.
_PREFIXES = {
    "p": -12, "pico": -12, "n": -9, "nano": -9, "µ": -6, "μ": -6, "u": -6, "micro": -6, "m": -3, "milli": -3,
    "c": -2, "centi": -2, "d": -1, "deci": -1, "": 0, "k": 3, "kilo": 3, "M": 6, "mega": 6,
}

#: The base kinds a prefix may be written against, by every spelling this accepts, with the factor
#: that spelling carries over the kind: an hour is 3600 seconds, and a litre is one litre.
#:
#: `metre` is absent on purpose: a bare "m" is both a metre and the milli prefix, and no reading of
#: it is safe enough to compare a published number against a deposited one. So is a bare "d": it is
#: both deci and a day.
_UNIT_SPELLINGS: dict[str, tuple[str, float]] = {
    "l": ("litre", 1.0), "L": ("litre", 1.0), "litre": ("litre", 1.0), "liter": ("litre", 1.0),
    "litres": ("litre", 1.0), "liters": ("litre", 1.0),
    "mol": ("mole", 1.0), "mole": ("mole", 1.0), "moles": ("mole", 1.0),
    "g": ("gram", 1.0), "gram": ("gram", 1.0), "grams": ("gram", 1.0), "gramme": ("gram", 1.0),
    "s": ("second", 1.0), "sec": ("second", 1.0), "second": ("second", 1.0),
    "seconds": ("second", 1.0),
    "min": ("second", 60.0), "minute": ("second", 60.0), "minutes": ("second", 60.0),
    "h": ("second", 3600.0), "hr": ("second", 3600.0), "hour": ("second", 3600.0),
    "hours": ("second", 3600.0),
    "day": ("second", 86400.0), "days": ("second", 86400.0),
}

#: One factor as this module renders one or an author writes one: an optional multiplier, an
#: optional power of ten, and a name. ``3600*10^2 second`` and ``nmol`` are both one factor.
_ONE_FACTOR = re.compile(r"^(?:([0-9.eE+-]+)\*)?(?:10\^(-?\d+) )?([A-Za-zµμ]+)$")

#: Molar, which is the one unit in this domain that is written as a whole quantity rather than as
#: a product: ``nM`` is nanomoles per litre and nothing about the spelling says so. It is read only
#: when it is the whole unit, which is how it is written; a general algebra of composite symbols is
#: not what this needs.
_MOLAR = re.compile(r"^([A-Za-zµμ]*)M$")

#: A factor that is only a number, which ``*`` splitting separates from the kind it multiplies.
_NUMBER_ONLY = re.compile(r"^[0-9.eE+-]+$")


def _canonical_unit(text: str) -> tuple[float, str] | None:
    """One unit factor as ``(how many of the base kind, the base kind)``, or ``None``.

    The model's side is rendered from its own ``unitDefinition`` — ``10^-3 litre`` — and no author
    writes that. They write ``mL``. Comparing the two as strings refuses every pairing an author
    would actually make, which turns an opt-in check into a trap, so both sides are read down to
    the same pair before they are compared.

    ``None`` for anything this cannot read exactly — an exponent, an unknown name. Those fall back
    to comparing the strings, which errs toward refusing to compare. That is the safe direction: a
    unit read wrongly as another compares two numbers that mean different things, which is the
    whole failure this exists to prevent.
    """
    factor = _ONE_FACTOR.match(text.strip())
    if factor is None:
        return None
    try:
        multiplier = float(factor.group(1) or 1.0)
    except ValueError:
        return None
    scale, word = int(factor.group(2) or 0), factor.group(3)
    prefixed = 10.0 ** scale * multiplier
    if word in _UNIT_SPELLINGS:
        kind, carried = _UNIT_SPELLINGS[word]
        return (prefixed * carried, kind)
    # A prefixed spelling: the longest prefix that leaves a unit this knows.
    for prefix, power in sorted(_PREFIXES.items(), key=lambda item: -len(item[0])):
        if prefix and word.startswith(prefix) and word[len(prefix):] in _UNIT_SPELLINGS:
            kind, carried = _UNIT_SPELLINGS[word[len(prefix):]]
            return (prefixed * 10.0 ** power * carried, kind)
    return None


def _canonical_composite(text: str) -> tuple[float, tuple[str, ...], tuple[str, ...]] | None:
    """A whole unit — ``nmol*h/mL`` — as ``(factor, kinds over, kinds under)``, or ``None``.

    A claim's unit is composed: a concentration is substance over volume, and an area under the
    curve carries the run's time as well. One factor at a time is not enough to compare those, and
    comparing the composed strings is what refuses ``nmol/mL`` against ``10^-9 mole / 10^-3 litre``.

    Products are split on ``*`` and a factor that is only a number is re-joined to what follows it,
    because ``3600*10^2 second`` is one factor and ``nmol*h`` is two.
    """
    molar = _MOLAR.match(text.strip())
    if molar is not None and molar.group(1) in _PREFIXES:
        return (10.0 ** _PREFIXES[molar.group(1)], ("mole",), ("litre",))
    groups = text.split("/")
    if len(groups) > 2:
        return None  # two solidi is an ambiguity, not a unit this should guess at
    factor = 1.0
    sides: list[tuple[str, ...]] = []
    for index, group in enumerate(groups):
        merged: list[str] = []
        for token in (t.strip() for t in group.split("*")):
            if merged and _NUMBER_ONLY.match(merged[-1]):
                merged[-1] = f"{merged[-1]}*{token}"
            else:
                merged.append(token)
        kinds: list[str] = []
        for one in merged:
            canonical = _canonical_unit(one)
            if canonical is None:
                return None
            size, kind = canonical
            factor = factor * size if index == 0 else factor / size
            kinds.append(kind)
        sides.append(tuple(sorted(kinds)))
    return (factor, sides[0], sides[1] if len(sides) > 1 else ())


def _units_known_to_differ(stated: str, declared: str) -> bool:
    """Whether the two are readable *and* different — the test a report needs, not a refusal.

    :func:`_units_differ` answers the question a refusal asks: it says "different" when either side
    cannot be read, so an unreadable unit is not compared. A line that *asserts* a disagreement
    has to establish one, and this repository has already shipped one check that cried wolf on
    correct files. A unit nobody here can parse is not evidence that two files disagree.
    """
    one, other = _canonical_composite(stated), _canonical_composite(declared)
    if one is None or other is None:
        return False
    return not (
        one[1] == other[1] and one[2] == other[2] and math.isclose(one[0], other[0], rel_tol=1e-12)
    )


def _unit_ratio(stated: str, declared: str) -> float | None:
    """How many of the stated unit make one declared unit, when the two are the same dimensions.

    ``None`` when they are not, or when either cannot be read. A ratio is what makes a difference
    actionable: `10^-9 mole * 3600*10^2 second / 10^-3 litre` against `nmol*h/mL` is a wall of
    notation, and "100 times" is the finding.
    """
    one, other = _canonical_composite(stated), _canonical_composite(declared)
    if one is None or other is None or one[1] != other[1] or one[2] != other[2]:
        return None
    return other[0] / one[0] if one[0] else None


def _units_differ(stated: str, declared: str) -> bool:
    """Whether an author's unit and the model's declared one are different quantities."""
    if stated == declared:
        return False
    one, other = _canonical_composite(stated), _canonical_composite(declared)
    if one is None or other is None:
        return True  # unreadable on either side: refuse rather than guess
    return not (
        one[1] == other[1] and one[2] == other[2] and math.isclose(one[0], other[0], rel_tol=1e-12)
    )


#: Which attribute names each kind's unit. A species' is its *substance* unit; when the value read
#: is an ``initialConcentration`` the unit is that per the compartment's own, which is composed
#: below rather than reported as if the species were an amount.
_UNIT_ATTRIBUTES = {"parameter": "units", "compartment": "units", "species": "substanceUnits"}


def _render_unit_definition(definition: ET.Element) -> str:
    """A ``unitDefinition`` as a readable product of base kinds, scales and exponents.

    SBML defines each factor as ``(multiplier * 10^scale * kind)^exponent`` — the exponent applies
    to the whole prefixed quantity, not to the kind alone, and putting the multiplier and scale
    outside it states the *reciprocal* of what the file says. That is the defect
    :func:`reprolith.ingest._render_unit_definition` carries the story of, and this is the same
    rendering without libSBML, so `tests/test_parameter_values.py` holds the two to each other on
    every committed model rather than trusting that a second implementation stayed in step.
    """
    factors = []
    for unit in definition.iter():
        # The factors sit inside a `listOfUnits`, not directly under the definition.
        if _localname(unit.tag) != "unit":
            continue
        kind = unit.get("kind") or ""
        try:
            exponent = float(unit.get("exponent") or 1.0)
            scale = int(unit.get("scale") or 0)
            multiplier = float(unit.get("multiplier") or 1.0)
        except ValueError:
            return ""  # a unit whose own numbers do not parse is not a resolution
        head = ""
        if multiplier != 1.0:
            head += f"{multiplier:g}*"
        if scale != 0:
            head += f"10^{scale} "
        if exponent == 1.0:
            factors.append(f"{head}{kind}")
        elif head:
            factors.append(f"({head}{kind})^{exponent:g}")
        else:
            factors.append(f"{kind}^{exponent:g}")
    return " * ".join(factors)


def _resolve_unit(unit_id: str, definitions: Mapping[str, str], level: int) -> str:
    """What a unit reference means, or that the model states none.

    A model names a unit by reference — ``units="volume"`` — and the meaning lives in a
    ``unitDefinition`` elsewhere in the file. Reporting the reference is not reporting a unit:
    `volume`, `unit_0` and `substance` say nothing to an author comparing their published
    millilitres against a model's litres, which is the comparison this exists for.
    """
    if not unit_id:
        return UNSTATED_UNIT
    resolved = definitions.get(unit_id)
    if resolved:
        return resolved
    if unit_id in _BASE_UNIT_KINDS:
        return unit_id  # already a base kind: `litre` means litre
    # Level 2 predefines five names a model may use without defining them, and a model that
    # defines one overrides the default — which is why this is consulted after the definitions.
    if level == 2 and unit_id in _L2_PREDEFINED_UNITS:
        return _L2_PREDEFINED_UNITS[unit_id]
    return UNSTATED_UNIT


#: Which SBML element carries a settable number, and the attribute that holds it.
#:
#: A model's runnable state is not only its parameter table. A compartment's ``size`` is a PBPK
#: model's tissue volume and a species' initial amount is its initial condition, and a paper that
#: omits either leaves a reproducer guessing exactly as a missing parameter does. A curator pairing
#: a published liver volume with the compartment that carries it used to be told the model declares
#: no such parameter — a mismatch reported against a model holding the very number the paper prints.
#:
#: A species declares at most one of the two attributes; whichever is present is the value.
_VALUE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "parameter": ("value",),
    "compartment": ("size",),
    "species": ("initialAmount", "initialConcentration"),
}

#: The element list each kind lives in. Only the model's own lists are read: a parameter local to a
#: reaction is scoped to that reaction and is not what a paper's parameter table names.
_QUANTITY_CONTAINERS: dict[str, str] = {
    "listOfParameters": "parameter",
    "listOfCompartments": "compartment",
    "listOfSpecies": "species",
}


def _declared_quantities(
    model_sbml: str,
) -> tuple[dict[str, tuple[str, float | None, str]], set[str]]:
    """The model's settable quantities by id — kind, value and unit — and the ids that are inert.

    Dependency-free on purpose: this module runs on the core gate, where libSBML is not installed.

    The second half is the point. A quantity an ``initialAssignment`` or an ``assignment``/``rate``
    rule sets does not run at the number in its declaring attribute, and this repository has been
    caught three times over reading such an attribute as if it were live. Comparing one against a
    paper would produce the most confident wrong answer available: agreement with a number that
    never reaches the integrator.
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
    level = int(root.get("level") or 3)
    definitions = {
        definition.get("id") or "": _render_unit_definition(definition)
        for container in model
        if _localname(container.tag) == "listOfUnitDefinitions"
        for definition in container
        if _localname(definition.tag) == "unitDefinition"
    }
    values: dict[str, tuple[str, float | None, str]] = {}
    #: A species declaring a concentration is in substance per its compartment's own unit, so the
    #: compartment it names has to be resolved before the species can be described.
    compartment_units: dict[str, str] = {}
    concentrations: dict[str, str] = {}
    overridden: set[str] = set()
    for container in model:
        name = _localname(container.tag)
        if name in _QUANTITY_CONTAINERS:
            kind = _QUANTITY_CONTAINERS[name]
            for element in container:
                if _localname(element.tag) != kind:
                    continue
                identifier = element.get("id")
                if not identifier:
                    continue
                attribute = next(
                    (
                        name
                        for name in _VALUE_ATTRIBUTES[kind]
                        if element.get(name) is not None
                    ),
                    None,
                )
                raw = None if attribute is None else element.get(attribute)
                unit = _resolve_unit(
                    element.get(_UNIT_ATTRIBUTES[kind]) or "", definitions, level
                )
                if kind == "compartment":
                    compartment_units[identifier] = unit
                if attribute == "initialConcentration":
                    concentrations[identifier] = element.get("compartment") or ""
                try:
                    values[identifier] = (kind, None if raw is None else float(raw), unit)
                except ValueError:
                    values[identifier] = (kind, None, unit)
        elif name == "listOfInitialAssignments":
            overridden.update(
                assignment.get("symbol") or "" for assignment in container
            )
        elif name == "listOfRules":
            overridden.update(rule.get("variable") or "" for rule in container)
    overridden.discard("")
    for identifier, compartment in concentrations.items():
        kind, value, substance = values[identifier]
        per = compartment_units.get(compartment, UNSTATED_UNIT)
        values[identifier] = (
            kind,
            value,
            UNSTATED_UNIT
            if UNSTATED_UNIT in (substance, per)
            else f"{substance} / {per}",
        )
    return values, overridden


def _declared_parameters(model_sbml: str) -> tuple[dict[str, float | None], set[str]]:
    """The parameter slice of :func:`_declared_quantities`, kept as its own name.

    The parameter count this repository publishes is a count of *parameters*, and folding
    compartments and species into it would silently redefine a measured number rather than add one.
    """
    quantities, overridden = _declared_quantities(model_sbml)
    return (
        {
            name: value
            for name, (kind, value, _unit) in quantities.items()
            if kind == "parameter"
        },
        overridden,
    )


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

    A record may name any settable quantity the model declares — a parameter, a compartment's size,
    or a species' initial amount or concentration. A PBPK paper's parameter table prints tissue
    volumes, and those are compartments; pairing one used to be answered with a mismatch against a
    model carrying the published number.
    """
    values, overridden = _declared_quantities(model_sbml)
    results: list[ParameterCheck] = []
    for record in parameters:
        identifier = str(record.get("parameter") or "")
        raw = record.get("reported")
        if raw is None:
            results.append(ParameterCheck(
                identifier, math.nan, None, None,
                "no reported value to check (an unfilled row)",
                values.get(identifier, ("", None, UNSTATED_UNIT))[2],
            ))
            continue
        reported = float(raw)
        if identifier not in values:
            results.append(ParameterCheck(
                identifier, reported, None, False,
                f"the model declares no parameter, compartment or species {identifier!r}",
            ))
            continue
        kind, carried, units = values[identifier]
        attribute = " or ".join(_VALUE_ATTRIBUTES[kind])
        if identifier in overridden:
            results.append(ParameterCheck(
                identifier, reported, carried, None,
                f"the {kind} {identifier} is set by an initialAssignment or a rule, so the number "
                f"in its {attribute} attribute is not what runs and comparing it would answer "
                "about the wrong quantity",
                units,
            ))
            continue
        if carried is None:
            results.append(ParameterCheck(
                identifier, reported, None, None,
                f"the {kind} {identifier} declares no {attribute}, so there is nothing to compare",
                units,
            ))
            continue
        stated = str(record.get("reported_units") or "")
        if stated and units != UNSTATED_UNIT and _units_differ(stated, units):
            # Refused rather than compared, and never called a mismatch: the numbers are not in the
            # same quantity, so neither agreement nor disagreement between them means anything. A
            # paper's millilitres against a model's litres agree numerically at a factor of a
            # thousand, which is the failure that survives every check downstream of this one.
            results.append(ParameterCheck(
                identifier, reported, carried, None,
                f"your paper reports {identifier} in {stated} and the model declares it in "
                f"{units}, so the two numbers are not comparable as they stand",
                units,
            ))
            continue
        places = _printed_decimals(reported)
        rounded = round(carried, places)
        agrees = math.isclose(rounded, reported, rel_tol=0.0, abs_tol=1e-9)
        results.append(ParameterCheck(
            identifier, reported, carried, agrees,
            (
                f"the {kind} carries {carried:g}, which is {reported:g} at the "
                f"{places} decimal place(s) the paper prints"
                if agrees
                else f"the {kind} carries {carried:g}, which is {rounded:g} at the "
                f"{places} decimal place(s) the paper prints, not {reported:g}"
            ),
            units,
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


def quantities_the_paper_does_not_state(
    model_sbml: str, records: Sequence[Mapping[str, Any]]
) -> dict[str, tuple[str, ...]]:
    """Every settable quantity no supplied record pairs, grouped by kind.

    :func:`parameters_the_paper_does_not_state` answers this for the model's parameter table, which
    is the half a paper's parameter *table* is about. It is the same floor one level up: a PBPK
    model's tissue volumes are compartments and its initial conditions are species, and a paper
    that prints neither leaves a reproducer taking both from the deposit or guessing — which the
    parameter count could not see, because it never looked at those lists.

    Kinds with nothing unstated are omitted, so an author who paired everything gets an empty
    mapping rather than three empty lists. Inert quantities are excluded for the reason
    :func:`_declared_quantities` gives, and nothing here is judged: which of these belong in a
    paper is the author's call, as it is for a parameter.

    Raises ``ValueError`` if the model is not parseable SBML.
    """
    declared, determined = _declared_quantities(model_sbml)
    paired = {str(record.get("parameter") or "") for record in records}
    unstated: dict[str, list[str]] = {}
    for name, (kind, _value, _unit) in declared.items():
        if name in determined or name in paired:
            continue
        unstated.setdefault(kind, []).append(name)
    return {kind: tuple(sorted(names)) for kind, names in sorted(unstated.items())}


_PARAMETERS_FILL_IN = (
    "Delete the rows your paper does not report, then fill in 'reported' (the number your paper "
    "prints) and 'source_location' (where in the paper it is) on the ones that are left, and pass "
    "this file to: reprolith params-check --parameters. A row left blank is reported as unfilled "
    "rather than checked — there is nothing to compare it against."
)


def parameters_template(model_sbml: str, *, accession: str | None = None) -> dict[str, Any]:
    """Write the file :func:`check_parameter_values` reads, with the blanks left for the author.

    Pairing a paper's row with a model id is the author's judgment and is never inferred — but
    *typing out* their model's ids is not judgment, and a PBPK deposit has scores of them. This
    emits one row per settable quantity, kind and all, with the three things only the author knows
    left empty — the value, the unit they published it in, and where in the paper it is.

    **It never carries the model's own value.** ``reported`` comes out ``null`` on every row,
    always, for the reason :mod:`reprolith.claims_template` gives about claims: a template that
    filled in the number the model holds would hand the check the model's own value as the paper's,
    and the comparison would agree by construction — which is the exact failure the check exists to
    catch, moved one file upstream.

    Quantities the model's own math determines are listed apart, never as rows. Their declaring
    attribute is inert, so pairing one is refused downstream as *not compared*, and a template that
    invited the pairing would be inviting an answer about the wrong quantity.

    Raises ``ValueError`` if the model is not parseable SBML.
    """
    declared, determined = _declared_quantities(model_sbml)
    rows = [
        {
            "parameter": name,
            "kind": kind,
            "reported": None,
            "reported_units": "",
            "source_location": "",
        }
        for name, (kind, _value, _unit) in sorted(
            declared.items(), key=lambda item: (item[1][0], item[0])
        )
        if name not in determined
    ]
    inert: dict[str, list[str]] = {}
    for name, (kind, _value, _unit) in declared.items():
        if name in determined:
            inert.setdefault(kind, []).append(name)
    body: dict[str, Any] = {
        "parameters": rows,
        "determined_by_the_model": {kind: sorted(names) for kind, names in sorted(inert.items())},
        "fill_in": _PARAMETERS_FILL_IN,
    }
    return {"entries": {accession: body}} if accession is not None else body


@dataclass(frozen=True)
class UnitCheck:
    """What a claim says its value is in, against what the model reads that output in."""

    claim_id: str
    stated: str
    #: The unit the model's own declarations compose for this output, or ``"unstated"``.
    declared: str
    #: ``True`` the same quantity, ``False`` a different one, ``None`` not comparable.
    agrees: bool | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "stated": self.stated,
            "declared": self.declared,
            "agrees": self.agrees,
            "detail": self.detail,
        }


def _model_and_definitions(model_sbml: str) -> tuple[ET.Element, dict[str, str], int]:
    """The model element, its unit definitions by id, and its SBML level."""
    try:
        root = ET.fromstring(model_sbml)
    except ET.ParseError as exc:
        raise ValueError(f"not parseable SBML: {exc}") from exc
    model = next((c for c in root.iter() if _localname(c.tag) == "model"), None)
    if model is None:
        raise ValueError("the SBML document contains no model element")
    definitions = {
        definition.get("id") or "": _render_unit_definition(definition)
        for container in model
        if _localname(container.tag) == "listOfUnitDefinitions"
        for definition in container
        if _localname(definition.tag) == "unitDefinition"
    }
    return model, definitions, int(root.get("level") or 3)


def model_time_unit(model_sbml: str) -> str:
    """The unit the model's own time is in, resolved — or ``"unstated"``.

    Every time-course reference is on the model's clock: a figure read in minutes against a model
    running in hours produces values that are ordered, smooth, plausible and aligned to the wrong
    places. Raises ``ValueError`` if the model is not parseable SBML.
    """
    model, definitions, level = _model_and_definitions(model_sbml)
    return _resolve_unit(model.get("timeUnits") or "", definitions, level)


def claim_units(model_sbml: str, species: str, metric: str = "cmax") -> str:
    """The unit a claim's value is read in, composed from the model's own declarations.

    A **species'** time course is read as a concentration — the engine asks for concentration data
    for every species, whatever the species declares its initial value as — so the unit is the
    substance unit over the compartment's own. A **parameter's** is read as the value itself, so
    it is that parameter's own declared unit and nothing is composed. Both appear in a time course
    and either can be what a claim reads; leaving parameters out meant a curve plotting one was
    passed over in silence, which reads exactly like agreement.

    An ``auc`` carries the run's time as well, which is why the metric is a term: the same output
    read two ways is two different quantities, and the paper's table says so in its own column
    headers.

    Returns ``"unstated"`` when any part of the composition is not resolvable, rather than a
    partial unit that reads as if it were established. Raises ``ValueError`` if the model is not
    parseable SBML or declares no such output.
    """
    model, definitions, level = _model_and_definitions(model_sbml)
    element = next(
        (
            child
            for container in model
            if _localname(container.tag) == "listOfSpecies"
            for child in container
            if child.get("id") == species
        ),
        None,
    )
    if element is None:
        parameter = next(
            (
                child
                for container in model
                if _localname(container.tag) == "listOfParameters"
                for child in container
                if child.get("id") == species
            ),
            None,
        )
        if parameter is None:
            raise ValueError(f"the model declares no species or parameter {species!r}")
        own = _resolve_unit(parameter.get("units") or "", definitions, level)
        time = _resolve_unit(model.get("timeUnits") or "", definitions, level)
        if own == UNSTATED_UNIT or (metric == "auc" and time == UNSTATED_UNIT):
            return UNSTATED_UNIT
        return f"{own} * {time}" if metric == "auc" else own
    compartment = next(
        (
            child
            for container in model
            if _localname(container.tag) == "listOfCompartments"
            for child in container
            if child.get("id") == element.get("compartment")
        ),
        None,
    )
    # A model may state each unit once for the whole model and leave the elements silent; the
    # element's own attribute wins where it has one.
    substance = _resolve_unit(
        element.get("substanceUnits") or model.get("substanceUnits") or "", definitions, level
    )
    volume = _resolve_unit(
        (compartment.get("units") if compartment is not None else "")
        or model.get("volumeUnits")
        or "",
        definitions,
        level,
    )
    time = _resolve_unit(model.get("timeUnits") or "", definitions, level)  # the run's own clock
    parts = (substance, volume) + ((time,) if metric == "auc" else ())
    if UNSTATED_UNIT in parts:
        return UNSTATED_UNIT
    over = f"{substance} * {time}" if metric == "auc" else substance
    return f"{over} / {volume}"


def check_claim_units(
    model_sbml: str, claims: Sequence[Mapping[str, Any]]
) -> tuple[UnitCheck, ...]:
    """Check each claim's stated unit against the one the model reads that output in.

    Every certificate in this repository compares a claim's number against a number the model
    produces, and nothing established that the two are the same *quantity*. A paper's µg/mL against
    a model's nmol/mL is a verdict about arithmetic that has nothing to do with the model — and it
    is not caught downstream, because the reconstruction runs the model's own numbers and
    reproduces the model's own curve.

    A claim that states no unit is reported as unchecked, never as agreement: this is opt-in, and
    the absence of a statement is not a statement.
    """
    results: list[UnitCheck] = []
    for record in claims:
        claim_id = str(record.get("claim_id") or "")
        stated = str(record.get("reported_units") or "")
        try:
            declared = claim_units(
                model_sbml, str(record.get("species") or ""), str(record.get("metric") or "cmax")
            )
        except ValueError as unreadable:
            results.append(UnitCheck(claim_id, stated, UNSTATED_UNIT, None, str(unreadable)))
            continue
        if not stated:
            results.append(UnitCheck(
                claim_id, "", declared, None,
                f"this claim states no unit; the model reads that output in {declared}",
            ))
        elif declared == UNSTATED_UNIT:
            results.append(UnitCheck(
                claim_id, stated, declared, None,
                "the model states no unit for that output, so there is nothing to compare against",
            ))
        elif not _units_known_to_differ(stated, declared) and _units_differ(stated, declared):
            # Readable on neither side, or on only one. A verdict of "another unit" is an
            # accusation, and one this cannot establish: an axis in "arbitrary units" or a percent
            # is not evidence that the claim and the model disagree. Not checked, like a claim
            # that stated nothing.
            results.append(UnitCheck(
                claim_id, stated, declared, None,
                f"this claim is in {stated}, which is not a unit this can read against "
                f"{declared}, so the two were not compared",
            ))
        elif _units_differ(stated, declared):
            results.append(UnitCheck(
                claim_id, stated, declared, False,
                f"this claim is in {stated} and the model reads that output in {declared}"
                + (
                    f", which is {ratio:g} times as large"
                    if (ratio := _unit_ratio(stated, declared)) is not None
                    else ""
                ),
            ))
        else:
            results.append(UnitCheck(
                claim_id, stated, declared, True,
                f"{stated} is the unit the model reads that output in ({declared})",
            ))
    return tuple(results)


def claims_in_another_unit(checks: Sequence[UnitCheck]) -> tuple[UnitCheck, ...]:
    """The checks that came back false, and never the ones that could not be made."""
    return tuple(check for check in checks if check.agrees is False)


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
    "UnitCheck",
    "check_claim_units",
    "check_claim_values",
    "check_parameter_values",
    "claim_units",
    "claims_in_another_unit",
    "model_time_unit",
    "disagreeing_parameters",
    "parameters_template",
    "parameters_the_paper_does_not_state",
    "quantities_the_paper_does_not_state",
    "unsupported_claims",
]
