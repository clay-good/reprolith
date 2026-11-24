"""Three curves crossing each other on one figure, read apart — and put on the model's clock.

Sluka et al. 2016 deposited two models and their paper prints a table of neither. The whole-body
PBPK module was certified against Figure 4, one black line among black data markers
(`tests/test_figure_reading_sluka2016.py`). This is the other deposit, the sub-cellular metabolism
module, and its figure is the other way a model curve is drawn: **three** black lines on white,
crossing twice, with no markers at all. Colour cannot separate them and continuity alone cannot
either — where two lines meet, one stroke is both of them, and a tracer that takes it inherits the
other line's slope and leaves on the wrong branch. They are followed together instead: a stroke two
lines both reach for is read as neither, and the reading interpolates across it.

The second thing this figure needs is a **clock**. It is plotted over forty minutes and the deposit
declares its time in seconds, so the reading and the run are sixty-fold apart until something says
so. The claim states that factor and where it comes from, the certificate prints it, and the test
below shows what it is worth: without it all three curves fail.
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
    in_time_unit,
    interpolation_cost,
    read_digitized_figure,
    time_unit_notes,
    window_faults,
)

_REPO = Path(__file__).resolve().parents[1]
_DATASETS = _REPO / "datasets"
_FIGURE = _DATASETS / "figures" / "Sluka2016_figure6"
_MANIFEST = json.loads((_FIGURE / "manifest.json").read_text(encoding="utf-8"))
_ENTRY = json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))["entries"][
    "BIOMD0000000624"
]
#: The factor every claim on this figure states: minutes to the deposit's seconds.
_TO_SECONDS = 60.0


def _missing(*modules: str) -> bool:
    """Whether any of ``modules`` cannot be imported here, as in CI's job without the extras."""
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError:
            return True
    return False


def _readings() -> dict[str, object]:
    return {
        series.claim_id: series
        for series in read_digitized_figure((_FIGURE / "fig6.json").read_text(encoding="utf-8"))
    }


def test_the_three_readings_cover_the_window_they_are_judged_on() -> None:
    readings = _readings()
    assert sorted(readings) == ["fig6-APAP", "fig6-APAPG", "fig6-APAPS"]
    on_the_clock = [
        in_time_unit(readings[record["claim_id"]], factor=_TO_SECONDS, unit="s")
        for record in _ENTRY["figure_claims"]
    ]
    windows = [(0.0, float(record["duration"])) for record in _ENTRY["figure_claims"]]
    assert not window_faults(on_the_clock, windows)
    # Each line is drawn from its first sample, on the frame edge the ticks are counted from; that
    # is the one point no column can hold, and it is what lets the run be judged from its own start.
    for series in readings.values():
        assert series.points[0][0] == 0.0


def test_the_calibration_lands_on_the_labels_it_did_not_use() -> None:
    """Built from ticks a step apart counted off the frame; the printed far labels are 40 and 0.10.

    Thirty-nine x ticks and nine y ticks are found, the rest hidden under the lines. A step misread,
    or a tick lattice off by one, would put the far end of an axis at 80, at 20, or at 0.09.
    """
    readings = _readings()
    (series,) = {id(s): s for s in readings.values()}.values() if len(readings) == 1 else [
        readings["fig6-APAP"]
    ]
    assert series.x_axis.maximum == pytest.approx(40.0, abs=0.1)
    assert series.y_axis.maximum == pytest.approx(0.10, abs=0.001)
    assert series.x_axis.unit == "min" and series.y_axis.unit == "mmol/L"


def test_the_lines_do_not_swap_where_they_cross() -> None:
    """The failure this figure invites, checked against the picture's own shape and nothing else.

    APAP is consumed and its two conjugates accumulate, so over the window each line runs one way
    and the order at the end is the reverse of the order at the start. A tracer that left a crossing
    on the wrong branch would produce two readings that agree from the crossing on — the symptom
    this asserts the absence of, by requiring the three to be separated at the end by far more than
    a stroke width.
    """
    apap, apapg, apaps = (_readings()[f"fig6-{name}"] for name in ("APAP", "APAPG", "APAPS"))
    assert apap.points[0][1] > apapg.points[0][1] and apap.points[0][1] > apaps.points[0][1]
    assert apapg.points[-1][1] > apaps.points[-1][1] > apap.points[-1][1]
    # Each line is monotone over the window, which a swapped branch is not.
    assert all(b <= a + 1e-4 for (_, a), (_, b) in zip(apap.points, apap.points[1:]))
    for rising in (apapg, apaps):
        assert all(b >= a - 1e-4 for (_, a), (_, b) in zip(rising.points, rising.points[1:]))
    # Two readings that had merged would end within a stroke of each other; these end apart.
    assert apapg.points[-1][1] - apaps.points[-1][1] > 0.01


