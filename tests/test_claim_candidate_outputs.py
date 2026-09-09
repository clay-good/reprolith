"""Naming the model output a candidate claim reads — suggested, never filled in.

`claims_template` gives a curator the model half of a claims file (the outputs a claim can read,
value blank); `claim_candidates` gives them the paper half (every number the tables print, output
blank). Nothing joined the two, so the curator held two files and matched them by hand — and
matching is the step the whole corpus is blocked behind: `reprolith loop-status` reports 27 entries
blocked on one input, which is a claims file somebody has to write.

The join here refuses to be clever, deliberately. A row label and a model output match when they
are the **same word** up to case and punctuation, against the output's id, its name, or the
compartment it lives in — nothing stemmed, no prefix stripped, no synonyms. "Plasma" does not name
`mPlasmaVenous`, and that silence is the feature: a wrong match checks a real number against the
wrong species, which is worse than no suggestion at all.

The measurement below is what makes it shippable rather than plausible. Run against the four
metformin deposits' committed claims — a file a curator wrote by hand, entirely independently of
this code — it agrees on 22 rows, stays silent on 12, and is wrong on none.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith.claim_candidates import _output_index, propose_claims, suggested_output
from reprolith.claims_template import readable_outputs

_ROOT = Path(__file__).resolve().parents[1]
_CLAIMS = _ROOT / "datasets" / "pkpd_claims.json"

#: The deposit each committed model belongs to. Four models, four papers' worth of claims.
_DEPOSITS = {
    "BIOMD0000001027": "Zake2021_Metformin_Mice_PO.xml",
    "BIOMD0000001028": "Zake2021_metformin_human_single_PO.xml",
    "BIOMD0000001029": "Zake2021_Metformin_Human_multiple_PO_dose.xml",
    "BIOMD0000001039": "Zake2021_Metformin_Mice_IV.xml",
}


def _outputs(model: str) -> list[dict[str, str]]:
    return readable_outputs(
        (_ROOT / "datasets" / "worked_examples" / model).read_text(encoding="utf-8")
    )


def _curated() -> dict[str, dict[str, str]]:
    """Per deposit, the tissue a claim cites and the species its curator chose for it."""
    entries = json.loads(_CLAIMS.read_text(encoding="utf-8"))["entries"]
    curated: dict[str, dict[str, str]] = {}
    for accession in _DEPOSITS:
        rows: dict[str, str] = {}
        for claim in entries[accession]["claims"]:
            location = claim["source_location"]
            if " row" in location:
                rows[location.split(", ")[1].replace(" row", "")] = claim["species"]
        curated[accession] = rows
    return curated


def test_the_suggestion_never_disagrees_with_the_curator_who_wrote_the_claims() -> None:
    """The measurement this rule stands on, against a file written without any knowledge of it.

    Silence is not a failure here and a wrong name is: the curator confirms every suggestion before
    it becomes a claim, so a missing one costs them the lookup they were doing anyway, while a
    wrong one is a name they may accept.
    """
    agreed = silent = 0
    wrong: list[tuple[str, str, str, str]] = []
    for accession, model in _DEPOSITS.items():
        index = _output_index(_outputs(model))
        for tissue, species in _curated()[accession].items():
            suggestion = suggested_output([tissue], index)
            if suggestion == species:
                agreed += 1
            elif suggestion == "":
                silent += 1
            else:
                wrong.append((accession, tissue, species, suggestion))
    assert wrong == []
    # Pinned so a rule that quietly stopped matching is a failure rather than a silent regression
    # to the hand-matching this exists to remove.
    assert (agreed, silent) == (22, 12)


def test_plasma_is_the_silence_the_rule_is_written_for() -> None:
    # The model calls it `mPlasmaVenous` and the paper calls it "Plasma". Every rule that would
    # bridge that — a prefix strip, a substring, a synonym list — would also bridge things that are
    # not the same tissue, and the curator is the one who knows which.
    index = _output_index(_outputs(_DEPOSITS["BIOMD0000001027"]))
    assert suggested_output(["Plasma"], index) == ""
    assert suggested_output(["Liver"], index) == "mLiver"
    # Case and the typography a table adds are not differences; the word is.
    assert suggested_output(["portal vein"], index) == "mPortalVein"
    assert suggested_output(["Portal-Vein"], index) == "mPortalVein"


def test_a_row_naming_two_outputs_names_none() -> None:
    # Two label cells pointing at different outputs is a row this cannot resolve, and picking one
    # would be the guess the whole module refuses.
    index = _output_index(_outputs(_DEPOSITS["BIOMD0000001027"]))
    assert suggested_output(["Liver", "Heart"], index) == ""


def test_the_suggestion_sits_beside_the_field_and_never_in_it() -> None:
    """`species` stays blank, so the loader still refuses a claim nobody confirmed."""
    tables = json.loads(
        (_ROOT / "datasets" / "manuscripts" / "BIOMD0000001027_tables.json").read_text(
            encoding="utf-8"
        )
    )["tables"]
    proposed = propose_claims(tables, outputs=_outputs(_DEPOSITS["BIOMD0000001027"]))
    suggested = [c for c in proposed["candidates"] if c.get("species_suggested")]
    assert suggested, "the metformin tables name tissues this model carries"
    assert all(c["species"] == "" for c in proposed["candidates"])
    assert any("species_suggested" in note for note in proposed["notes"])
    # And with no model there is nothing to suggest from, so no candidate carries the key and no
    # note claims a match was attempted.
    bare = propose_claims(tables)
    assert not any("species_suggested" in c for c in bare["candidates"])
    assert not any("species_suggested" in note for note in bare["notes"])


def test_a_spanned_label_cell_is_not_read_from_the_row_above() -> None:
    """The row-span inference this command refuses everywhere else is refused here too.

    The metformin tables write "Liver" once and leave the cell empty on the Fitted row beneath it —
    which is the row the curator's own claims are read from. Carrying the label down would suggest
    on those rows, and would be the same positional guess that puts a value under the wrong header.
    """
    tables = {
        "Table 9": {
            "rows": [
                ["Tissue", "Type", "Cmax"],
                ["Liver", "Measured", "10.0"],
                ["", "Fitted", "11.0"],
            ]
        }
    }
    outputs = _outputs(_DEPOSITS["BIOMD0000001027"])
    by_id = {c["claim_id"]: c for c in propose_claims(tables, outputs=outputs)["candidates"]}
    assert by_id["Table9-r1c2"]["species_suggested"] == "mLiver"
    assert "species_suggested" not in by_id["Table9-r2c2"]


def test_what_it_volunteers_is_measured_too_not_only_what_it_gets_right() -> None:
    """Precision on the answer key is the wrong place to stop, and the parameter join proved it.

    That key holds only the rows a curator *did* pair, so it says nothing about the rows a suggester
    volunteers where the curator would pair nothing — which is where the parameter version of this
    join died (`Ktp_Liver` offered for the liver's Cmax, on 115 of 169 candidates, at a precision of
    8/8 on the key). This is the second measurement, on the half that shipped.

    Every suggestion the four deposits produce comes off a `Tissue` row and names the species of
    that tissue. There are 8 distinct pairings and each recurs once per metric column, which is
    right rather than redundant: a claim's species does not change with the column it is read from.
    """
    pairs: set[tuple[str, str]] = set()
    volunteered = 0
    for accession, model in _DEPOSITS.items():
        tables = json.loads(
            (_ROOT / "datasets" / "manuscripts" / f"{accession}_tables.json").read_text(
                encoding="utf-8"
            )
        )["tables"]
        for candidate in propose_claims(tables, outputs=_outputs(model))["candidates"]:
            suggestion = candidate.get("species_suggested")
            if not suggestion:
                continue
            volunteered += 1
            label = candidate["source_location"].split(", ")[1]
            pairs.add((label, suggestion))
    # No suggestion comes off a row labelled anything but a tissue: a "Type Measured" row, whose
    # word names no model element, is left alone rather than reached for.
    assert all(label.startswith("Tissue ") for label, _ in pairs)
    # The tissue and the species are the same word, on every pairing offered anywhere.
    assert all(
        label.replace("Tissue ", "").replace(" ", "").lower() == species[1:].lower()
        for label, species in pairs
    )
    assert (len(pairs), volunteered) == (8, 359)
