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
#: The six curve entries, one per network type.
_CURVES = {
    "BIOMD0000000010", "BIOMD0000000012", "BIOMD0000000051",
    "BIOMD0000000005", "BIOMD0000000021", "BIOMD0000000058",
}
#: The class's second target: the circadian model's period and peak-to-trough, certified against
#: the same libRoadRunner trajectory the curve entries are judged against. It has **no second
#: engine** of its own — the corroboration surface re-runs curves, and re-running one to read a
#: period off it would be this measurement stated twice rather than confirmed — so the corroboration
#: record covers the six curves and this entry is reported as an absence rather than a pass.
_OSCILLATION = {"BIOMD0000000021_oscillation"}
_EXPECTED = _CURVES | _OSCILLATION


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
    for accession in _CURVES:
        content = json.loads(
            (_MILESTONE / "certificates" / f"{accession}.json").read_text(encoding="utf-8")
        )
        assert content["overall"] == "reproduced"
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
        # The curve oracle judged each claim by normalized distance, not a scalar metric.
        assert content["assessments"][0]["method"] == "curve-normalized-distance"


def test_the_oscillation_entry_is_judged_as_a_scalar_and_names_its_grid() -> None:
    """The second target, and the two things that make it evidence rather than a number.

    It is judged by the *scalar* comparison, not the curve one — which is the whole point, since a
    curve distance over a limit cycle is dominated by phase. And each claim's protocol carries how
    far the number moved between the run's grid and twice it, because a period read off a run
    sampled three times per cycle is the grid's answer rather than the model's.
    """
    content = json.loads(
        (_MILESTONE / "certificates" / "BIOMD0000000021_oscillation.json").read_text(
            encoding="utf-8"
        )
    )
    assert content["overall"] == "reproduced"
    assert {a["claim_id"] for a in content["assessments"]} == {
        "BIOMD0000000021-period", "BIOMD0000000021-peak-to-trough"
    }
    for assessment in content["assessments"]:
        assert assessment["method"] == "scalar-relative-error"
        assert "between 200 and 400 samples" in assessment["protocol"]
        assert "reference period and peak-to-trough read off the curve computed by" in (
            assessment["source_location"]
        )


def test_every_entry_is_recorded_engine_independent() -> None:
    corroboration = json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))
    assert set(corroboration) == _CURVES
    for entry in corroboration.values():
        assert entry["engines"] == ["copasi", "roadrunner"]
        assert entry["engine_independent"] is True


def test_the_catalog_recorded_every_entry_as_a_certified_kinetic_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "kinetic"
        assert entry["state"] == "certified"
        assert entry["ground_truth"]["expected"] == "reproduced"