def test_what_each_reading_costs_is_measured_and_inside_the_budget() -> None:
    """Under 2% of the pass budget each: a dense trace of a smooth curve joins to itself cheaply."""
    for series in _readings().values():
        cost = interpolation_cost(series, window=(0.0, 39.0))
        assert cost["measurable"]
        assert cost["budget_share"] < 0.02


def test_the_claims_state_the_clock_conversion_they_make() -> None:
    """The figure is in minutes and the model in seconds; the factor and its basis are published."""
    curves = figure_claims(_ENTRY["figure_claims"], base_dir=_DATASETS)
    assert len(curves) == 3
    for curve in curves:
        assert curve.reference_kind is ReferenceKind.DIGITIZED_FIGURE
        assert "placed on the run's clock in s by x60" in curve.cited_source
        assert "60 s to the minute" in curve.cited_source


def test_a_conversion_that_does_not_say_what_it_is_is_refused() -> None:
    """A factor with no basis reads on a certificate as a conversion somebody justified."""
    (record,) = _ENTRY["figure_claims"][:1]
    half_stated = {**record, "time_scale": {"factor": 60.0, "unit": "s"}}
    with pytest.raises(ValueError, match="time_scale states no basis"):
        figure_claims([half_stated], base_dir=_DATASETS)


def test_a_time_conversion_cannot_reverse_or_collapse_an_axis() -> None:
    series = _readings()["fig6-APAP"]
    for factor in (0.0, -60.0, float("inf")):
        with pytest.raises(ValueError, match="positive factor"):
            in_time_unit(series, factor=factor, unit="s")
    converted = in_time_unit(series, factor=_TO_SECONDS, unit="s")
    assert converted.x_axis.unit == "s"
    assert converted.x_axis.maximum == pytest.approx(series.x_axis.maximum * _TO_SECONDS)
    # The curve is untouched: only the axis it is read against moves.
    assert [y for _, y in converted.points] == [y for _, y in series.points]


def test_the_models_own_clock_is_read_and_the_disagreement_reported() -> None:
    """The deposit states seconds the Level 2 way — by redefining `time` — and the figure is in minutes.

    This is the check that would have caught the mistake the conversion exists to prevent, and until
    this entry it could not fire on any Level 2 model: it read only the `timeUnits` attribute, which
    Level 2 does not have.
    """
    sbml = (_DATASETS / _ENTRY["model_file"]).read_text(encoding="utf-8")
    readings = list(_readings().values())
    notes = time_unit_notes(readings, sbml, carrier="this deposit")
    assert len(notes) == 3
    assert "x axis in min" in notes[0] and "states its time in second" in notes[0]
    # The second is a sixtieth of the minute the figure is drawn in, which is the ratio the
    # note reports and the reciprocal of the factor the claim states.
    assert "0.0166667 times as large" in notes[0]
    # Converted, there is nothing to report.
    assert time_unit_notes(
        [in_time_unit(series, factor=_TO_SECONDS, unit="s") for series in readings], sbml
    ) == ()


def test_the_published_certificate_is_a_clean_pass_marked_as_a_figure_reading() -> None:
    certificate = json.loads(
        (_DATASETS / "milestone" / "certificates" / "BIOMD0000000624.json").read_text(
            encoding="utf-8"
        )
    )
    assert certificate["overall"] == "reproduced"
    assert not certificate["assumptions"]
    assert len(certificate["assessments"]) == 3
    for assessment in certificate["assessments"]:
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
    regenerated = json.loads((copy / "fig6.json").read_text(encoding="utf-8"))
    assert regenerated == json.loads((_FIGURE / "fig6.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(
    _missing("PIL", "numpy"),
    reason="the digitizer needs Pillow and numpy, which the package does not depend on",
)
def test_a_threshold_that_would_swallow_the_ticks_is_refused(tmp_path: Path) -> None:
    """The thinnest line here never reaches the ink a thick one is read at, so the panel states its
    own threshold — and a threshold low enough to catch the axis ticks would hand a trace near the
    foot of the frame a lattice of short strokes to follow. The separation is measured, not assumed.
    """
    copy = tmp_path / "figure"
    copy.mkdir()
    (copy / _MANIFEST["image"]).write_bytes((_FIGURE / _MANIFEST["image"]).read_bytes())
    manifest = json.loads(json.dumps(_MANIFEST))
    manifest["panels"][0]["line_ink"] = 0.4  # below the grey the ticks are drawn in
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "digitize_figure_panels.py"),
         str(copy / "manifest.json")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "a trace can follow a tick" in result.stderr


