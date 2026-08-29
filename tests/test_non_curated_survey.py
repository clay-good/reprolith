"""The committed measurement of the *other* half of a certificate: does the entry's model run?

`table_survey.json` measures whether an entry's paper states a result that can be read.
`non_curated_survey.json` measures whether its model runs. A certificate needs both, and the reason
this file exists is what happens when the two are joined: across all nine non-curated SBML entries
they are **disjoint**. The one whose paper prints a results table is the one that does not run, and
of the five that run, four have no paper this repository can read and the fifth prints no results
table.

So "entries whose models run" was never the lift the roadmap carried it as — five of nine already
do. Dependency-free: it reads what the survey script committed, and regenerating that needs the
network and the engine.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATASETS = Path(__file__).parent.parent / "datasets"
_SURVEY = json.loads((_DATASETS / "non_curated_survey.json").read_text(encoding="utf-8"))
_TABLES = json.loads((_DATASETS / "manuscripts" / "table_survey.json").read_text(encoding="utf-8"))


def _has_a_results_table(pmcid: str) -> bool:
    paper = _TABLES["papers"].get(pmcid)
    return bool(paper) and any(
        table["candidates_stating_a_metric"] > 0 for table in paper["tables"]
    )


def test_the_survey_covers_every_non_curated_sbml_entry() -> None:
    """Derived from the entry list, not hard-coded: a survey of a subset chosen by hand would
    answer the roadmap's question about whichever entries were convenient."""
    expected = {
        entry["accession"]
        for entry in _TABLES["entries"]
        if entry["curation"] != "CURATED" and entry["model_format"] == "SBML"
    }
    assert {entry["accession"] for entry in _SURVEY["entries"]} == expected
    assert expected, "the seeded set must contain non-curated SBML entries"


def test_the_headline_count_is_the_one_the_entries_support() -> None:
    counted = sum(1 for e in _SURVEY["entries"] if e.get("completes_a_course"))
    assert _SURVEY["models_that_complete_a_course"] == counted
    assert counted > 0, "if nothing ran, the conclusion below would be about the probe"


def test_a_model_that_completes_records_how_far_and_through_what() -> None:
    """A bare boolean would leave a reader unable to tell a model that ran for 0.1 units from one
    that ran for 10,000, and the ladder is the whole reason the negative result is a floor."""
    for entry in _SURVEY["entries"]:
        if entry.get("completes_a_course"):
            assert entry["longest_duration_completed"] > 0
            assert entry["probed_through"]
        else:
            assert entry["longest_duration_completed"] is None
            assert entry["stopped_with"], "a model that did not run must say what stopped it"


def test_no_non_curated_entry_clears_both_conditions_and_they_fail_on_opposite_sides() -> None:
    """The finding. Running and having a readable result are both necessary, and no entry has
    both — the model that has the paper does not run, and the models that run have no paper."""
    by_accession = {entry["accession"]: entry for entry in _TABLES["entries"]}
    runs_with_a_table = []
    runs_without = 0
    has_a_table_but_does_not_run = 0
    for entry in _SURVEY["entries"]:
        pmcid = by_accession[entry["accession"]].get("pmcid") or ""
        table = _has_a_results_table(pmcid)
        if entry.get("completes_a_course") and table:
            runs_with_a_table.append(entry["accession"])
        elif entry.get("completes_a_course"):
            runs_without += 1
        elif table:
            has_a_table_but_does_not_run += 1
    assert runs_with_a_table == [], (
        f"an entry now clears both conditions and should be certified: {runs_with_a_table}"
    )
    assert runs_without > 0 and has_a_table_but_does_not_run > 0, (
        "the finding is that the two conditions fail on opposite sides; if every entry failed the "
        "same way, this file is asserting something it no longer measures"
    )


def test_the_limits_travel_with_the_numbers() -> None:
    """A probe course is not the model's own run, and a reader who takes the count for a
    reproducibility rate has been misled by this file rather than by the models."""
    limits = " ".join(_SURVEY["limits"])
    assert "No claim is reproduced and no verdict is reached." in limits
    assert "floor" in limits
