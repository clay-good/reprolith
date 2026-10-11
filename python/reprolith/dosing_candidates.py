"""Candidate dosing statements read out of a paper's running text (spec: ``paper-ingestion``).

A dossier's dosing protocol is the one element a deposited model routinely does not carry: the
file holds a default dose, and the doses the paper's results were produced at are in its text. The
metformin worked example found them by reading, and so did every claim that names a dose since.
This reads them, under the rule the claim readers hold (:mod:`reprolith.claim_candidates`): a
candidate is a proposal with the whole sentence attached, never a protocol.

What it will not do is as much the point as what it does. It does not say which model parameter
a dose sets, convert a salt to its free base, turn "375 mg twelve hours earlier" into a schedule,
or supply a dose a paper leaves out — an absent dose is an absence in the output, which is the gap
a reconstruction has to record rather than close.
"""

from __future__ import annotations

import re
from typing import Any

from .claim_candidates import _MEASURED, _SIMULATED, _sentences

#: The units a *dose* wears: an amount of substance or mass, alone or per kilogram of body weight.
#: A concentration is not one — "840 nmol/mL for a 500mg dose" states one dose, and the lookahead
#: below is what keeps "nmol/mL" from being read as an amount in nmol.
_UNIT = r"(?:mg|µg|μg|ug|ng|g|nmol|µmol|μmol|mmol|IU)(?:/[kK]g)?"
_NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?"
_AMOUNT = re.compile(r"(?<![\w.,/])(" + _NUMBER + r")\s?(" + _UNIT + r")(?![\w/])")

#: What may stand between two members of one list or range of doses, and nothing else may.
_LIST = r"\s*(?:,\s*(?:and|or)\s+|,\s*|\s+and\s+|\s+or\s+)\s*"
_RANGE = r"\s*(?:[–—-]|\s+to\s+|\s+up\s+to\s+)\s*"
#: Bare numbers leading up to a unit-bearing one, which lend them its unit: "0.5, 1.0, and 2.0
#: mg/kg" is three doses and "0.1–40 mg" is one range, and reading only the number beside the unit
#: would report the last of the three and the top of the range as the whole of what was said.
_LEADING = re.compile(r"((?:" + _NUMBER + r"(?:" + _LIST + r"|" + _RANGE + r"))+)$")
_LEAD_ITEM = re.compile(r"(" + _NUMBER + r")(" + _LIST + r"|" + _RANGE + r")")

#: Words that make the amount beside them a dose. A mass in a paper is as often what was excreted,
#: what a compartment holds, or what an assay detects, and a reader that proposed every one would
#: bury the doses — so the amount has to sit *next to* one of these, on the side shown.
_BEFORE = re.compile(
    r"\b(?:dos(?:e|es|ed|ing)|pre-dose|administ\w+|application|applied|bolus|inject\w+|infus\w+)\b"
    r"([^\d.;]{0,30})$",
    re.IGNORECASE,
)
_AFTER = re.compile(
    r"^([^\d.;,()]{0,30}?)(?:\b(?:dos(?:e|es|ing)|pre-dose|bolus|oral\w*|peroral\w*|PO|IV|"
    r"intravenous\w*|subcutaneous\w*|intraperitoneal\w*|intramuscular\w*|inject\w+|infus\w+|"
    r"daily|(?:once|twice)\s+a\s+day|times\s+(?:a|per)\s+day|per\s+day)\b|"
    r"i\.v\.|p\.o\.|q\.d\.|b\.i\.d\.|t\.i\.d\.|q\.i\.d\.)",
    re.IGNORECASE,
)
#: A number that is a reference or a year rather than a quantity, read by what stands before it.
#: Both reach a dose word the same way a dose does — "Figure 2g dose–response", "in 2019, 10 mg
#: doses" — and a list that lends its unit backwards would hand a year a unit of milligrams.
_REFERENCE = re.compile(r"\b(?:Fig(?:ure|s|ures|\.)?|Tables?|Sections?|Eqs?\.?|Refs?\.?)\s*$", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:in|since|during|until|by|from)\s+$", re.IGNORECASE)
_SHARE_OF = re.compile(r"%\s+of\s+(?:the\s+)?$")
#: A dose stated as a limit rather than as a dose: "doses >250 mg", "if the dose exceeds 100 mg".
#: The amount is real and the model was not run at it, so the candidate says which side it bounds.
_BOUND = re.compile(
    r"(?:(?P<above>[>≥]|\b(?:exceeds?|exceeding|above|over|(?:higher|greater|more)\s+than))|"
    r"(?P<below>[<≤]|\b(?:below|under|(?:lower|less)\s+than)))\s*$",
    re.IGNORECASE,
)
#: "i.e.," and "e.g.," carry a comma and two full stops into a gap that is otherwise one phrase.
_ABBREVIATION = re.compile(r"\b(?:i\.e\.|e\.g\.),?", re.IGNORECASE)

