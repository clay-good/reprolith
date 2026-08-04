"""The committed generic-kinetic milestone artifact stays consistent (spec task 8.1 analogue).

Dependency-free guard on the walkable result `scripts/run_kinetic_milestone.py` produces: if the
committed agreement report, certificates, or catalog drift from a full-agreement blind run, this
fails and the artifact must be regenerated. Reading JSON needs no extras, so it runs in the core
CI job. (The engine pin recorded in each certificate is the concrete COPASI version, so this guard
checks verdicts and structure, not version-specific numbers.)
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "kinetic" / "milestone"
_EXPECTED = {
    "BIOMD0000000010", "BIOMD0000000012", "BIOMD0000000051",
    "BIOMD0000000005", "BIOMD0000000021", "BIOMD0000000058",
}


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    assert {e["entry"] for e in report["per_entry"]} == _EXPECTED
    for entry in report["per_entry"]:
        assert entry["expected"] == "reproduced" and entry["actual"] == "reproduced"
        assert entry["agree"] is True


def test_every_committed_certificate_is_a_reproduced_curve_verdict() -> None:
    for accession in _EXPECTED:
        content = json.loads(
            (_MILESTONE / "certificates" / f"{accession}.json").read_text(encoding="utf-8")
        )
        assert content["overall"] == "reproduced"
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
        # The curve oracle judged each claim by normalized distance, not a scalar metric.
        assert content["assessments"][0]["method"] == "curve-normalized-distance"


def test_the_catalog_recorded_every_entry_as_a_certified_kinetic_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "kinetic"
        assert entry["state"] == "certified"
        assert entry["ground_truth"]["expected"] == "reproduced"
