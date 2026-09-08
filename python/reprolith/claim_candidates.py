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
_METRICS = {
    "cmax": "cmax", "auc": "auc", "auc24": "auc", "tmax": "tmax",
    # A column headed "Period, h" is a claim this engine can express now; before it could, leaving
    # the word out cost nothing, and after it did the heading would have been read as no metric at
    # all. "Amplitude" is deliberately absent: the field spells it two ways that differ by a factor
    # of two, so a heading naming it states no metric this can express.
    "period": "period",
}

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
    # Split on the period too. This paper's own Table 1 separates the heading from its unit with
    # one — `Cmax. nmol/mL` where every other table of the same paper writes `Cmax, nmol/mL` — and
    # the first token came out `cmax.`, which is in no table of metrics. Every candidate from that
    # table was proposed with no metric at all, for one of the four entries this repository
    # certifies, while the unit beside it read cleanly.
    first = re.split(r"[,.\s]", heading.strip(), maxsplit=1)[0].casefold()
    return _METRICS.get(first, "")


def _unit_for(heading: str) -> str:
    """The unit a column heading names, or ``""`` when it names none this can read.

    A results table says what its numbers are *of* in the heading — ``Cmax, nmol/mL`` beside
    ``AUC24, nmol*h/mL`` — and a candidate without it is a bare number a curator has to go back to
    the paper for. The tail after the last separator is taken and then *checked*: it is a unit only
    if the unit reader can read it as one, so ``Cmax measured-fitted, %`` proposes nothing, which
    is right twice over — a percentage difference is not one of the values, and a unit this cannot
    read must not be published as one.
    """
    from .manuscript_values import _canonical_composite

    tail = re.split(r"[,.]", heading.strip())[-1].strip()
    return tail if tail and _canonical_composite(tail) is not None else ""


#: The sentence that ends every proposal: what the reader has to decide, in the vocabulary of the
#: file being proposed. It is not a refusal, so a caller reshaping the candidates drops this one
#: and keeps the rest.
_PICK_YOUR_OWN = (
    "These are candidates, not claims: a table prints measured values, fitted values, "
    "percentage differences and doses side by side, and which of them your model should "
    "reproduce is your judgment. Delete the rest, then name the model output each one reads."
)


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
                    # The unit the heading names, under the key the checks read. A candidate that
                    # reaches `claims-check --model` with it is checked against the unit the model
                    # reads that output in; without it the check has nothing to compare, and a
                    # number in one unit judged against a model in another is a verdict about
                    # arithmetic.
                    "reported_units": _unit_for(heading),
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
    # Last, and last on purpose: everything before it is a *refusal* — a table this could not read
    # positionally, a cell it would not split — and a caller reshaping these candidates into
    # another file's vocabulary keeps those and replaces this one.
    notes.append(_PICK_YOUR_OWN)

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


#: The units a number can wear in the prose of a paper this engine certifies. The unit is what
#: separates a reported quantity from a figure number, a citation, a year, or a count of datasets —
#: a bare number in a sentence is almost never a result, and admitting one buries the ones that are.
#:
#: Ordered longest-first within each family, because the alternation is first-match: "nmol/mL"
#: before "nM" or the reader takes a prefix and calls it the unit.
#:
#: This list was one class's for as long as one class had a manuscript reader. The engine certifies
#: six, and a paper about any of the other five states its results in units nothing here knew: a
#: front speed in µm/min, a decay length in µm, a flux in mmol/gDW/h, a growth rate in 1/h. Those
#: sentences produced no candidate at all — not a noisy one a curator would delete, *nothing* — so
#: the surface that exists to turn "read the paper and type them in" into "delete the rows you do
#: not mean" had no rows to offer for five sixths of what this engine can judge.
_PROSE_UNITS = (
    # concentration and exposure (PK/PD, kinetic)
    "nmol\\*h/mL", "nmol/mL", "µg/mL", "ug/mL", "mg/L", "ng/mL", "mmol/L", "µM", "nM",
    # specific flux and growth rate (constraint-based)
    "mmol/gDW/h", "mmol/gDW/hr", "mmol gDW-1 h-1", "1/h", "h-1", "h⁻¹",
    # length (spatial: a decay length, a wavelength, a domain)
    "µm", "um", "mm", "cm",
    # speed (spatial: an invasion front)
    "µm/min", "um/min", "µm/h", "mm/h", "mm/day",
    # diffusivity (spatial)
    "µm²/s", "um2/s", "cm²/s", "cm2/s",
    # time (every class). Spelled out for seconds, and the abbreviation deliberately left out: a
    # bare "s" cannot be told from a plural or a panel label, so "data collected in the 1990s"
    # reads as 1990 seconds and "Fig 2s" as two — a year and a figure reference, which are the two
    # things this reader's unit rule exists to keep out. Found by re-reading the widened list
    # against the sentences it would now admit.
    "h", "hours?", "min", "seconds?",
)
_PROSE_VALUE = re.compile(
    r"(?<![\w.])([-+]?\d[\d ,]*(?:\.\d+)?)\s*"
    r"(" + "|".join(_PROSE_UNITS) + r")(?![\w/²µ-])"
)

