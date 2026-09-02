"""Whether the corpus's ceiling is a property of the seeded set or of the literature.

`table_survey.json` measures the thirty-one seeded PK/PD entries and finds that a table reader
reaches three papers in ten of the open-access subset, and that the entries clearing both bars are
exactly the four already certified. The honest objection is that somebody chose that set, so the
number may be measuring the choice.

`scripts/survey_candidate_papers.py` asks the same question of the curated models the seeded set
does *not* contain — everything the repository's own search returns for pharmacokinetic and
pharmacodynamic terms. This reads its committed output; the fetching is dev-only, as with every
other survey here.
"""

from __future__ import annotations

import json
from pathlib import Path

_SURVEY = json.loads(
    (Path(__file__).parent.parent / "datasets" / "manuscripts" / "candidate_survey.json")
    .read_text(encoding="utf-8")
)
_ENTRIES = _SURVEY["entries"]


def test_the_survey_reaches_beyond_the_seeded_set() -> None:
    seeded = {
        entry["accession"]
        for entry in json.loads(
            (Path(__file__).parent.parent / "datasets" / "pkpd_test_set.json")
            .read_text(encoding="utf-8")
        )["entries"]
    }
    assert _ENTRIES, "the survey reached no candidate at all"
    assert not {e["accession"] for e in _ENTRIES} & seeded, "these are the entries already seeded"
    assert all(e["accession"].startswith("BIOMD") for e in _ENTRIES), "the curated branch only"


def test_no_candidate_outside_the_seeded_set_is_reachable_either() -> None:
    """The finding, and it is a negative one: the ceiling is not the seeded set's doing.

    Six curated PK/PD models the search returns are not in the test set. Five of them belong to
    papers that are not open access, so nothing here can read a table of theirs at all. The sixth
    is open access and prints ninety-five numbers across two tables, and not one of its column
    headings names a quantity a reproduction targets — a parameter table, not a results table,
    which is the same signal the seeded survey reads.
    """
    assert len(_ENTRIES) == 6
    assert sum(1 for e in _ENTRIES if e["open_access"]) == 1
    (open_access,) = [e for e in _ENTRIES if e["open_access"]]
    assert open_access["candidates"] > 50, "a paper printing nothing would prove nothing"
    assert open_access["metrics"] == []
    assert _SURVEY["reachable"] == []


def test_a_candidate_with_a_results_table_would_be_named() -> None:
    """The check is not written so that it can only pass.

    `reachable` is the list a curator would work from, and it is empty because every candidate's
    metrics list is. A candidate whose table named a metric would appear in both.
    """
    assert all(bool(e["metrics"]) == (e["accession"] in _SURVEY["reachable"]) for e in _ENTRIES)
