"""The committed spatial milestone artifact stays consistent (spec: spatial-class).

Dependency-free guard on `scripts/run_spatial_milestone.py`: if the committed agreement report,
certificates, or catalog drift from a full-agreement blind run over the analytically-grounded
diffusion systems, this fails and the artifact must be regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "spatial" / "milestone"
#: The three profile entries, whose walls are Reprolith's choice, and the two scalar entries, whose
#: model states its own — so this is the one milestone that does not expect a single verdict for
#: everything in it, and the split is what the checks below are about.
_PROFILES = {"diffusion_D1", "diffusion_D2", "diffusion_Dhalf"}
_SCALARS = {"gradient_length", "front_speed"}
_EXPECTED = _PROFILES | _SCALARS


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    for entry in report["per_entry"]:
        # `partially-reproduced` for a profile on both sides: it matches the closed form exactly,
        # and the certificate is still downgraded because a claim that states no wall is run under
        # a zero-flux boundary Reprolith imposes. The label says so too, so a run that dropped the
        # qualification reads as a disagreement, not as a better number.
        #
        # And a clean `reproduced` for the two scalars, which is the counterpart: a gradient's
        # walls are the model rather than a choice, so nothing qualifies it. A class whose every
        # entry read `partially` would invite reading the qualification as a property of the class.
        expected = "reproduced" if entry["entry"] in _SCALARS else "partially-reproduced"
        assert entry["expected"] == expected, entry["entry"]
        assert entry["actual"] == expected, entry["entry"]
        assert entry["agree"] is True


def test_every_certificate_is_a_reproduced_curve_verdict() -> None:
    for key in _PROFILES:
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


def test_the_two_scalar_certificates_are_clean_and_judged_as_scalars() -> None:
    """The evidence the class's own README claim rests on: a decay length and a front speed are
    numbers a paper prints in its text, so unlike a profile they are reachable without a curator
    digitizing a figure — and their certificates are the class's first clean passes, because a
    gradient's walls are the model rather than a wall Reprolith chose in the absence of one."""
    for key in sorted(_SCALARS):
        content = json.loads((_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8"))
        assert content["overall"] == "reproduced", key
        assert [a["verdict"] for a in content["assessments"]] == ["reproduced"], key
        assert content["assumptions"] == [], key
        assert content["assessments"][0]["method"] == "scalar-relative-error", key
        # Every input the number turns on, on the certificate: the run can be re-derived from it.
        assert content["assessments"][0]["protocol"]


def test_the_wavelength_claim_is_deliberately_absent_from_the_blind_run() -> None:
    """Stated where a reader would look for it. Linear stability predicts the fastest-growing mode
    and the saturated nonlinear pattern selects a different one, so there is no independent closed
    form for the quantity a wavelength certificate judges — a blind entry would either score the
    class against the wrong number or check the solver against itself."""
    keys = {path.stem for path in (_MILESTONE / "certificates").glob("*.json")}
    assert keys == _EXPECTED
    script = (Path(__file__).parent.parent / "scripts" / "run_spatial_milestone.py").read_text(
        encoding="utf-8"
    )
    assert "wavelength claim is deliberately **not** here" in script
