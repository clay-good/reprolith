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


def test_everything_proposed_is_printed_where_it_says_it_is() -> None:
    """The two new tools check each other: 63 candidates, all confirmed against their own tables.

    A proposer that mis-read a cell, mis-numbered a column, or dropped a thousands separator would
    produce a value the cited table does not print — which is exactly what `check_claim_values`
    reports. Running one over the other is a genuine cross-check, not a restatement: they read the
    rows by different code paths and agree on every number.
    """
    from reprolith import check_claim_values, unsupported_claims

    candidates = propose_claims(_TABLES)["candidates"]
    assert len(candidates) > 20
    checks = check_claim_values(candidates, _TABLES)
    assert unsupported_claims(checks) == ()
    assert all(check.found is True for check in checks), [
        c.detail for c in checks if c.found is not True
    ]


_SIDEWAYS = {"Table 1": {"rows": [
    ["Dose", "Parameter", "In vivo", "PBPK"],
    ["i.v. - 0.3 mg", "AUC", "10.2 ± 1.18", "10.4 ± 0.23"],
    ["Oral - 2 mg", "Cmax", "0.44 ± 0.24", "0.34 ± 0.19"],
    ["Oral - 2 mg", "Tmax", "3.8 ± 0.4", "2.5 ± 0.34"],
]}}


def test_a_value_with_a_stated_spread_is_a_candidate_and_keeps_its_spread() -> None:
    """The rule that only bare numbers count was found wrong by running this on a real paper.

    The first paper outside this corpus that it was pointed at prints every result as
    `value ± spread`, and a survey built on the bare-number rule counted its results table as
    holding none — which would have published "no paper in this set reports a reproducible value
    in a table" as a measurement. The sign is unambiguous, unlike parentheses, which may hold a
    range, an interval, or an n.
    """
    proposed = propose_claims(_SIDEWAYS)["candidates"]
    first = next(c for c in proposed if c["reported"] == 10.2)
    assert first["reported_spread"] == 1.18
    assert "reported as 10.2 ± 1.18" in first["source_location"]


def test_a_quantity_named_down_the_side_still_states_its_metric() -> None:
    """AUC and Cmax as row labels, the models across the top — a common results layout."""
    by_value = {c["reported"]: c for c in propose_claims(_SIDEWAYS)["candidates"]}
    assert by_value[10.2]["metric"] == "auc"
    assert by_value[0.44]["metric"] == "cmax"
    assert by_value[3.8]["metric"] == ""  # Tmax is a time, not a way of reading a trajectory
    # And the label that says what the number is travels in the source location.
    assert "Parameter AUC" in by_value[10.2]["source_location"]


def test_a_label_column_is_measured_as_well_as_named() -> None:
    """A "Parameter" column holds no numbers, so it is a label whatever it is called.

    A vocabulary alone would have to anticipate every word a paper uses for the side of its
    table, and measuring alone would make a dose column — whose cells are numbers — a result.
    """
    proposed = propose_claims(_SIDEWAYS)["candidates"]
    assert not [c for c in proposed if c["quantity"].startswith("Parameter")]
    assert not [c for c in proposed if c["quantity"].startswith("Dose")]
    # Every candidate comes from one of the two model columns.
    assert {c["quantity"].split(" (")[0] for c in proposed} == {"In vivo", "PBPK"}


def test_a_row_naming_two_metrics_proposes_neither() -> None:
    """An ambiguous row gets a blank metric, never a guessed one."""
    tables = {"Table 1": {"rows": [
        ["Parameter", "Also", "Value"],
        ["AUC", "Cmax", "1.0"],
    ]}}
    (candidate,) = propose_claims(tables)["candidates"]
    assert candidate["metric"] == ""


def test_a_bare_number_carries_no_spread_field() -> None:
    """Absent, not zero: a paper that stated no spread did not state a spread of nothing."""
    tables = {"Table 1": {"rows": [["Tissue", "Cmax"], ["Plasma", "6.1"]]}}
    (candidate,) = propose_claims(tables)["candidates"]
    assert "reported_spread" not in candidate


def test_prose_finds_the_two_values_the_corpus_committed() -> None:
    """The sentence that states them is the same paper's, and the numbers are the committed ones."""
    from reprolith.claim_candidates import propose_claims_from_prose

    sentence = (
        "The model simulations show that after a single 500mg and 1000mg PO dose metformin "
        "hydrochloride concentrations in plasma reach a maximum of 6.1 nmol/mL (0.79 mg/L) and "
        "11.2 nmol/mL (1.45 mg/L) respectively."
    )
    proposed = propose_claims_from_prose(sentence)["candidates"]
    found = {c["reported"] for c in proposed if c["reported_units"] == "nmol/mL"}
    assert {6.1, 11.2} <= found
    for candidate in proposed:
        assert candidate["species"] == ""            # never guessed, as in the table reader
        assert candidate["attribution"] == "simulated"
        assert candidate["metric"] == "cmax"         # "reach a maximum of"
        assert sentence[:40] in candidate["source_location"]


def test_a_number_with_no_unit_is_not_a_result() -> None:
    """In prose a bare number is a figure reference or a citation far more often than a value."""
    from reprolith.claim_candidates import propose_claims_from_prose

    proposed = propose_claims_from_prose(
        "See Fig 4 and reference 36 for details of the 12 datasets."
    )
    assert proposed["candidates"] == []
    assert any("bare number" in note for note in proposed["notes"])


