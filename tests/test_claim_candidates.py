"""Reading candidate claims out of the tables a paper prints (bootstrap task 2.2).

Thirty of the thirty-one PK/PD entries abstain because nobody has said which of the paper's
results to target. `claims_template` gives the model half of a claims file; this gives the paper
half. The strongest evidence it works is that it independently rediscovers the two claims a human
extracted from this paper by hand — with the same numbers, the same metric, and a source location
naming the row and column rather than a table.

They are candidates, not claims, and the tests below are mostly about what is *not* proposed.

Pure standard library, so this runs in the dependency-free core gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import propose_claims

_TABLES = json.loads(
    (Path(__file__).parent.parent / "datasets" / "manuscripts"
     / "BIOMD0000001028_tables.json").read_text(encoding="utf-8")
)["tables"]


def test_it_rediscovers_the_two_claims_a_human_extracted_by_hand() -> None:
    """The committed claims for this paper, found again from its tables alone."""
    proposed = propose_claims(_TABLES)["candidates"]
    plasma_cmax = {
        c["reported"]: c
        for c in proposed
        if "Table 6" in c["source_location"] and "Tissue Plasma" in c["source_location"]
        and c["metric"] == "cmax"
    }
    assert {6.1, 11.2} <= set(plasma_cmax)
    assert "Dose, mg 500" in plasma_cmax[6.1]["source_location"]
    assert "Dose, mg 1000" in plasma_cmax[11.2]["source_location"]


def test_no_candidate_names_a_model_output() -> None:
    """A wrong match checks a real number against the wrong species — worse than no candidate."""
    proposed = propose_claims(_TABLES)["candidates"]
    assert proposed
    assert all(c["species"] == "" for c in proposed)


def test_a_metric_is_proposed_only_where_the_column_states_one() -> None:
    """A defaulted metric is a claim about the paper that the paper did not make."""
    proposed = propose_claims(_TABLES)["candidates"]
    by_heading = {c["quantity"].split(" (")[0]: c["metric"] for c in proposed}
    assert by_heading["Cmax, nmol/mL"] == "cmax"
    assert by_heading["AUC24, nmol*h/mL"] == "auc"
    assert by_heading["Tmax, h"] == ""  # a time, not a way of reading a trajectory
    # A percentage difference is a comparison between two numbers, not one of them.
    assert by_heading["Cmax measured- fitted, %"] == ""


def test_a_dose_column_is_a_condition_not_a_result() -> None:
    """500 and 1000 are what the row holds at, and no reproduction targets them."""
    proposed = propose_claims(_TABLES)["candidates"]
    assert not [c for c in proposed if c["quantity"].startswith("Dose")]
    assert not [c for c in proposed if c["quantity"].startswith("Study")]


def test_a_ragged_table_is_refused_rather_than_aligned() -> None:
    """Reading cells positionally across a row span puts a value under the wrong header."""
    ragged = {"Table 1": {"rows": [["Tissue", "Dose, mg", "Cmax"], ["Plasma", "500", "6.1"],
                                   ["1000", "11.2"]]}}
    proposed = propose_claims(ragged)
    assert proposed["candidates"] == []
    assert any("not the width of its header" in note for note in proposed["notes"])


def test_a_cell_stating_two_things_is_not_proposed() -> None:
    """"5.7 (2.1)" states a value and something else, and which the column means is not mechanical."""
    tables = {"Table 1": {"rows": [["Tissue", "Cmax"], ["Plasma", "5.7 (2.1)"], ["Liver", "3.2"]]}}
    proposed = propose_claims(tables)["candidates"]
    assert [c["reported"] for c in proposed] == [3.2]


def test_a_table_with_no_data_rows_says_so() -> None:
    proposed = propose_claims({"Table 1": {"rows": [["Tissue", "Cmax"]]}})
    assert proposed["candidates"] == []
    assert any("no data rows" in note for note in proposed["notes"])


def test_every_result_carries_the_warning_that_these_are_not_claims() -> None:
    """The whole shape of the output depends on the reader knowing it must choose."""
    for tables in (_TABLES, {"Table 1": {"rows": [["a", "b"]]}}):
        proposed = propose_claims(tables)
        assert any("candidates, not claims" in note for note in proposed["notes"])


def test_the_accession_form_is_the_shape_a_multi_paper_claims_file_uses() -> None:
    proposed = propose_claims(_TABLES, accession="BIOMD0000001028")
    assert set(proposed["entries"]) == {"BIOMD0000001028"}
    assert proposed["entries"]["BIOMD0000001028"]["candidates"]


def test_a_thousands_separator_is_read_as_one_number() -> None:
    """Table 6 prints '7 235.1' for a kidney AUC; a candidate must not be 7."""
    tables = {"Table 1": {"rows": [["Tissue", "AUC24"], ["Kidney", "7 235.1"]]}}
    (candidate,) = propose_claims(tables)["candidates"]
    assert candidate["reported"] == 7235.1
