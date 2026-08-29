"""Proposing candidate claims from the tables a paper prints (bootstrap task 2.2).

Thirty of the thirty-one entries in the PK/PD test set abstain, all for the same reason: nobody
has said which of the paper's results a reproduction should target. `claims_template` supplies one
half of a claims file from the author's *model* — the outputs a claim can read — and leaves the
number blank. This supplies the other half from the author's *paper*: every number its tables
print, with the row and column that name it.

**These are candidates, not claims.** A number in a table is not a statement that a model should
reproduce it: the same table routinely carries measured data, fitted values, percentage
differences, and doses. Which of them a reproduction targets is a judgment about the paper, and
this makes none of it. What it does is turn "read the paper and type them in" into "delete the
rows you do not mean", which is the same shape `claims_template` gives the model half.

Nothing here is guessed:

``the model output is never proposed``
    Matching a table's "Plasma" to a model's `mPlasmaVenous` is a judgment, and a wrong match is a
    certificate checking the wrong species against a real number — worse than no candidate at all.
    Every candidate's ``species`` is blank, and the loader refuses a claims file that still is.

``a metric is proposed only where the paper's own wording names one``
    A column headed "Cmax" says how the number comes off a trajectory; one headed "Amount at Cmax"
    does not, and neither does "AUC measured-fitted, %". A table may instead put the quantity down
    the side — "AUC", "Cmax", "Tmax" as row labels with the models across the top — and that
    wording states it too, taken only when the heading states none and the row names exactly one.
    Where neither says, the field is blank rather than defaulted, because a defaulted metric is a
    claim about the paper.

``a value's stated spread is carried, not consumed``
    A paper printing ``10.2 ± 1.18`` reported 10.2 and said how far it varies. The value is the
    candidate and the spread travels beside it, because nothing here compares distributions yet
    and dropping it would lose the paper's own account of what counts as a difference.

``a ragged table is refused, not aligned``
    A cell spanning rows is written once, so reading cells positionally puts a value under the
    wrong header — the exact way a reference value becomes a number the paper prints somewhere
    else. A table whose rows are not all the width of its header is skipped and named.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

#: A cell that is a number and nothing else. A cell reading "5.7 (2.1)" states two things and
#: which one the column means is not mechanical, so it is not proposed.
_NUMERIC = re.compile(r"^[-+]?\d[\d  ,]*(?:\.\d+)?(?:[eE][-+]?\d+)?$")

#: A value with its stated spread — ``10.2 ± 1.18``. Unlike parentheses, which may hold a range,
#: a confidence interval, or an ``n``, the sign says exactly one thing: this is the value, and
#: that is how far it varies. Refusing these cost more than it saved — the first paper this tool
#: was pointed at outside its own corpus prints every result that way, and a survey built on the
#: bare-number rule counted its results table as holding none.
_WITH_SPREAD = re.compile(
    r"^([-+]?\d[\d  ,]*(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?:±|\+/-|\+-)\s*"
    r"(\d[\d  ,]*(?:\.\d+)?(?:[eE][-+]?\d+)?)$"
)

#: Column headings whose wording states how a number comes off a time course. Matched on the
#: heading's first word only: "Cmax, nmol/mL" names a peak, and "Cmax measured-fitted, %" is a
#: comparison between two numbers rather than one of them.
_METRICS = {"cmax": "cmax", "auc": "auc", "auc24": "auc"}

#: Column headings that are the row's *conditions* rather than a result — a dose, a time point.
#: Proposed as a candidate's conditions, never as its value.
_CONDITIONS = re.compile(r"^(dose|study|tissue|type|group|subject|species|model)\b", re.IGNORECASE)


def _value_and_spread(cell: str) -> tuple[str, str] | None:
    """``(value, stated spread)`` for a cell that is a number, or ``None`` when it is not.

    The spread is ``""`` for a bare number. It is never folded into the value and never dropped:
    a paper reporting ``10.2 ± 1.18`` reported 10.2, and how far it varies is part of what it
    said.
    """
    text = cell.strip()
    if _NUMERIC.match(text):
        return text, ""
    spread = _WITH_SPREAD.match(text)
    return (spread.group(1), spread.group(2)) if spread else None


def _to_float(text: str) -> float:
    return float(text.replace(" ", "").replace(",", "").replace("\u202f", ""))


def _metric_for(heading: str) -> str:
    """The metric a column heading states, or ``""`` when it states none."""
    if "%" in heading:
        return ""  # a difference between two numbers, not one of them
    first = re.split(r"[,\s]", heading.strip(), maxsplit=1)[0].casefold()
    return _METRICS.get(first, "")


def propose_claims(
    tables: Mapping[str, Mapping[str, Any]], *, accession: str | None = None
) -> dict[str, Any]:
    """Candidate claims for every number the supplied tables print.

    ``tables`` maps a table's label as the paper prints it — ``"Table 6"`` — to a mapping with
    ``rows`` (a rectangular list of cell lists, header first) and optionally ``caption``; that is
    the shape ``datasets/manuscripts/`` stores and ``scripts/fetch_manuscript_tables.py`` writes.

    Returns a claims-file skeleton: ``candidates`` in the claims-file record shape with
    ``species`` blank, ``notes`` for anything not proposed, and the tables it read. ``accession``
    wraps it in the ``entries`` shape a multi-paper claims file uses.
    """
    candidates: list[dict[str, Any]] = []
    notes: list[str] = []
    seen: set[str] = set()

    for label in tables:
        rows = list(tables[label].get("rows") or ())
        if len(rows) < 2:
            notes.append(f"{label} has no data rows, so nothing was proposed from it")
            continue
        header = [str(cell) for cell in rows[0]]
        ragged = [i for i, row in enumerate(rows[1:], start=1) if len(row) != len(header)]
        if ragged:
            notes.append(
                f"{label} has {len(ragged)} row(s) that are not the width of its header, so a "
                "value cannot be put under a column without guessing; nothing was proposed from "
                "it. Resolve its row and column spans first"
            )
            continue
        # A column is the row's label rather than a result in two ways, and both are needed. Its
        # heading may say so — a dose is a condition even though its cells are numbers — or it may
        # simply hold no numbers at all, which catches a "Parameter" column reading AUC/Cmax/Tmax
        # without a vocabulary that has to anticipate every word a paper might use. Measuring
        # alone would make a dose a result; the vocabulary alone lost the row label that says what
        # the number *is*, on the first paper outside this corpus it was pointed at.
        label_columns = [
            i for i, head in enumerate(header)
            if _CONDITIONS.match(head)
            or not any(_value_and_spread(str(row[i])) for row in rows[1:])
        ]
        for index, row in enumerate(rows[1:], start=1):
            conditions = ", ".join(
                f"{header[i]} {row[i]}" for i in label_columns if str(row[i]).strip()
            )
            # A table may put the quantity in a row label instead of a column heading — "AUC" and
            # "Cmax" down the side, the models across the top — and that wording states a metric
            # exactly as a heading does. Taken only when the heading states none and the row names
            # exactly one, so an ambiguous row proposes no metric rather than a guessed one.
            stated = {_metric_for(str(row[i])) for i in label_columns} - {""}
            row_metric = next(iter(stated)) if len(stated) == 1 else ""
            for column, heading in enumerate(header):
                cell = str(row[column]).strip()
                if column in label_columns:
                    continue
                parsed = _value_and_spread(cell)
                if parsed is None:
                    continue
                value, spread = parsed
                where = ", ".join(
                    part for part in (conditions, f"{heading} column") if part
                )
                claim_id = f"{label.replace(' ', '')}-r{index}c{column}"
                if claim_id in seen:
                    continue
                seen.add(claim_id)
                record: dict[str, Any] = {
                    "claim_id": claim_id,
                    "quantity": f"{heading}{f' ({conditions})' if conditions else ''}",
                    # Never proposed: which model output this row names is a judgment about the
                    # paper, and a wrong one checks a real number against the wrong species.
                    "species": "",
                    "reported": _to_float(value),
                    "source_location": (
                        f"{label}, {where}" if where else label
                    ) + (f" (reported as {cell})" if spread else ""),
                    "metric": _metric_for(heading) or row_metric,
                    "parameter_overrides": {},
                }
                if spread:
                    # Carried, not consumed: the oracle here compares scalars, so nothing reads
                    # this yet — and dropping a stated spread on the way past would lose the one
                    # thing that says how much of a difference the paper itself calls a
                    # difference.
                    record["reported_spread"] = _to_float(spread)
                candidates.append(record)
    if not candidates and not notes:
        notes.append("no table printed a number on its own in a cell, so nothing was proposed")
    notes.append(
        "These are candidates, not claims: a table prints measured values, fitted values, "
        "percentage differences and doses side by side, and which of them your model should "
        "reproduce is your judgment. Delete the rest, then name the model output each one reads."
    )

    body: dict[str, Any] = {
        "description": (
            "Candidate claims read from the tables the paper prints. Delete the ones your model "
            "is not asked to reproduce, fill in 'species' on the ones that are left, and check "
            "the result with: reprolith claims-check --claims <file> --tables <tables>"
        ),
        "candidates": candidates,
        "tables_read": sorted(tables),
        "notes": notes,
    }
    if accession is not None:
        return {"description": body["description"], "entries": {accession: body}}
    return body


__all__ = ["propose_claims"]
