"""The committed spatial milestone artifact stays consistent (spec: spatial-class).

Dependency-free guard on `scripts/run_spatial_milestone.py`: if the committed agreement report,
certificates, or catalog drift from a full-agreement blind run over the analytically-grounded
diffusion systems, this fails and the artifact must be regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "spatial" / "milestone"
_EXPECTED = {"diffusion_D1", "diffusion_D2", "diffusion_Dhalf"}


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    for entry in report["per_entry"]:
        # `partially-reproduced` on both sides: the profile matches the closed form exactly, and
        # the certificate is still downgraded because this class runs every claim under a zero-flux
        # boundary Reprolith imposes rather than one the paper stated. The label says so too, so a
        # run that dropped the qualification reads as a disagreement, not as a better number.
        assert entry["expected"] == "partially-reproduced"
        assert entry["actual"] == "partially-reproduced"
        assert entry["agree"] is True


def test_every_certificate_is_a_reproduced_curve_verdict() -> None:
    for key in _EXPECTED:
        content = json.loads((_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8"))
        # Every claim reproduces; the certificate is qualified by the class's own boundary
        # assumption, which is load-bearing and named in the certificate.
        assert content["overall"] == "partially-reproduced"
        assert [a["verdict"] for a in content["assessments"]] == ["reproduced"]
        assert [a["id"] for a in content["assumptions"]] == [f"spatial-boundary-{key}-profile"]
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
        # A spatial profile is judged by the shared curve oracle.
        assert content["assessments"][0]["method"] == "curve-normalized-distance"


def test_the_catalog_recorded_every_entry_as_a_certified_spatial_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "spatial"
        assert entry["state"] == "certified"
