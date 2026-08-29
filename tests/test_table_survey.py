"""What the committed survey says, and that it still adds up.

`propose_claims` reads candidate claims out of a paper's tables. The survey measures how far that
gets on the seeded PK/PD set — and the number that matters is small: of the ten open-access papers
it can reach, **three** print a reported model output in a table. The rest print parameter sets,
study overviews and diagnostics, and their results live in figures.

One of the three is the paper this repository already has committed claims for, which is the
survey validating itself: pointed at the whole set, its own tooling finds the entry a human
extracted by hand.

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
    assert all(e["pmcid"] and (e["pubmed_id"] or e["doi"]) for e in open_access)
    assert {e["pmcid"] for e in open_access} == set(_PAPERS)


def test_a_paper_is_reached_by_either_identifier_the_repository_records() -> None:
    """Reading only the PubMed link measured which identifier a curator used, not the literature.

    Seven entries cross-reference their paper by DOI alone — four of them the metformin paper,
    which is open access, prints its results in tables, and is the one entry with committed
    claims. The first version of this survey called all seven unreachable and published a
    results-table rate over a denominator that had dropped them.
    """
    by_doi_only = [e for e in _ENTRIES if e["doi"] and not e["pubmed_id"]]
    assert len(by_doi_only) == 7
    assert any(e["open_access"] for e in by_doi_only)
    assert all(e["pubmed_id"] or e["doi"] for e in _ENTRIES)


def _with_results() -> set[str]:
    return {
        pmcid
        for pmcid, paper in _PAPERS.items()
        if any(t["candidates_stating_a_metric"] for t in paper["tables"])
    }


def test_three_of_the_reachable_papers_print_a_results_table() -> None:
    """The measurement the whole survey exists for, and it is a small number."""
    assert len(_PAPERS) == 10
    assert len(_with_results()) == 3, sorted(_with_results())


def test_the_survey_finds_the_paper_whose_claims_are_already_committed() -> None:
    """Its own tooling, pointed at the whole set, reaches the one a human extracted by hand."""
    metformin = next(
        e["pmcid"] for e in _ENTRIES if e["accession"] == "BIOMD0000001028"
    )
    assert metformin in _with_results()
    captions = " ".join(
        t["caption"].casefold()
        for t in _PAPERS[metformin]["tables"]
        if t["candidates_stating_a_metric"]
    )
    assert "metformin pharmacokinetic parameters" in captions


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


def test_the_entries_that_clear_both_blockers_are_the_ones_already_claimed() -> None:
    """A paper stating results is half of what a certificate needs; a runnable model is the other.

    Two of the three papers that state results in tables belong to entries shipping no runnable
    SBML — one an R script, one a non-curated hybrid whose other half is a separate file — so
    extracting their claims would still not produce a certificate. On this set the entries that
    clear both are exactly the four variants of the one paper this repository already has claims
    for, which is why "thirty abstain for want of claims" is not the whole account.
    """
    runnable = {
        e["accession"]
        for e in _ENTRIES
        if e["model_format"] == "SBML" and e["curation"] == "CURATED"
    }
    assert len(runnable) == 21
    clearing_both = {
        e["accession"]
        for e in _ENTRIES
        if e["accession"] in runnable
        and e["open_access"]
        and any(t["candidates_stating_a_metric"] for t in _PAPERS.get(e["pmcid"], {}).get("tables", ()))
    }
    assert clearing_both == {
        "BIOMD0000001027", "BIOMD0000001028", "BIOMD0000001029", "BIOMD0000001039"
    }


def test_the_survey_states_the_limits_of_its_own_denominator() -> None:
    """Entries outnumber papers, so an entry count is not a paper count.

    Four of the thirty-one entries are variants of the same metformin model and cite one paper.
    A rate quoted over entries would count that paper four times.
    """
    reachable = [e for e in _ENTRIES if e["open_access"]]
    assert len(reachable) > len(_PAPERS)  # 17 entries, 10 papers
    limits = " ".join(_SURVEY["limits"]).casefold()
    assert "floor" in limits and "not a paper count" in limits