def test_a_sentence_quoting_an_experiment_is_marked_not_dropped() -> None:
    """Which number a reproduction targets is the reading this refuses to make."""
    from reprolith.claim_candidates import propose_claims_from_prose

    proposed = propose_claims_from_prose(
        "The measured value is 26.1 nmol*h/mL, and the simulated value is 91.4 nmol*h/mL."
    )["candidates"]
    assert {c["reported"] for c in proposed} == {26.1, 91.4}
    # Both words are in the sentence, so neither number is claimed for either side.
    assert {c["attribution"] for c in proposed} == {"both"}


def test_a_quantity_it_cannot_express_still_makes_a_sentence_ambiguous() -> None:
    """The error this was written with: T1/2 was not in the vocabulary, so a sentence naming a
    half-life *and* an AUC looked unambiguous and put `auc` on two half-lives."""
    from reprolith.claim_candidates import propose_claims_from_prose

    proposed = propose_claims_from_prose(
        "T1/2 is measured at 0.50h while the AUC simulations show 0.9h."
    )["candidates"]
    assert proposed
    assert all(c["metric"] == "" for c in proposed)


def test_the_survey_records_that_prose_does_not_reach_what_tables_miss() -> None:
    """The measurement that decides whether prose extraction is worth pursuing for reach.

    Of the ten open-access papers, three state a result in a table. Their *prose* states results
    too — but the seven that have no results table have none in their text either: their numbers
    are in the figures. So reading prose broadens what can be read from a paper already reachable,
    and reaches no new paper.
    """
    import json
    from pathlib import Path

    survey = json.loads(
        (Path(__file__).parent.parent / "datasets" / "manuscripts" / "table_survey.json")
        .read_text(encoding="utf-8")
    )
    papers = survey["papers"]
    with_table = {
        pmcid for pmcid, paper in papers.items()
        if any(t["candidates_stating_a_metric"] for t in paper["tables"])
    }
    with_prose = {
        pmcid for pmcid, paper in papers.items() if paper["prose"]["naming_a_quantity"]
    }
    assert with_prose <= with_table, sorted(with_prose - with_table)
    assert with_prose, "no paper states a result in prose; this check would pass vacuously"
    assert " ".join(survey["limits"]).count("figures") >= 1


def test_a_candidate_carries_the_unit_its_column_heading_names() -> None:
    """A results table says what its numbers are *of*, and the proposal dropped it.

    A candidate without a unit is a bare number a curator has to go back to the paper for — and
    once promoted, it reaches `claims-check --model` with nothing to check the model's own unit
    against, which is the comparison that catches a number judged in the wrong quantity.

    Taken from the heading and then *checked*: the tail is a unit only if the unit reader can read
    it as one, so a "measured − fitted, %" column proposes none. That is right twice over — a
    percentage difference is not one of the values, and a unit this cannot read must not be
    published as one.
    """
    import json

    from reprolith import propose_claims

    repo = Path(__file__).resolve().parents[1]
    committed = json.loads(
        (repo / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8")
    )["entries"]

    for accession in sorted(committed):
        path = repo / "datasets" / "manuscripts" / f"{accession}_tables.json"
        if not path.exists():
            continue
        tables = json.loads(path.read_text(encoding="utf-8"))["tables"]
        proposed = propose_claims(tables)["candidates"]
        assert proposed, accession
        by_metric = {
            (c["metric"], c["reported_units"]) for c in proposed if c["reported_units"]
        }
        # Every metric this paper's committed claims read is offered with the unit that paper's
        # own heading names — the same fact `check_claim_units` checks against the model from the
        # other side. Only the metrics it actually reads: the intravenous entry's table prints no
        # Cmax at all, and the paper says why ("due to the IV curves' decreasing nature, only
        # AUC24 and T1/2 values were calculated").
        for claim in committed[accession]["claims"]:
            metric = claim.get("metric", "cmax")
            expected = "nmol*h/mL" if metric == "auc" else "nmol/mL"
            assert claim["reported_units"] == expected, (accession, claim["claim_id"])
            assert (metric, expected) in by_metric, (accession, metric, sorted(by_metric))

    # A percentage column names no unit this can read, so none is proposed for it.
    percentages = propose_claims({"Table 1": {"caption": "x", "rows": [
        ["Tissue", "Cmax, nmol/mL", "Cmax measured-fitted, %"],
        ["Plasma", "6.1", "-6"],
    ]}})["candidates"]
    assert {c["reported_units"] for c in percentages} == {"nmol/mL", ""}


def test_a_heading_that_separates_its_unit_with_a_period_still_states_its_metric() -> None:
    """One paper, four tables, two punctuation marks.

    Every table of the metformin paper writes `Cmax, nmol/mL` except its Table 1, which writes
    `Cmax. nmol/mL` — and that table is the mouse oral-dose model's, one of the four entries this
    repository certifies. The first token came out `cmax.`, which is in no table of metrics, so
    every candidate proposed from it carried no metric at all while the unit beside it read
    cleanly. A curator would have had to supply by hand the one thing the heading states.
    """
    from reprolith.claim_candidates import _metric_for

    assert _metric_for("Cmax, nmol/mL") == _metric_for("Cmax. nmol/mL") == "cmax"
    assert _metric_for("AUC24. nmol*h/mL") == "auc"
    # Still not a metric: a percentage column is a difference between two numbers, not one of them.
    assert _metric_for("Cmax measured -fitted. %") == ""
