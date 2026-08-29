"""What the committed survey says, and that it still adds up.

`propose_claims` reads candidate claims out of a paper's tables. The survey measures how far that
gets on the seeded PK/PD set — and the number that matters is small: of the eight open-access
papers it can reach, **one** prints a reported model output in a table. The rest print parameter
sets, study overviews and diagnostics, and their results live in figures.

That is the figure boundary this repository's findings note describes, measured rather than
asserted. It is also the reason a table reader alone does not close the claim gap.

Reads only the committed file, so it runs in the dependency-free core gate. Regenerate with
`scripts/survey_manuscript_tables.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

_SURVEY = json.loads(
    (Path(__file__).parent.parent / "datasets" / "manuscripts" / "table_survey.json")
    .read_text(encoding="utf-8")
)
_ENTRIES = _SURVEY["entries"]
_PAPERS = _SURVEY["papers"]


def test_the_survey_covers_the_whole_seeded_set() -> None:
    """A survey of a subset, silently, is how a rate gets reported over the wrong denominator."""
    seeded = json.loads(
        (Path(__file__).parent.parent / "datasets" / "pkpd_test_set.json").read_text(
            encoding="utf-8"
        )
    )["entries"]
    assert [e["accession"] for e in _ENTRIES] == [e["accession"] for e in seeded]


def test_the_counts_partition() -> None:
    """Open access implies a PMC id implies a paper that was actually read."""
    open_access = [e for e in _ENTRIES if e["open_access"]]
    assert all(e["pmcid"] and e["pubmed_id"] for e in open_access)
    assert {e["pmcid"] for e in open_access} == set(_PAPERS)


def test_one_of_the_reachable_papers_prints_a_results_table() -> None:
    """The measurement the whole survey exists for, and it is a small number."""
    with_results = {
        pmcid
        for pmcid, paper in _PAPERS.items()
        if any(t["candidates_stating_a_metric"] for t in paper["tables"])
    }
    assert len(with_results) == 1, sorted(with_results)
    (only,) = with_results
    (results_table,) = [
        t for t in _PAPERS[only]["tables"] if t["candidates_stating_a_metric"]
    ]
    assert "pharmacokinetic parameters" in results_table["caption"].casefold()


def test_the_other_papers_numeric_tables_are_inputs_not_outputs() -> None:
    """Not "no numbers" — a parameter table is full of them, and none is a result to reproduce."""
    others = {
        pmcid: paper
        for pmcid, paper in _PAPERS.items()
        if not any(t["candidates_stating_a_metric"] for t in paper["tables"])
    }
    assert len(others) == 7
    # They are not empty: the point is that their numbers are inputs and diagnostics.
    assert sum(t["candidates"] for p in others.values() for t in p["tables"]) > 100


def test_the_survey_states_the_limits_of_its_own_denominator() -> None:
    """Seven entries carry no PubMed id at all — including the one entry that has claims.

    A reachability figure that did not say so would read as a census of the literature rather than
    of one repository's cross-references.
    """
    assert len([e for e in _ENTRIES if not e["pubmed_id"]]) == 7
    unreachable = {e["accession"] for e in _ENTRIES if not e["pubmed_id"]}
    assert "BIOMD0000001028" in unreachable  # the metformin entry, whose paper is open access
    limits = " ".join(_SURVEY["limits"]).casefold()
    assert "floor" in limits and "not a census" in limits
