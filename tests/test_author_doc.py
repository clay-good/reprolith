"""The author guide, checked against the thing it documents.

[`docs/author-check.md`](../docs/author-check.md) is written for someone who has never run this
and will copy from it. Three of its claims are mechanical, and each fails invisibly: a command
that was renamed still reads fine, a claims-file schema drifts a field at a time, and the sample
output it shows is the whole reason the page exists.

Pure stdlib for the first two; the last needs the engine extra to read a real model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from reprolith.cli import build_parser

_ROOT = Path(__file__).parent.parent
_DOC = (_ROOT / "docs" / "author-check.md").read_text(encoding="utf-8")
_WORKED = _ROOT / "datasets" / "worked_examples"


def test_every_command_line_the_guide_shows_parses() -> None:
    """Someone copying a line from the guide should not be the one who finds out it moved."""
    parser = build_parser()
    lines = [line.strip() for line in re.findall(r"^reprolith .+$", _DOC, re.MULTILINE)]
    assert lines, "the guide shows no commands; this check would pass vacuously"
    for line in lines:
        parsed = parser.parse_args(line.split()[1:])  # raises SystemExit if the guide is wrong
        assert parsed.command == "archive-check"


def test_the_claims_file_the_guide_shows_is_a_claims_file(tmp_path: Path) -> None:
    """A schema drifts one field at a time, and every field here is required or defaulted."""
    from reprolith.cli import _load_claims

    block = re.search(r"```json\n(.*?)```", _DOC, re.DOTALL)
    assert block is not None, "the guide shows no claims file"
    path = tmp_path / "claims.json"
    path.write_text(block.group(1), encoding="utf-8")
    (claim,) = _load_claims(path, None)
    assert claim.claim_id == "Cmax-1000mg"
    assert claim.parameter_overrides == (("Metformin_Dose_in_Lumen_in_mg", 779.9),)


def test_the_finding_the_guide_prints_is_the_finding_it_produces() -> None:
    """The sample output is the reason the page exists, so it is generated, not remembered."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import Claim, pair_report

    dataset = json.loads((_ROOT / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8"))
    claims = [
        Claim.from_record(record)
        for record in dataset["entries"]["BIOMD0000001028"]["claims"]
    ]
    report = pair_report(
        (_WORKED / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8"),
        (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8"),
        claims=claims,
    )
    (item,) = [item for item in report["fix_list"] if item["kind"] == "manuscript"]
    # The guide wraps the line to fit the page; compare the parts that carry the meaning.
    for fragment in ("Cmax-1000mg", "779.9", "389.92", "389.2, 778.4, 1167.6"):
        assert fragment in item["issue"], fragment
        assert fragment in _DOC, f"the guide no longer shows {fragment}"