#: Words that say whose number a sentence is quoting. Recorded, never acted on: a reproduction
#: targets what the paper's *model* produced, and a sentence reporting an experiment is a
#: different thing — but which one a sentence means is a reading, so both are reported with the
#: sentence attached and the curator decides.
_SIMULATED = ("simulat", "model predict", "model shows", "fitted", "predicted")
_MEASURED = ("measured", "experimental", "observed", "reported in the")


#: "Period" in its other sense: a stretch of time rather than an oscillation's. Removed before the
#: vocabulary is matched, because in that sense it names no metric at all. Found in the corpus
#: rather than imagined — "over a simulated 8 hour time period we ran 50 simulations" is a sentence
#: from PMC5026379, and it was proposing a *period* claim on the length of somebody's simulation.
#: A survey counted that paper as the one place text reaches a result a table does not.
_PERIOD_OF_TIME = re.compile(
    r"\b(?:time|study|dosing|sampling|observation|simulation|incubation|washout|treatment)\s+"
    r"period\b|\bperiod\s+of\s+time\b"
)


def _prose_metric(sentence: str) -> str:
    """The metric a sentence names, or ``""`` when it names none or more than one.

    `_metric_for` reads a column *heading*, where the metric is the first word; a sentence has to
    be scanned. Wording counts as naming one only when it is unambiguous — "reach a maximum of"
    and "Cmax" both say a peak — and a sentence naming two ("T1/2 is measured at 0.50h while the
    AUC…") names none, because which one a given number belongs to is exactly the reading this
    module refuses to make.
    """
    lowered = _PERIOD_OF_TIME.sub(" ", sentence.casefold())
    # Quantities this can *recognise*, which is a wider set than the ones it can express. A
    # half-life is not a metric here, and leaving it out of this vocabulary was a real error: the
    # sentence "T1/2 is measured at 0.50h while the AUC simulations show 0.9h" then looked
    # unambiguous, and put `auc` on two half-lives. A term it cannot express still has to make a
    # sentence ambiguous, or the ambiguity check only sees the half of the vocabulary it likes.
    terms = {
        term
        for phrase, term in (
            ("cmax", "cmax"), ("maximum", "cmax"), ("peak", "cmax"),
            ("auc", "auc"), ("area under", "auc"),
            ("t1/2", ""), ("half-life", ""), ("half life", ""),
            ("tmax", "tmax"), ("time of maximal", "tmax"), ("time to peak", "tmax"),
            ("clearance", ""), ("volume of distribution", ""),
            # An oscillation's period became an expressible metric the day this engine could
            # certify one, and a vocabulary that did not know the word read "the period is 24.2 h
            # and the peak reaches 3.1" as unambiguously a *peak* — which is this docstring's own
            # example with a different term in it.
            ("period", "period"), ("oscillation period", "period"),
            # Recognised and deliberately not expressible: the field spells "amplitude" as
            # peak-to-trough and as half of it, so a sentence naming one is ambiguous about which,
            # and "peak-to-trough" contains "peak" — without this it proposed a Cmax.
            ("amplitude", ""), ("peak-to-trough", ""), ("peak to trough", ""),
            # The other five classes' quantities. None is expressible: `metric` says how a number
            # comes off a *time course*, and a decay length, a flux or a basin is not read off one
            # — those claims name their own quantity on their own claim type. They belong here
            # anyway, and for the reason the half-life does: the ambiguity check only sees the half
            # of the vocabulary it knows. "The front reached a peak speed of 2.4 µm/min" names a
            # front speed and contains "peak", so without these the wider unit list would put a
            # `cmax` on a wave speed — a candidate a curator has to know this engine to reject.
            # Matched on the shortest wording that names one, because every one of them resolves
            # to "" and the cost of over-matching is a blank metric — which is this module's own
            # answer wherever a reading is not mechanical. "Peak speed" has to reach the check as a
            # *speed*, and it says "front" and "speed" rather than the phrase "front speed".
            ("decay length", ""), ("wavelength", ""), ("wave length", ""), ("gradient", ""),
            ("front", ""), ("speed", ""), ("velocity", ""),
            ("growth rate", ""), ("doubling time", ""), ("flux", ""), ("yield", ""),
            ("fano factor", ""), ("coefficient of variation", ""), ("basin", ""),
            ("steady state", ""), ("steady-state", ""), ("attractor", ""),
        )
        if phrase in lowered
    }
    return next(iter(terms)) if len(terms) == 1 else ""


