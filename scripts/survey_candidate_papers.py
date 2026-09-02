#!/usr/bin/env python3
"""Is the corpus's ceiling a property of the seeded set, or of the literature?

`datasets/manuscripts/table_survey.json` measures the thirty-one *seeded* PK/PD entries and finds
the reach of a table reader: three papers in ten of the open-access subset print a reported model
output in a table, and the four entries clearing both that bar and "ships a curated model" are
exactly the four already certified. The honest objection to that number is that the seeded set was
chosen by somebody, so it may be measuring the choice.

This asks the same question of the entries the seeded set does *not* contain: every model in the
curated branch that the repository's own search returns for pharmacokinetic and pharmacodynamic
terms. For each new candidate it resolves the paper, asks whether it is open access, and — where
it is — reads its tables with the same `propose_claims` the corpus is built on.

Dev-only and network-bound, like the `regenerate_*_references.py` scripts. It writes
`datasets/manuscripts/candidate_survey.json`, which is what the test reads.

    python scripts/survey_candidate_papers.py

Only identifiers and counts are stored: no paper text crosses into this repository from a source
whose licence has not been checked, and a count is not a reproduction of anything.
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
from fetch_manuscript_tables import _grid, _localname  # noqa: E402

sys.path.insert(0, str(REPO / "python"))
from reprolith import propose_claims  # noqa: E402

OUT = REPO / "datasets" / "manuscripts" / "candidate_survey.json"

#: What the repository is asked for. Broad on purpose: a term that missed a whole family would
#: understate the pool this measures, and the curated-branch filter below is what narrows it.
_TERMS = (
    "pharmacokinetic",
    "pharmacodynamic",
    "PBPK",
    "physiologically based pharmacokinetic",
)

_SEARCH = "https://www.ebi.ac.uk/biomodels/search?query={query}&format=json&numResults=100"
_MODEL = "https://www.ebi.ac.uk/biomodels/{accession}?format=json"
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json"
_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"


def _read(url: str, accept: str = "application/json") -> str:
    request = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - fixed hosts
        return response.read().decode("utf-8")


def _candidates(seeded: set[str]) -> dict[str, str]:
    """Curated-branch models the search returns that the seeded set does not already carry."""
    found: dict[str, str] = {}
    for term in _TERMS:
        payload = json.loads(_read(_SEARCH.format(query=urllib.parse.quote(term))))
        for model in payload.get("models", []):
            # The curated branch only: a `MODEL…` accession is the non-curated tail, which the
            # committed non-curated survey already measures and which carries no ground truth.
            if model["id"].startswith("BIOMD") and model["id"] not in seeded:
                found[model["id"]] = model.get("name", "")
    return found


def _paper(accession: str) -> tuple[str, str]:
    metadata = json.loads(_read(_MODEL.format(accession=accession)))
    link = (metadata.get("publication") or {}).get("link", "")
    return (
        link.rsplit("/", 1)[-1] if "pubmed" in link else "",
        link.split("/doi/", 1)[-1] if "/doi/" in link else "",
    )


def _reachable(pubmed_id: str, doi: str) -> dict[str, str]:
    if not pubmed_id and not doi:
        return {}
    query = f"EXT_ID:{pubmed_id}" if pubmed_id else f'DOI:"{doi}"'
    payload = json.loads(_read(_EPMC.format(query=urllib.parse.quote(query))))
    results = payload.get("resultList", {}).get("result") or [{}]
    return results[0]


def _tables_of(pmcid: str) -> dict[str, dict]:
    root = ET.fromstring(_read(_FULLTEXT.format(pmcid=pmcid), "application/xml"))
    tables = {}
    for index, wrap in enumerate(
        (e for e in root.iter() if _localname(e.tag) == "table-wrap"), start=1
    ):
        rows = _grid(wrap)
        if rows:
            tables[f"Table {index}"] = {"caption": "", "rows": rows}
    return tables


def main() -> None:
    seeded = {
        entry["accession"]
        for entry in json.loads(
            (REPO / "datasets" / "pkpd_test_set.json").read_text(encoding="utf-8")
        )["entries"]
    }
    records = []
    for accession, name in sorted(_candidates(seeded).items()):
        pubmed_id, doi = _paper(accession)
        hit = _reachable(pubmed_id, doi)
        record = {
            "accession": accession,
            "name": name,
            "pubmed_id": pubmed_id,
            "doi": doi,
            "pmcid": hit.get("pmcid", ""),
            "open_access": hit.get("isOpenAccess", "N") == "Y",
            "tables": 0,
            "candidates": 0,
            # The metrics a column heading names. Empty means the paper prints numbers in tables
            # and none of them is a quantity a reproduction targets — a parameter table, not a
            # results table, which is the same signal `table_survey.json` reads.
            "metrics": [],
        }
        if record["pmcid"] and record["open_access"]:
            tables = _tables_of(record["pmcid"])
            proposed = propose_claims(tables)["candidates"] if tables else []
            record["tables"] = len(tables)
            record["candidates"] = len(proposed)
            record["metrics"] = sorted({c["metric"] for c in proposed if c["metric"]})
        records.append(record)
        print(f"  {accession}: {record['pmcid'] or 'no PMC'} "
              f"{'open' if record['open_access'] else 'closed'} "
              f"metrics={record['metrics']}")

    reachable = [r for r in records if r["metrics"]]
    OUT.write_text(json.dumps({
        "description": (
            "Curated-branch PK/PD models the BioModels search returns that the seeded test set "
            "does not contain, with whether each one's paper is open access and whether its "
            "tables state a quantity a reproduction targets. Identifiers and counts only."
        ),
        "search_terms": list(_TERMS),
        "entries": records,
        "reachable": [r["accession"] for r in reachable],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} — {len(records)} candidate(s), "
          f"{len(reachable)} with a results table")


if __name__ == "__main__":
    main()