@pytest.mark.skipif(
    _missing("COPASI", "libsbml"),
    reason="the optional 'engine' extra (python-copasi, python-libsbml) is not installed",
)
def test_the_verdict_is_not_vacuous() -> None:
    """All three pass as published, and all three fail with the figure's minutes left unconverted.

    Which is the whole of what the clock conversion buys: the window check cannot see this, because
    0-39 is covered by a reading that runs 0-40, and every value lands in the wrong place.
    """
    from reprolith import PaperIdentity, certify_curves, engine_pin

    sbml = (_DATASETS / _ENTRY["model_file"]).read_text(encoding="utf-8")
    paper = PaperIdentity(**_ENTRY["paper"])

    def verdicts(records: list[dict]) -> list[Verdict]:
        claims = figure_claims(records, base_dir=_DATASETS)
        return [
            assessment.verdict
            for assessment in certify_curves(
                sbml, paper=paper, engine_pin=engine_pin(), claims=claims
            ).assessments
        ]

    assert verdicts(_ENTRY["figure_claims"]) == [Verdict.REPRODUCED] * 3
    unconverted = [
        {key: value for key, value in record.items() if key != "time_scale"}
        | {"duration": 39.0}
        for record in _ENTRY["figure_claims"]
    ]
    assert verdicts(unconverted) == [Verdict.FAILED] * 3


def test_a_reading_in_another_unit_is_not_reported_as_a_short_one() -> None:
    """The hole the clock conversion opened, and the check that was on the wrong side of it.

    `figure-check` runs before any claim exists, so it cannot know a claim will state a factor. It
    compares the reading's span against the document's run as numbers — and against a run in
    seconds a perfectly good reading in minutes looks far too narrow. Told it is short, a curator
    goes back and re-reads a figure that was already right. Where the model says the two files are
    in different units, the shortfall is not a shortfall: it is the unit question, and the message
    is the conversion rather than the reading.
    """
    readings = list(_readings().values())
    run = [(0.0, float(_ENTRY["duration"]))]
    blamed = window_faults(readings, run, carrier="your document")
    assert blamed and all("needs values outside what was read" in fault for fault in blamed)

    excused = window_faults(
        readings, run, carrier="your document",
        unconvertible={reading.claim_id for reading in readings},
    )
    assert len(excused) == len(blamed)
    for fault in excused:
        assert "in another unit" in fault and "state the conversion on the claim" in fault
        assert "needs values outside what was read" not in fault
    # And it is still reported: a curator who does nothing has a claim that cannot be judged.
    assert excused


def test_converting_a_log_axis_moves_the_axis_and_not_which_points_join() -> None:
    """The claim `in_time_unit` makes about a log10 x axis, checked rather than asserted.

    A positive factor is a constant shift in log space, so the joins a reading is interpolated
    along are the same ones before and after. If it were not true, a conversion would quietly
    re-shape every reference read off a log axis — the axis figures in this field are most often
    drawn on.
    """
    from reprolith import Axis, AxisScale, DigitizedSeries, resample_series

    series = DigitizedSeries(
        claim_id="c", figure="Figure 1", curve="plasma", digitizer="WebPlotDigitizer 4.7",
        x_axis=Axis(minimum=0.1, maximum=100.0, unit="min", scale=AxisScale.LOG10),
        y_axis=Axis(minimum=0.0, maximum=10.0, unit="mg/L"),
        points=((0.1, 1.0), (1.0, 5.0), (10.0, 3.0), (100.0, 0.5)),
    )
    converted = in_time_unit(series, factor=_TO_SECONDS, unit="s")
    assert converted.x_axis.scale is AxisScale.LOG10
    # Sampled at the same places in the curve's own coordinates, the values are identical.
    before = resample_series(series, [0.2, 2.0, 20.0, 50.0])
    after = resample_series(converted, [x * _TO_SECONDS for x in (0.2, 2.0, 20.0, 50.0)])
    assert after == pytest.approx(before)
