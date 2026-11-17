"""A paper whose results are only a figure: Sluka et al. 2016, Figure 4, read and judged.

The acetaminophen PBPK module (BIOMD0000000619) was one of the entries blocked for want of a claim:
its paper prints no table of what the model does. It plots one curve, Figure 4, over the clinical
data the module was built to match. That curve is read off the published image by the curator's
digitizer in its dark-line mode (`datasets/figures/Sluka2016_figure4/`), because the line and the
data markers are both black: it is followed by continuity, and every marker is blanked so a column
through one is skipped rather than misread.

Two things hold the reading to something other than itself. The calibration is built from the grey
ticks counted up from the frame's 0, and the frame's top edge carries a printed "20" that nothing
in that construction used — so the top of the axis landing on 20 is a check. And the reading is
regenerated from the committed image.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from reprolith import (
    ReferenceKind,
    Verdict,
    figure_claims,
    interpolation_cost,
    read_digitized_figure,
    window_faults,
)

_REPO = Path(__file__).resolve().parents[1]
_DATASETS = _REPO / "datasets"
_FIGURE = _DATASETS / "figures" / "Sluka2016_figure4"
_MANIFEST = json.loads((_FIGURE / "manifest.json").read_text(encoding="utf-8"))
_ENTRY = json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))["entries"][
    "BIOMD0000000619"
]


def _missing(*modules: str) -> bool:
    """Whether any of ``modules`` cannot be imported here, as in CI's job without the extras."""
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError:
            return True
    return False


def _reading():
    (series,) = read_digitized_figure((_FIGURE / "fig4.json").read_text(encoding="utf-8"))
    return series


def test_the_reading_is_accepted_and_covers_the_window_it_is_judged_on() -> None:
    reading = _reading()
    assert reading.claim_id == "fig4-venous-APAP"
    (record,) = _ENTRY["figure_claims"]
    assert not window_faults([reading], [(0.0, float(record["duration"]))])
    # The line leaves the frame corner, which is where its first point is read.
    x0, y0 = reading.points[0]
    assert (x0, y0) == (reading.x_axis.minimum, reading.y_axis.minimum)
    assert len(reading.points) > 1000


def test_the_calibration_lands_on_the_labels_it_did_not_use() -> None:
    """Built from ticks counted up from 0; the frame's printed top label is 20, and it lands there.

    Thirteen of the y axis's ticks are found, the rest hidden under the line. A step misread as
    two units, or a tick lattice off by one, would put the top of the frame at 40 or at 19.
    """
    reading = _reading()
    assert reading.y_axis.maximum == pytest.approx(20.0, abs=0.05)
    assert reading.y_axis.minimum == pytest.approx(0.0, abs=0.1)
    # The x axis runs to the last tick, 24 hours, the paper's own observation window.
    assert reading.x_axis.maximum == pytest.approx(24.0, abs=0.05)


def test_what_the_reading_costs_is_measured_and_inside_the_budget() -> None:
    """41% of the figure band, most of it in the first half hour, where markers hide the line."""
    cost = interpolation_cost(_reading(), window=(0.0, 20.0))
    assert cost["measurable"]
    assert 0.3 < cost["budget_share"] < 0.5


def test_the_claim_states_the_unit_conversion_it_makes() -> None:
    """The figure is in ug/mL and the model in mol/L; the factor and its basis are on the claim."""
    (curve,) = figure_claims(_ENTRY["figure_claims"], base_dir=_DATASETS)
    assert curve.reference_kind is ReferenceKind.DIGITIZED_FIGURE
    assert "converted to mol/L by x6.61376e-06" in curve.cited_source
    assert "APAP_MW of 151.2 g/mol" in curve.cited_source
    reading = _reading()
    # The reference is the reading, converted: its peak in the model's units is ~17 ug/mL's worth.
    assert max(curve.reference) == pytest.approx(max(y for _, y in reading.points) / 151200, rel=0.02)


def test_the_published_certificate_is_a_clean_pass_marked_as_a_figure_reading() -> None:
    certificate = json.loads(
        (_DATASETS / "milestone" / "certificates" / "BIOMD0000000619.json").read_text(
            encoding="utf-8"
        )
    )
    assert certificate["overall"] == "reproduced"
    assert not certificate["assumptions"]
    (assessment,) = certificate["assessments"]
    assert assessment["verdict"] == Verdict.REPRODUCED.value
    assert assessment["reference_kind"] == ReferenceKind.DIGITIZED_FIGURE.value


@pytest.mark.skipif(
    _missing("PIL", "numpy"),
    reason="the digitizer needs Pillow and numpy, which the package does not depend on",
)
def test_the_committed_reading_is_what_the_image_gives(tmp_path: Path) -> None:
    copy = tmp_path / "figure"
    copy.mkdir()
    for name in ("manifest.json", _MANIFEST["image"]):
        (copy / name).write_bytes((_FIGURE / name).read_bytes())
    subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "digitize_figure_panels.py"),
         str(copy / "manifest.json")],
        check=True, capture_output=True,
    )
    regenerated = json.loads((copy / "fig4.json").read_text(encoding="utf-8"))
    assert regenerated == json.loads((_FIGURE / "fig4.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(
    _missing("COPASI", "libsbml"),
    reason="the optional 'engine' extra (python-copasi, python-libsbml) is not installed",
)
def test_the_verdict_is_not_vacuous() -> None:
    """The same reading passes the deposit as published and fails two runs a reproducer could make.

    Twice the dose, and the comparison made without the unit conversion — the figure's ug/mL laid
    against the model's mol/L, which is the arithmetic mistake the stated conversion is there to
    keep visible.
    """
    from dataclasses import replace

    from reprolith import PaperIdentity, certify_curves, engine_pin

    sbml = (_DATASETS / _ENTRY["model_file"]).read_text(encoding="utf-8")
    (curve,) = figure_claims(_ENTRY["figure_claims"], base_dir=_DATASETS)
    unconverted = [
        {key: value for key, value in record.items() if key != "value_scale"}
        for record in _ENTRY["figure_claims"]
    ]
    (raw,) = figure_claims(unconverted, base_dir=_DATASETS)
    paper = PaperIdentity(**_ENTRY["paper"])

    def verdict(claim, model=sbml):
        (assessment,) = certify_curves(
            model, paper=paper, engine_pin=engine_pin(), claims=[claim]
        ).assessments
        return assessment.verdict

    assert verdict(curve) is Verdict.REPRODUCED
    assert verdict(replace(curve, parameter_overrides=(("APAP_Dose_grams", 2.8),))) is not (
        Verdict.REPRODUCED
    )
    assert verdict(raw) is Verdict.FAILED
