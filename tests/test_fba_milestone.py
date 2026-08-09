"""The committed constraint-based milestone artifact stays consistent (spec task 8.1 analogue).

Dependency-free guard on the walkable result `scripts/run_fba_milestone.py` produces: if the
committed agreement report or catalog drifts from a full-agreement blind run, this fails and the
artifact must be regenerated. Reading JSON needs no extras, so it runs in the core CI job.

The expected entry set is *derived* from the cross-validation reference the milestone is built from
(e_coli_core plus every genome-scale model in `reference_growth.json`), not hardcoded — so adding a
model to the reference without regenerating the committed milestone fails this guard instead of
drifting silently, the exact staleness that once left iJO1366 out of the committed artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

_CB = Path(__file__).parent.parent / "datasets" / "constraint_based"
_MILESTONE = _CB / "milestone"

_REFERENCE_GROWTH = json.loads(
    (_CB / "cross_validation" / "reference_growth.json").read_text(encoding="utf-8")
)
# The milestone seeds e_coli_core (documented literature value) plus every genome-scale model the
# reference labels — so the expected set tracks the reference automatically.
_EXPECTED_ENTRIES = {"e_coli_core", *_REFERENCE_GROWTH["models"]}


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED_ENTRIES)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    assert {e["entry"] for e in report["per_entry"]} == _EXPECTED_ENTRIES
    for entry in report["per_entry"]:
        assert entry["expected"] == "reproduced" and entry["actual"] == "reproduced"
        assert entry["agree"] is True


def test_every_committed_certificate_is_a_reproduced_verdict() -> None:
    for accession in _EXPECTED_ENTRIES:
        content = json.loads(
            (_MILESTONE / "certificates" / f"{accession}.json").read_text(encoding="utf-8")
        )
        assert content["overall"] == "reproduced"
        # The inescapable scope flag travels with every stored certificate.
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_the_catalog_recorded_every_entry_as_certified() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED_ENTRIES)
    for entry in entries:
        assert entry["model_class"] == "constraint-based"
        assert entry["state"] == "certified"
        # The ground-truth label is retained on the durable entry (it is only withheld from the
        # verdict path's blind view, not from the persisted record).
        assert entry["ground_truth"]["expected"] == "reproduced"
