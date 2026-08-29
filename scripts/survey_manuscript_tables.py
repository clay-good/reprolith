#!/usr/bin/env python3
"""Measure how much of the test set's claim gap a *table* reader can close.

Thirty of the thirty-one PK/PD entries abstain because nobody has said which of each paper's
results to target, and `propose_claims` reads candidates out of a paper's tables. The question
this answers is how far that gets: of the seeded entries, how many papers can be reached, and how
many of those print a reported model output in a table rather than in a figure.

Dev-only and network-bound, like the `regenerate_*_references.py` scripts. It writes
`datasets/manuscripts/table_survey.json`, which is what the test reads.

    python scripts/survey_manuscript_tables.py

Two limits travel in the output rather than being left for a reader to discover:

* It reaches a paper only through the identifier the model repository records, by PubMed id or by
  DOI. An entry naming no paper at all cannot be reached, and several entries name the *same*
  paper, so the entry count is not a paper count.
* "Has a results table" is read off `propose_claims`: a table whose candidates state a metric
  (Cmax, AUC) is naming quantities a reproduction targets, and a parameter table does not. That
  is a signal, not a proof, and the counts are reported per table so the judgment stays visible.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_manuscript_tables import _grid, _localname, _text  # noqa: E402

sys.path.insert(0, str(REPO / "python"))
from reprolith import propose_claims  # noqa: E402

_BIOMODELS = "https://www.ebi.ac.uk/biomodels/{accession}?format=json"
_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&pageSize=100"
_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed hosts
        return json.loads(response.read().decode("utf-8"))


def _search(term: str, values: list[str]) -> dict[str, dict]:
    """Europe PMC results for a list of identifiers, keyed by both the pmid and the lowercased DOI."""
    if not values:
        return {}
    query = urllib.parse.quote("(" + " OR ".join(term.format(v) for v in values) + ")")
    found: dict[str, dict] = {}
    for result in _get_json(_SEARCH.format(query=query))["resultList"]["result"]:
        if result.get("pmid"):
            found[result["pmid"]] = result
        if result.get("doi"):
            found[result["doi"].casefold()] = result
    return found


def main() -> None:
    entries = json.loads(
        (REPO / "datasets" / "pkpd_test_set.json").read_text(encoding="utf-8")
    )["entries"]

    records = []
    for entry in entries:
        accession = entry["accession"]
        try:
            metadata = _get_json(_BIOMODELS.format(accession=accession))
            link = (metadata.get("publication") or {}).get("link", "")
        except Exception:  # noqa: BLE001 - a repository that will not answer is a data point
            link = ""
        # The repository cross-references a paper by PubMed id *or* by DOI, and reading only the
        # first understates reach: seven entries link by DOI alone, four of them to the one paper
        # this repository has committed claims for. A survey whose denominator depends on which
        # identifier a curator happened to use is measuring the curator, not the literature.
        records.append({
            "accession": accession,
            "pubmed_id": link.rsplit("/", 1)[-1] if "pubmed" in link else "",
            "doi": link.split("/doi/", 1)[-1] if "/doi/" in link else "",
        })

    by_pubmed = _search("EXT_ID:{}", [r["pubmed_id"] for r in records if r["pubmed_id"]])
    by_doi = _search('DOI:"{}"', [r["doi"] for r in records if r["doi"] and not r["pubmed_id"]])
    for record in records:
        result = (
            by_pubmed.get(record["pubmed_id"])
            or by_doi.get((record["doi"] or "").casefold())
            or {}
        )
        record["pmcid"] = result.get("pmcid") or ""
        record["open_access"] = result.get("isOpenAccess") == "Y" and bool(record["pmcid"])

    papers: dict[str, dict] = {}
    for pmcid in sorted({r["pmcid"] for r in records if r["open_access"]}):
        with urllib.request.urlopen(  # noqa: S310 - fixed host
            _FULLTEXT.format(pmcid=pmcid), timeout=60
        ) as response:
            root = ET.fromstring(response.read().decode("utf-8"))
        tables = {}
        for wrap in root.iter():
            if _localname(wrap.tag) != "table-wrap":
                continue
            label = next(
                (_text(x) for x in wrap if _localname(x.tag) == "label"), wrap.get("id", "")
            )
            caption = next((_text(x) for x in wrap if _localname(x.tag) == "caption"), "")
            tables[label] = {"caption": caption, "rows": _grid(wrap)}
        proposed = propose_claims(tables)["candidates"]
        papers[pmcid] = {
            "tables": [
                {
                    "label": label,
                    "caption": table["caption"][:120],
                    "candidates": sum(
                        1 for c in proposed if c["source_location"].split(",")[0] == label
                    ),
                    "candidates_stating_a_metric": sum(
                        1
                        for c in proposed
                        if c["source_location"].split(",")[0] == label and c["metric"]
                    ),
                }
                for label, table in tables.items()
            ],
        }

    out = {
        "description": (
            "How far a table reader gets on the seeded PK/PD set: which entries resolve to an "
            "open-access paper, and which of those papers print a reported model output in a "
            "table rather than a figure. Regenerate with scripts/survey_manuscript_tables.py."
        ),
        "limits": [
            "A paper is reached through the identifier the model repository records, by PubMed "
            "id or by DOI. An entry naming no paper cannot be reached, and several entries name "
            "the same paper, so the entry count is a floor and not a paper count.",
            "'A results table' is read off propose_claims: a table whose candidates state a "
            "metric is naming quantities a reproduction targets. That is a signal, not a proof, "
            "so the per-table counts are kept.",
        ],
        "entries": records,
        "papers": papers,
    }
    path = REPO / "datasets" / "manuscripts" / "table_survey.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reachable = sum(1 for r in records if r["open_access"])
    identified = [r for r in records if r["pubmed_id"] or r["doi"]]
    with_results = sum(
        1
        for paper in papers.values()
        if any(t["candidates_stating_a_metric"] for t in paper["tables"])
    )
    print(f"wrote {path.relative_to(REPO)}")
    print(f"  {len(records)} entries, {len(identified)} naming a paper, {reachable} open access")
    print(f"  {len(papers)} distinct papers; {with_results} print a results table")


if __name__ == "__main__":
    main()
