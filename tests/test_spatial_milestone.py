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
        # A clean `reproduced` on every entry, and each for its own reason. The scalars were never
        # qualified: a gradient's walls are the model rather than a choice this engine made. The
        # three profiles read `partially-reproduced` for a month, for a zero-flux wall Reprolith
        # imposed and their source did not state — while their reference was the free-space
        # Gaussian, which is the solution on a domain with no walls at all. They state that domain
        # now, and it is honoured by measurement rather than by trust: the claim is judged only
        # once this grid's edge rules are shown to bracket free space to within a tenth of the
        # pass tolerance. Both sides say `reproduced`, so a run that could no longer show it reads
        # as a disagreement rather than as a quietly better number.
        assert entry["expected"] == "reproduced", entry["entry"]
        assert entry["actual"] == "reproduced", entry["entry"]
        assert entry["agree"] is True


def test_every_certificate_is_a_reproduced_curve_verdict() -> None:
    for key in _PROFILES:
        content = json.loads((_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8"))
        # Every claim reproduces, and nothing qualifies it: these claims state their domain
        # (`unbounded`), and the run measured that this grid's walls could not have reached the
        # profile. A wall that cannot be detected is not an assumption about the number.
        assert content["overall"] == "reproduced"
        assert [a["verdict"] for a in content["assessments"]] == ["reproduced"]
        assert content["assumptions"] == []
        # The measurement that let the qualification go is on the certificate, not just in a test.
        assert "unbounded domain, verified rather than assumed" in content["assessments"][0]["protocol"]
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