def _sentences(text: str) -> list[str]:
    """The text split into sentences, crudely and on purpose.

    A sentence splitter that understood abbreviations would still be wrong often enough to matter,
    and what this needs from a sentence is only that it be short enough to read and long enough to
    carry the number's context. Splitting on terminal punctuation followed by a space does that.
    """
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def propose_parameters(
    tables: Mapping[str, Mapping[str, Any]], *, accession: str | None = None
) -> dict[str, Any]:
    """The same table reading, written into the file `params-check` reads.

    A paper's tables carry its model's **inputs** as well as its results — the metformin paper's
    Table 3 is ten tissue-plasma partition coefficients, and the committed
    `datasets/pkpd_parameters.json` was typed out of it by hand. Nothing mechanical tells an input
    from an output: which is which is a judgment about the paper, the same one
    :func:`propose_claims` refuses to make about a result. So this proposes the same cells in the
    other shape, and says so.

    It is the second half of a bracket. :func:`reprolith.parameters_template` writes the model's
    ids with the values blank; this writes the paper's values with the ids blank. A curator has
    both sides of the pairing in front of them and makes the join, which is the one thing neither
    can do.
    """
    proposed = propose_claims(tables)
    candidates = [
        {
            # The model id this value belongs to is never guessed, for the reason the claim reader
            # gives about outputs: a wrong pairing checks a real number against the wrong element.
            "parameter": "",
            "reported": candidate["reported"],
            "reported_units": candidate["reported_units"],
            "source_location": candidate["source_location"],
            "quantity": candidate["quantity"],
        }
        for candidate in proposed["candidates"]
    ]
    body: dict[str, Any] = {
        "description": (
            "Candidate parameter values read from the tables a paper prints. Nothing here knows "
            "an input from an output — a results table and a parameter table are both numbers in "
            "cells — so delete the ones your model does not carry, then name the model element "
            "each survivor is, which `reprolith params-template` lists for you."
        ),
        "parameters": candidates,
        # Every refusal the reading made, and this file's own closing sentence in place of the
        # claims file's: the two ask a reader for different judgments about the same cells.
        "notes": [
            *(note for note in proposed["notes"] if note != _PICK_YOUR_OWN),
            "Which of these your model carries as an input is your judgment, and the pairing to a "
            "model id is never proposed: a wrong pairing checks a real number against the wrong "
            "element, which is worse than no candidate at all.",
        ],
    }
    if accession is not None:
        return {"description": body["description"], "entries": {accession: body}}
    return body


def propose_claims_from_prose(
    text: str, *, accession: str | None = None
) -> dict[str, Any]:
    """Candidate claims for every value the *prose* of a paper states, with its sentence.

    The table reader (:func:`propose_claims`) reaches three papers in ten of this repository's
    open-access subset; the rest put their results in figures, and their text is the only other
    place a number can be read from. This reads it, under the same rule: a candidate is a
    proposal, never a claim.

    It is much noisier than the table reader, and deliberately does not try to be less so. What it
    can do mechanically is attach the evidence: every candidate carries the **whole sentence** it
    came from, so a curator sees at once that "the measured value is 26.1 nmol*h/mL" is the
    experiment and "the simulated value is 91.4 nmol*h/mL" is the model. Which of those a
    reproduction targets is the reading it refuses to make; ``attribution`` records which words
    were present and nothing more.

    A number with no unit beside it is not proposed. In prose a bare number is a figure reference,
    a citation, a year, or a count far more often than it is a result, and admitting them buries
    the ones that are.
    """
    candidates: list[dict[str, Any]] = []
    notes: list[str] = []
    seen: set[tuple[float, str, int]] = set()

    for index, sentence in enumerate(_sentences(text)):
        lowered = sentence.casefold()
        simulated = any(word in lowered for word in _SIMULATED)
        measured = any(word in lowered for word in _MEASURED)
        attribution = (
            "both" if simulated and measured
            else "simulated" if simulated
            else "measured" if measured
            else "unattributed"
        )
        for match in _PROSE_VALUE.finditer(sentence):
            value = _to_float(match.group(1))
            unit = match.group(2)
            key = (value, unit, index)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "claim_id": f"prose-s{index}-{len(candidates)}",
                "quantity": f"{unit} value stated in the text",
                # Never proposed, for the reason the table reader gives: which model output a
                # sentence names is a judgement, and a wrong one checks a real number against the
                # wrong element.
                "species": "",
                "reported": value,
                # One vocabulary with the table reader and with `check_claim_units`: two producers
                # of the same record calling the paper's unit two different names is a seam a
                # curator falls into once and never sees.
                "reported_units": unit,
                "source_location": sentence if len(sentence) <= 300 else sentence[:297] + "…",
                "metric": _prose_metric(sentence),
                "attribution": attribution,
                "parameter_overrides": {},
            })
    if not candidates:
        notes.append(
            "no sentence states a number with a unit beside it, so nothing was proposed; a bare "
            "number in prose is a figure reference or a citation far more often than a result"
        )
    notes.append(
        "These are candidates, not claims, and prose is noisier than a table: a sentence may be "
        "quoting an experiment rather than the model. Each candidate carries its whole sentence "
        "and, in 'attribution', which words were present — read it before promoting one."
    )
    body: dict[str, Any] = {
        "description": (
            "Candidate claims read from the running text of a paper. Delete the ones that are not "
            "results your model should reproduce — many will be measurements, or values quoted "
            "from other work — then name the model output each survivor reads."
        ),
        "candidates": candidates,
        "notes": notes,
    }
    if accession is not None:
        return {"description": body["description"], "entries": {accession: body}}
    return body


__all__ = ["propose_claims", "propose_claims_from_prose", "propose_parameters"]
