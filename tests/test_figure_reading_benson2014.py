"""Seven curves separated by colour, a legend painted out, and one line that cannot be read.

Benson et al. 2014 plot one thing their FAAH-inhibitor model does: brain CB1 receptor occupancy
after single oral doses, seven doses on one panel, in seven colours, with no measured data on it at
all. It is the third kind of figure this repository has had to read, after a single dark line among
dark markers and three dark lines crossing each other, and the first under a licence more
restrictive than CC BY — the image is redistributed in the publisher's own bytes, unmodified, which
is what CC BY-NC-ND permits.

Two things about it are worth testing beyond "the model reproduces it".

The **legend sits inside the frame**, drawn in the same seven colours as the curves, so every
column under it offered each curve a second place to be and the weighted centre landed between
them. It is painted out before the trace, and what that removed is reported per colour.

The **0.1 mg curve is read and not claimed**, which is not the same as leaving it out. Every pixel
goes to the colour it fits best *among those listed*, so an unlisted line does not leave its ink
alone — it hands it to whichever listed colour fits next, and the neighbouring curves move. Listed,
it absorbs its own; unclaimed, nothing is certified from it.
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
)

_REPO = Path(__file__).resolve().parents[1]
_DATASETS = _REPO / "datasets"
_FIGURE = _DATASETS / "figures" / "Benson2014_figure5"
_MANIFEST = json.loads((_FIGURE / "manifest.json").read_text(encoding="utf-8"))
_ENTRY = json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))["entries"][
    "BIOMD0000000512"
]
#: The dose that is read so its ink is not given away, and never certified.
_UNCLAIMED = "fig5-occupancy-0.1mg"


def _missing(*modules: str) -> bool:
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError:
            return True
    return False


def _readings() -> dict[str, object]:
    return {
        series.claim_id: series
        for series in read_digitized_figure((_FIGURE / "fig5.json").read_text(encoding="utf-8"))
    }


def test_the_unreadable_curve_is_read_and_not_claimed() -> None:
    """Both halves, because either one alone is a different and wrong thing to do.

    Dropped from the manifest, its ink would go to the next-best colour and move its neighbours:
    measured, the 3 mg curve's worst point goes from 0.43 to 0.73 of scale when the black line is
    not listed. Claimed, it would certify a reading that reaches 11% on a curve that never passes
    1.4% — a near-black line cannot be told from the dark edge of a saturated one, and its own
    interpolation cost says so at 185% of the pass budget against 11-90% for the six that are.
    """
    readings = _readings()
    assert _UNCLAIMED in readings, "the black line must still be traced, or its ink is given away"
    claimed = {record["claim_id"] for record in _ENTRY["figure_claims"]}
    assert _UNCLAIMED not in claimed
    assert len(claimed) == 6

    cost = interpolation_cost(readings[_UNCLAIMED], window=(0.0, 330.0))
    assert cost["budget_share"] > 1.0, "the unclaimed reading is supposed to be the expensive one"
    for claim_id in claimed:
        assert interpolation_cost(readings[claim_id], window=(0.0, 330.0))["budget_share"] < 1.0


def test_the_legend_inside_the_frame_is_painted_out_and_says_what_it_removed() -> None:
    (panel,) = _MANIFEST["panels"]
    (region,) = panel["blank"]
    x0, y0, x1, y1 = region
    # It covers the legend and stops above every curve: measured on the image, no saturated pixel
    # sits above row 285 in any column right of the legend's swatches.
    assert (x0, y0) == (525, 0) and y1 <= 285
    # And the curves are read over the full width regardless, which is what says the blank did not
    # eat one: every claimed series still reaches the right-hand end of the axis.
    for series in _readings().values():
        assert max(x for x, _ in series.points) > 330.0


def test_the_claims_state_the_dose_and_the_percent_conversion() -> None:
    curves = figure_claims(_ENTRY["figure_claims"], base_dir=_DATASETS)
    doses = sorted(dict(curve.parameter_overrides)["Dose"] for curve in curves)
    assert doses == [0.3, 1.0, 3.0, 10.0, 20.0, 40.0]
    for curve in curves:
        assert curve.reference_kind is ReferenceKind.DIGITIZED_FIGURE
        assert "converted to fraction by x0.01" in curve.cited_source
        assert "bound fraction" in curve.cited_source


def test_the_published_certificate_reproduces_four_and_partially_two() -> None:
    """The result as it came out, including the two that did not pass.

    Both partials are the steep descent, where the curve falls twenty-three points in a few hours:
    the plateau height and the shape agree and the transition sits a little early or late, so the
    worst *point* crosses the band while the distance over the whole curve is a twentieth of it.
    That is a different fact from a model that reproduces nothing, and the certificate states it
    per claim rather than as a verdict on the paper.
    """
    certificate = json.loads(
        (_DATASETS / "milestone" / "certificates" / "BIOMD0000000512.json").read_text(
            encoding="utf-8"
        )
    )
    assert certificate["overall"] == "partially-reproduced"
    verdicts = {a["claim_id"]: a["verdict"] for a in certificate["assessments"]}
    assert len(verdicts) == 6
    assert sorted(v for v in verdicts.values()) == [
        Verdict.PARTIAL.value, Verdict.PARTIAL.value,
        *([Verdict.REPRODUCED.value] * 4),
    ]
    assert {k for k, v in verdicts.items() if v == Verdict.PARTIAL.value} == {
        "fig5-occupancy-3mg", "fig5-occupancy-20mg",
    }
    for assessment in certificate["assessments"]:
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
    assert json.loads((copy / "fig5.json").read_text(encoding="utf-8")) == json.loads(
        (_FIGURE / "fig5.json").read_text(encoding="utf-8")
    )


@pytest.mark.skipif(
    _missing("COPASI", "libsbml"),
    reason="the optional 'engine' extra (python-copasi, python-libsbml) is not installed",
)
def test_each_curve_is_judged_against_its_own_dose() -> None:
    """The overrides are what separate six claims read off one model, so a swap must be visible."""
    from dataclasses import replace

    from reprolith import PaperIdentity, certify_curves, engine_pin

    sbml = (_DATASETS / _ENTRY["model_file"]).read_text(encoding="utf-8")
    paper = PaperIdentity(**_ENTRY["paper"])
    (lowest,) = [c for c in figure_claims(_ENTRY["figure_claims"], base_dir=_DATASETS)
                 if dict(c.parameter_overrides)["Dose"] == 0.3]

    def verdict(claim):
        (assessment,) = certify_curves(
            sbml, paper=paper, engine_pin=engine_pin(), claims=[claim]
        ).assessments
        return assessment.verdict

    assert verdict(lowest) is Verdict.REPRODUCED
    # The same reading against the highest dose the panel shows is a different curve entirely.
    assert verdict(replace(lowest, parameter_overrides=(("Dose", 40.0),))) is Verdict.FAILED
