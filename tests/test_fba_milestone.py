"""The committed constraint-based milestone artifact stays consistent (spec task 8.1 analogue).

Dependency-free guard on the walkable result `scripts/run_fba_milestone.py` produces: if the
committed agreement report or catalog drifts from a full-agreement blind run, this fails and the
artifact must be regenerated. Reading JSON needs no extras, so it runs in the core CI job.
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "constraint_based" / "milestone"


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == 1
    assert report["agreements"] == 1
    assert report["agreement_rate"] == 1.0
    (entry,) = report["per_entry"]
    assert entry["entry"] == "e_coli_core"
    assert entry["expected"] == "reproduced" and entry["actual"] == "reproduced"
    assert entry["agree"] is True


def test_the_committed_certificate_is_a_reproduced_verdict() -> None:
    content = json.loads(
        (_MILESTONE / "certificates" / "e_coli_core.json").read_text(encoding="utf-8")
    )
    assert content["overall"] == "reproduced"
    # The inescapable scope flag travels with the stored certificate.
    assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_the_catalog_recorded_the_entry_as_certified() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    (entry,) = catalog["entries"]
    assert entry["model_class"] == "constraint-based"
    assert entry["state"] == "certified"
    # The ground-truth label is retained on the durable entry (it is only withheld from the
    # verdict path's blind view, not from the persisted record).
    assert entry["ground_truth"]["expected"] == "reproduced"