#: Routes, each under the one name the candidate reports. Matched on the sentence, and reported
#: only when the sentence names exactly one: "both the intravenous dataset and the peroral dataset"
#: names two, and which dose went by which is the reading this module refuses to make.
_ROUTES = (
    ("oral", re.compile(r"\b(?:oral\w*|peroral\w*|PO|gavage)\b|p\.o\.", re.IGNORECASE)),
    ("intravenous", re.compile(r"\b(?:intravenous\w*|IV)\b|i\.v\.", re.IGNORECASE)),
    ("subcutaneous", re.compile(r"\bsubcutaneous\w*\b|s\.c\.", re.IGNORECASE)),
    ("intraperitoneal", re.compile(r"\bintraperitoneal\w*\b|i\.p\.", re.IGNORECASE)),
    ("intramuscular", re.compile(r"\bintramuscular\w*\b|i\.m\.", re.IGNORECASE)),
)

#: Wording that says *when*, quoted and not interpreted. "One 375mg pre-dose 12 hours before the
#: main dose" is a schedule to a reader and four separate facts to a pattern, so the words are
#: handed over as the paper wrote them and the schedule is the curator's to assemble.
_SCHEDULE = re.compile(
    r"\b(?:single|once|twice|pre-dose|daily|per\s+day|(?:\w+\s+)?times\s+(?:a|per)\s+day|"
    r"every\s+\d+[\s-]?(?:h|hours?|days?|weeks?)\b|every\s+\d+-week|"
    r"\d+\s?(?:h|hours?|days?|weeks?)\s+(?:before|after|earlier|later|apart|interval)|"
    r"Q\d+W|steady[\s-]state)\b|q\.d\.|b\.i\.d\.|t\.i\.d\.|q\.i\.d\.",
    re.IGNORECASE,
)


def _to_float(text: str) -> float:
    return float(text.replace(",", ""))


def _groups(sentence: str, preceding: str = "") -> list[list[dict[str, Any]]]:
    """The amounts in a sentence, gathered into the lists and ranges they were written as.

    Each member is ``{"low", "high", "units", "bound", "start", "end"}`` with ``low == high`` for a single
    value. A group is what one dose word can govern: "a single PO dose of 500mg, 1000mg, and
    1500mg" is three doses under one "dose of", and judging each on its own would keep the first
    and drop the two it was listed with.

    ``preceding`` is the sentence before this one, and is here for one case: the splitter breaks
    after "Fig." and hands over "2g dose–response" as the start of a sentence.
    """
    members: list[dict[str, Any]] = []
    for match in _AMOUNT.finditer(sentence):
        units = match.group(2)
        start = match.start()
        high = _to_float(match.group(1))
        if _REFERENCE.search(sentence[:start] if start else preceding):
            continue
        leading = _LEADING.search(sentence[:start])
        inherited: list[tuple[float, bool, int]] = []
        if (
            leading
            and not re.search(r"[\w.,/]$", sentence[: leading.start()])
            and not _REFERENCE.search(sentence[: leading.start()])
            and not (
                _YEAR.search(sentence[: leading.start()])
                and re.match(r"(?:19|20)\d\d\b", leading.group(1))
            )
        ):
            inherited = [
                (_to_float(item.group(1)), bool(re.fullmatch(_RANGE, item.group(2))),
                 leading.start() + item.start())
                for item in _LEAD_ITEM.finditer(leading.group(1))
            ]
        low = high
        for index, (value, is_range, at) in enumerate(inherited):
            if is_range and index == len(inherited) - 1:
                low, start = value, at
            else:
                members.append({"low": value, "high": value, "units": units, "start": at,
                                "end": at, "bare": True, "bound": ""})
        bound = _BOUND.search(sentence[:start])
        members.append({
            "low": low, "high": high, "units": units, "start": start, "end": match.end(),
            "bound": ("above" if bound.group("above") else "below") if bound else "",
        })
    members.sort(key=lambda member: member["start"])
    # A range written with the unit on both ends — "500 mg up to 3000 mg" — is two amounts to the
    # pattern and one range to the reader. Only in one unit: "2 mg–3 mg/kg" is kept as the two
    # amounts it prints, because a range needs one unit and choosing it would be a reading.
    merged: list[dict[str, Any]] = []
    for member in members:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and not previous.get("bare")
            and previous["low"] == previous["high"]
            and member["low"] == member["high"]
            and previous["units"] == member["units"]
            and re.fullmatch(_RANGE, sentence[previous["end"]: member["start"]])
        ):
            merged[-1] = {**member, "low": previous["low"], "start": previous["start"]}
        else:
            merged.append(member)
    groups: list[list[dict[str, Any]]] = []
    for member in merged:
        previous = groups[-1][-1] if groups else None
        joined = previous is not None and (
            previous.get("bare")
            or re.fullmatch(_LIST + "|" + _RANGE, sentence[previous["end"]: member["start"]])
        )
        if joined:
            groups[-1].append(member)
        else:
            groups.append([member])
    return groups


