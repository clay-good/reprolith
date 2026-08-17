"""The committed logical milestone artifact stays consistent (roadmap #9).

Dependency-free guard on the walkable result `scripts/run_logical_milestone.py` produces: if the
committed agreement report, certificates, or catalog drift from a full-agreement blind run, this
fails and the artifact must be regenerated. The set is the CANA-validated small models (published
fixed-point networks plus two synthetic limit-cycle networks, certified on their full attractor
count) and the large T-LGL leukemia network (certified on its steady-state count via the scalable
SAT path). Reading JSON needs no extras, so it runs in the core CI job. (The non-circular
reproduction of the counts themselves is checked in test_logical_cross_validation.py and
test_logical_scalable.py; this guards the catalog and agreement-report integration.)
"""

from __future__ import annotations

import json
from pathlib import Path

_LOGICAL = Path(__file__).parent.parent / "datasets" / "logical"
_MILESTONE = _LOGICAL / "milestone"

# Derive the expected entries from the references the milestone is built from — the small models in
# reference.json plus the large models in scalable_fixed_points.json — so adding a model to either
# reference without regenerating the milestone fails this guard instead of drifting silently.
_EXPECTED = (
    set(json.loads((_LOGICAL / "cross_validation" / "reference.json").read_text())["models"])
    | set(json.loads(
        (_LOGICAL / "cross_validation" / "scalable_fixed_points.json").read_text()
    )["models"])
)


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
        # Judged by the discrete attractor oracle, not a curve or scalar metric — and named for
        # exactly what the independent reference supports. A small model's reference gives the
        # attractor count and each period (a signature, weaker than a set match); a large model's
        # gives the SHA-256 of the fixed-point set itself, which is a set match. Neither may claim
        # the other's strength, and the tolerance column says which projection was compared rather
        # than printing a zero that reads as an exact match of the whole quantity.
        assessment = content["assessments"][0]
        assert assessment["method"] in ("attractor-signature-match", "attractor-set-match")
        assert assessment["tolerance"].startswith("exact match on ")
        if assessment["method"] == "attractor-set-match":
            assert "fixed-point set" in assessment["tolerance"]
        # The update scheme every number was computed under is on the pin: the same network has
        # different cyclic attractors asynchronously, so a certificate omitting it names a result
        # a third party cannot reproduce.
        assert content["engine_pin"]["algorithm"].startswith("synchronous-update")


def test_the_catalog_recorded_every_entry_as_a_certified_logical_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "logical"
        assert entry["state"] == "certified"
        assert entry["ground_truth"]["expected"] == "reproduced"
