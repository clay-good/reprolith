"""Checking a claims file's reference values against the paper's own printed tables.

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

import re
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "reported": self.reported,
            "cited": self.cited,
            "found": self.found,
            "detail": self.detail,
        }


def _numbers_in(rows: Sequence[Sequence[str]]) -> set[str]:
    """Every number a table prints, as it is printed, with separators removed."""
    found: set[str] = set()
    for row in rows:
        for cell in row:
            for match in _NUMBER.finditer(cell):
                found.add(match.group(0).replace(" ", "").replace(",", "").replace(" ", ""))
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
        hit = bool(spellings & printed)
        results.append(ValueCheck(
            claim_id, value, label, hit,
            (
                f"{value:g} is printed in {label}"
                if hit
                else f"{value:g} is not printed in {label}, which the claim cites"
            ),
        ))
    return tuple(results)


def unsupported_claims(checks: Sequence[ValueCheck]) -> tuple[ValueCheck, ...]:
    """The checks that came back false — a value the cited table does not print.

    Only ``False``, never ``None``: a claim whose table was not supplied is unchecked, and folding
    the two together would report an absence of evidence as evidence of absence, which is the
    mistake this module's own docstring refuses everywhere else.
    """
    return tuple(check for check in checks if check.found is False)


__all__ = ["ValueCheck", "check_claim_values", "unsupported_claims"]