def _is_a_dose(sentence: str, group: list[dict[str, Any]]) -> bool:
    """Whether a dose word sits beside this group, on the side it is written on."""
    before = _ABBREVIATION.sub(" ", sentence[: group[0]["start"]])
    found = _BEFORE.search(before)
    # "46.3% of the dose (362mg) is excreted" puts an amount straight after "dose", and it is what
    # left the body rather than what went in. Measured on the metformin paper, where it was the one
    # candidate in sixty-seven that was not a dose.
    if found and "," not in found.group(1) and not _SHARE_OF.search(before[: found.start()]):
        return True
    return bool(_AFTER.match(sentence[group[-1]["end"]:]))


def propose_dosing_from_prose(text: str, *, accession: str | None = None) -> dict[str, Any]:
    """Candidate dosing statements for every dose the *prose* of a paper states, with its sentence.

    A candidate is an amount (or a range of amounts, or a limit — ``bound`` says "above" or
    "below" for "doses >250 mg") in the paper's own unit, written beside a word that makes it a dose — "a single PO dose of 500mg", "8 mg/kg intravenous dose", "600 mg
    four times a day". Each carries the whole sentence, the route when the sentence names exactly
    one, the scheduling words the sentence uses verbatim, and whether the sentence speaks of a
    simulation or a measurement.

    Three things it leaves blank on purpose, because each is a reading and a wrong one runs a real
    model at the wrong dose: ``parameter`` (which model input the dose sets), the amount in the
    *model's* unit (a paper doses the salt and a model often takes the free base), and the
    schedule itself. A paper that states no dose yields no candidate and a note that says so —
    which is the gap, not a value.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[float, float, str, str]] = set()
    sentences = _sentences(text)
    for index, sentence in enumerate(sentences):
        preceding = sentences[index - 1] if index else ""
        groups = [
            group for group in _groups(sentence, preceding) if _is_a_dose(sentence, group)
        ]
        if not groups:
            continue
        lowered = sentence.casefold()
        simulated = any(word in lowered for word in _SIMULATED)
        measured = any(word in lowered for word in _MEASURED)
        routes = [name for name, pattern in _ROUTES if pattern.search(sentence)]
        schedule_words: list[str] = []
        for found in _SCHEDULE.finditer(sentence):
            if found.group(0).casefold() not in {word.casefold() for word in schedule_words}:
                schedule_words.append(found.group(0))
        for group in groups:
            for member in group:
                # Keyed on the sentence's words, not its position: a figure legend repeated under
                # four panels is one statement, and four identical candidates are three to delete.
                key = (member["low"], member["high"], member["units"], sentence)
                if key in seen:
                    continue
                seen.add(key)
                is_range = member["low"] != member["high"]
                candidates.append({
                    "dose_id": f"dose-s{index}-{len(candidates)}",
                    "amount": None if is_range else member["high"],
                    "amount_range": [member["low"], member["high"]] if is_range else None,
                    "amount_units": member["units"],
                    "bound": member["bound"],
                    "route": routes[0] if len(routes) == 1 else "",
                    "schedule_words": schedule_words,
                    "source_location": sentence if len(sentence) <= 300 else sentence[:297] + "…",
                    "attribution": (
                        "both" if simulated and measured
                        else "simulated" if simulated
                        else "measured" if measured
                        else "unattributed"
                    ),
                    # Never proposed: which model input a dose sets is a judgement, and a wrong
                    # one doses a real model through the wrong door.
                    "parameter": "",
                })
    notes: list[str] = []
    if not candidates:
        notes.append(
            "no sentence states an amount beside a word that makes it a dose, so nothing was "
            "proposed. If the paper's results were produced at a dose, that dose is not in this "
            "text — a gap to record, not a value to supply"
        )
    notes.append(
        "These are candidates, not a protocol. Each amount is in the paper's unit and may be a "
        "salt where your model takes the free base; 'route' is blank where the sentence names "
        "none or more than one; 'schedule_words' quotes the sentence and assembles nothing. Read "
        "the sentence before you use one."
    )
    body: dict[str, Any] = {
        "description": (
            "Candidate dosing statements read from the running text of a paper. Delete the ones "
            "your results were not produced at — many will be doses quoted from other work, or "
            "the therapeutic range — then name the model input each survivor sets."
        ),
        "candidates": candidates,
        "notes": notes,
    }
    if accession is not None:
        return {"description": body["description"], "entries": {accession: body}}
    return body


__all__ = ["propose_dosing_from_prose"]
