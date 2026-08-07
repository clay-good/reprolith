"""The committed logical milestone artifact stays consistent (roadmap #9).

Dependency-free guard on the walkable result `scripts/run_logical_milestone.py` produces: if the
committed agreement report, certificates, or catalog drift from a full-agreement blind run over the
four CANA-validated published Boolean models, this fails and the artifact must be regenerated.
Reading JSON needs no extras, so it runs in the core CI job. (The non-circular reproduction of the
attractor counts themselves is checked in test_logical_cross_validation.py; this guards the catalog
and agreement-report integration — the fourth class flowing through the shared contracts.)
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "logical" / "milestone"
_EXPECTED = {"thaliana", "drosophila", "budding_yeast", "marques_pita"}


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    assert {e["entry"] for e in report["per_entry"]} == _EXPECTED
    for entry in report["per_entry"]:
        assert entry["expected"] == "reproduced" and entry["actual"] == "reproduced"
        assert entry["agree"] is True


def test_every_committed_certificate_is_a_reproduced_attractor_verdict() -> None:
    for key in _EXPECTED:
        content = json.loads(
            (_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8")
        )
        assert content["overall"] == "reproduced"
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
        # Judged by the discrete attractor oracle, not a curve or scalar metric.
        assert content["assessments"][0]["method"] == "attractor-set-match"


def test_the_catalog_recorded_every_entry_as_a_certified_logical_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "logical"
        assert entry["state"] == "certified"
        assert entry["ground_truth"]["expected"] == "reproduced"
