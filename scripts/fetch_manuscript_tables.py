#!/usr/bin/env python3
"""Re-read the tables a committed claim cites, from the paper's own open-access full text.

The one certificate in this repository that checks a reconstruction against numbers read from a
*paper* rested on two values nobody had checked against the paper since they were written down.
One of them was not in it: the 500 mg plasma Cmax was recorded as 6.2 nmol/mL, and the paper
prints 6.1 — in Table 6, in Table 4's "Fitted" row, and in the sentence of its own Results. Both
claims also cited the wrong place.

This is the dev-only regenerator for `datasets/manuscripts/`, the counterpart of the
`regenerate_*_references.py` scripts: it fetches, and the test that uses its output does not.
Needs the network; the committed JSON is what CI reads.

    python scripts/fetch_manuscript_tables.py

Only open-access full text is fetched, and only the cited rows are stored, with the paper's
license recorded beside them (see `datasets/THIRD-PARTY-NOTICES.md`).
"""

from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "datasets" / "manuscripts"
_EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

#: Which paper, and which of its tables the committed claims cite.
_WANTED = {
    "BIOMD0000001028": {
        "pmcid": "PMC8026019",
        "tables": {"pone.0249594.t004": 8, "pone.0249594.t006": 4},
    }
}


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _grid(wrap: ET.Element) -> list[list[str]]:
    """A table's cells as a rectangular grid, with row and column spans filled in.

    JATS writes a cell that spans rows once, on the row it starts, so reading the cells in
    document order gives ragged rows: the metformin paper's Table 6 has a `Plasma` cell spanning
    three dose rows, and the two rows under it come back one cell short. Aligning a value to a
    column header by position across those rows lands it under the wrong header — which is how a
    reference value ends up being a number the paper prints somewhere else, the defect this whole
    directory exists to catch.

    So the spans are resolved here, once, and what is stored is rectangular.
    """
    grid: list[list[str]] = []
    pending: dict[int, tuple[str, int]] = {}
    for row in wrap.iter():
        if _localname(row.tag) != "tr":
            continue
        cells: list[str] = []
        column = 0
        carried = dict(pending)
        pending = {}
        for cell in row:
            if _localname(cell.tag) not in ("td", "th"):
                continue
            while column in carried:
                value, remaining = carried.pop(column)
                cells.append(value)
                if remaining > 1:
                    pending[column] = (value, remaining - 1)
                column += 1
            value = _text(cell)
            span_rows = int(cell.get("rowspan", "1") or 1)
            span_cols = int(cell.get("colspan", "1") or 1)
            for _ in range(span_cols):
                cells.append(value)
                if span_rows > 1:
                    pending[column] = (value, span_rows - 1)
                column += 1
        while column in carried:
            value, remaining = carried.pop(column)
            cells.append(value)
            if remaining > 1:
                pending[column] = (value, remaining - 1)
            column += 1
        grid.append(cells)
    return grid


def _tables(root: ET.Element, wanted: dict[str, int]) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for wrap in root.iter():
        if _localname(wrap.tag) != "table-wrap" or wrap.get("id") not in wanted:
            continue
        label = next((_text(x) for x in wrap if _localname(x.tag) == "label"), wrap.get("id", ""))
        caption = next((_text(x) for x in wrap if _localname(x.tag) == "caption"), "")
        rows = _grid(wrap)
        found[label] = {"caption": caption, "rows": rows[: wanted[wrap.get("id", "")]]}
    return found


def main() -> None:
    for accession, spec in _WANTED.items():
        path = OUT / f"{accession}_tables.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        url = _EUROPE_PMC.format(pmcid=spec["pmcid"])
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed host
            root = ET.fromstring(response.read().decode("utf-8"))
        record["tables"] = _tables(root, spec["tables"])  # type: ignore[arg-type]
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} — {', '.join(record['tables'])}")


if __name__ == "__main__":
    main()
