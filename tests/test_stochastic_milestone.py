"""The committed stochastic milestone artifact stays consistent (spec: stochastic-class).

Dependency-free guard on `scripts/run_stochastic_milestone.py`: if the committed agreement report,
certificates, or catalog drift from a full-agreement blind run over the analytically-grounded
systems, this fails and the artifact must be regenerated. Reading JSON needs no extras.
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "stochastic" / "milestone"
_EXPECTED = {"immigration_death_10", "immigration_death_4", "reversible_isomerization"}


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    for entry in report["per_entry"]:
        # The claim reproduces, but a stochastic verdict is sampling-qualified, so both the ground
        # truth and the actual verdict are partially-reproduced — and they agree.
        assert entry["expected"] == "partially-reproduced"
        assert entry["actual"] == "partially-reproduced"
        assert entry["agree"] is True


def test_every_certificate_is_a_qualified_stochastic_reproduction() -> None:
    for key in _EXPECTED:
        content = json.loads((_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8"))
        assert content["overall"] == "partially-reproduced"
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
        claim = content["assessments"][0]
        assert claim["verdict"] == "reproduced" and claim["assumption_qualified"] is True
        assert claim["method"] == "scalar-relative-error"


def test_the_catalog_recorded_every_entry_as_a_certified_stochastic_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "stochastic"
        assert entry["state"] == "certified"
