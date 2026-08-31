"""Reading a figure's values in, and refusing the readings that are wrong rather than imprecise.

Every claim in this repository whose values live in a figure abstains, and until now nothing
could give one a value. These are the properties that make a digitized series usable as a
reference: it is recovered on the run's own grid, it is never extrapolated, a mis-calibrated
reading is refused by name, and the widened figure tolerance it must be judged in cannot be
escaped by attaching it.

No published figure is in this corpus, so every series here is generated from a function whose
value at each point is known. That is the same fence the population and estimation engines carry:
the reader is validated against mathematics, not against a paper's picture.
"""

from __future__ import annotations

import json
import math

import pytest
from reprolith import (
    ClaimAssessment,
    DossierClaim,
    ReferenceKind,
    Verdict,
    attach_digitized_values,
    curve_reference,
    judge_curve,
    pairing_faults,
    read_digitized_figure,
    resample_series,
    series_resolution,
    undetermined_shortfall,
)
from reprolith.digitization import Axis, AxisScale, DigitizedSeries


def _figure(points, *, y_axis=None, claim="fig-3a", curve="plasma", figure="Figure 3A") -> str:
    return json.dumps({
        "figure": figure,
        "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": y_axis or {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": claim, "curve": curve, "points": points}],
    })


def _series(points, **kwargs) -> DigitizedSeries:
    return read_digitized_figure(_figure(points, **kwargs))[0]


def test_a_reading_carries_where_it_was_read_and_what_read_it() -> None:
    """A digitized point is a measurement of a picture, and travels as one."""
    series = _series([[0, 0.0], [6, 8.0], [24, 2.0]])
    assert series.claim_id == "fig-3a"
    assert series.source_location == (
        "Figure 3A, plasma (digitized from the figure with WebPlotDigitizer 4.7)"
    )
    assert series.span == (0.0, 24.0)


@pytest.mark.parametrize(
    ("record", "complaint"),
    [
        ({"digitizer": "WebPlotDigitizer 4.7"}, "figure"),
        ({"figure": "Figure 3A"}, "digitizer"),
    ],
)
def test_a_series_with_no_provenance_is_not_read(record: dict, complaint: str) -> None:
    body = dict(record)
    body.update({
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "c", "curve": "plasma", "points": [[0, 1], [1, 2]]}],
    })
    with pytest.raises(ValueError, match=complaint):
        read_digitized_figure(json.dumps(body))


def test_a_point_outside_its_own_axes_is_refused_as_a_calibration_error() -> None:
    """The failure that produces the most confident wrong answer: plausible, smooth, mis-scaled.

    A digitizer maps pixels through two calibration points. Get one wrong and every value comes
    out ordered and smooth and wrong by a constant factor, which no downstream check can see.
    A reading off the top of its own axis is the cheapest evidence that happened.
    """
    with pytest.raises(ValueError, match="outside its own axis"):
        _series([[0, 1.0], [6, 14.0], [24, 2.0]])
    with pytest.raises(ValueError, match="outside its own axis"):
        _series([[0, 1.0], [30, 4.0]])


def test_two_readings_at_one_x_and_a_single_point_are_refused() -> None:
    with pytest.raises(ValueError, match="must increase along the axis"):
        _series([[0, 1.0], [6, 8.0], [6, 2.0]])
    with pytest.raises(ValueError, match="at least two"):
        _series([[3, 1.0]])


def test_an_axis_this_reader_cannot_draw_is_named_rather_than_assumed() -> None:
    with pytest.raises(ValueError, match="probit"):
        _series([[0, 1.0], [6, 2.0]], y_axis={
            "minimum": 0.1, "maximum": 10, "unit": "nmol/mL", "scale": "probit",
        })
    with pytest.raises(ValueError, match="above zero"):
        _series([[1, 1.0], [6, 2.0]], y_axis={
            "minimum": 0.0, "maximum": 10, "unit": "nmol/mL", "scale": "log10",
        })


def test_two_curves_paired_with_one_claim_is_refused() -> None:
    """Which curve a claim reads is the curator's statement, and two of them is not one."""
    body = json.loads(_figure([[0, 1.0], [6, 2.0]]))
    body["series"].append({"claim": "fig-3a", "curve": "liver", "points": [[0, 2.0], [6, 4.0]]})
    with pytest.raises(ValueError, match="more than one curve"):
        read_digitized_figure(json.dumps(body))


def test_resampling_recovers_the_function_the_points_were_read_off() -> None:
    """Densely read points, resampled anywhere inside the span, return the original curve."""
    def concentration(t: float) -> float:
        return 8.0 * (math.exp(-0.12 * t) - math.exp(-0.9 * t))

    series = _series([[i * 0.25, concentration(i * 0.25)] for i in range(97)])
    for t in (1.7, 6.05, 13.3, 23.9):
        assert resample_series(series, [t])[0] == pytest.approx(concentration(t), abs=0.01)
    # Where the curve bends hardest — the absorption limb — the same reading spacing is worth an
    # order of magnitude less, which is the whole reason `series_resolution` reports the gap
    # rather than this module judging it.
    assert resample_series(series, [0.4])[0] == pytest.approx(concentration(0.4), abs=0.05)


def test_a_log_axis_is_interpolated_in_the_scale_it_was_drawn_in() -> None:
    """An exponential decay is a straight line on a log axis, so it is recovered exactly.

    Interpolating it linearly instead is a real error — 9% at the midpoint of a decade-wide gap —
    and it is the shape half of pharmacokinetic figures are plotted in: read as a straight line
    the midpoint of a decade-wide gap comes out 81% high.
    """
    decay = [[t, 4.0 * math.exp(-0.2 * t)] for t in (0.0, 12.0, 24.0)]
    log_axis = {"minimum": 0.01, "maximum": 10, "unit": "nmol/mL", "scale": "log10"}
    on_log = _series(decay, y_axis=log_axis)
    on_linear = _series(decay)

    exact = 4.0 * math.exp(-0.2 * 6.0)
    assert resample_series(on_log, [6.0])[0] == pytest.approx(exact, rel=1e-12)
    assert resample_series(on_linear, [6.0])[0] > 1.8 * exact  # joined as a straight line


def test_nothing_is_extrapolated_past_what_was_read() -> None:
    """Outside the digitized span there is no reference, and the last read value is not one."""
    series = _series([[2, 1.0], [18, 4.0]])
    for outside in (0.0, 1.9, 18.1, 24.0):
        with pytest.raises(ValueError, match="only extrapolation"):
            resample_series(series, [outside])
    assert resample_series(series, [2.0, 10.0, 18.0]) == pytest.approx((1.0, 2.5, 4.0))


def test_the_run_grid_is_derived_from_the_claim_rather_than_by_the_curator() -> None:
    """A curve is judged point against point, so the reference must sit on the run's own grid."""
    series = _series([[i, i * 0.4] for i in range(25)])
    assert curve_reference(series, duration=24.0, steps=4) == pytest.approx((0.0, 2.4, 4.8, 7.2, 9.6))
    assert len(curve_reference(series, duration=24.0, steps=100)) == 101
    # A window the curator did not read over is refused here, not padded to length downstream.
    with pytest.raises(ValueError, match="only extrapolation"):
        curve_reference(_series([[6, 1.0], [18, 2.0]]), duration=24.0, steps=4)


def test_the_widest_gap_is_reported_because_the_reference_there_is_a_straight_line() -> None:
    series = _series([[0, 1.0], [2, 4.0], [24, 2.0]])
    resolution = series_resolution(series)
    assert resolution["points"] == 3
    assert resolution["widest_gap"] == pytest.approx(22.0)
    assert resolution["widest_gap_fraction"] == pytest.approx(22.0 / 24.0)


_CLAIMS = (
    DossierClaim(
        id="fig-3a", quantity="[plasma] curve", conditions="500 mg single dose",
        source_location="Figure 3A, curve 1", reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    ),
    DossierClaim(
        id="fig-3b", quantity="[liver] curve", conditions="500 mg single dose",
        source_location="Figure 3B, curve 1", reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    ),
)


def test_attaching_gives_values_to_the_paired_claim_and_leaves_the_rest_abstaining() -> None:
    """A partial digitization is a partial digitization, not a reason to guess the rest."""
    attached = attach_digitized_values(
        _CLAIMS, [_series([[0, 1.0], [12, 6.0], [24, 2.0]])], times=[0.0, 12.0, 24.0],
    )
    plasma, liver = attached
    assert plasma.reference_data == pytest.approx((1.0, 6.0, 2.0))
    assert plasma.reference_kind is ReferenceKind.DIGITIZED_FIGURE
    assert "digitized from the figure with WebPlotDigitizer 4.7" in plasma.source_location
    assert "Figure 3A, curve 1" in plasma.source_location  # the claim's own citation survives
    assert liver == _CLAIMS[1] and not liver.reference_data


def test_a_reading_cannot_be_recorded_as_a_printed_number() -> None:
    """The band a figure is judged in is three times a printed number's, and is not escapable."""
    numeric = DossierClaim(
        id="fig-3a", quantity="[plasma] curve", conditions="",
        source_location="Figure 3A", reference_kind=ReferenceKind.NUMERIC,
    )
    attached = attach_digitized_values(
        [numeric], [_series([[0, 1.0], [24, 2.0]])], times=[0.0, 24.0],
    )
    assert attached[0].reference_kind is ReferenceKind.DIGITIZED_FIGURE


def test_a_reading_paired_with_nothing_is_a_reading_of_the_wrong_figure() -> None:
    with pytest.raises(ValueError, match="which this dossier does not carry"):
        attach_digitized_values(
            _CLAIMS, [_series([[0, 1.0], [24, 2.0]], claim="fig-7c")], times=[0.0, 24.0],
        )


def test_values_are_never_given_to_a_claim_that_has_them_or_to_one_that_is_not_a_target() -> None:
    """Both are the curator's call through a tracked revision, and neither is silent."""
    shipped = DossierClaim(
        id="fig-3a", quantity="[plasma] curve", conditions="",
        source_location="the archive's own data file", reference_kind=ReferenceKind.NUMERIC,
        reference_data=(1.0, 2.0),
    )
    with pytest.raises(ValueError, match="does not replace numbers the paper shipped"):
        attach_digitized_values([shipped], [_series([[0, 1.0], [24, 2.0]])], times=[0.0, 24.0])

    report = DossierClaim(
        id="fig-3a", quantity="[plasma] curve", conditions="",
        source_location="report 'plasma'", targetable=False,
    )
    with pytest.raises(ValueError, match="never staked"):
        attach_digitized_values([report], [_series([[0, 1.0], [24, 2.0]])], times=[0.0, 24.0])


def test_every_way_the_pairing_is_wrong_is_named_at_once() -> None:
    """One source of truth for the pairing refusals, and it reports all of them.

    These three checks used to be reachable only from `attach_digitized_values`, which is to say
    only from Python: a curator at the terminal wrote the pairing, filled in the reading, and was
    told nothing until somebody else ran the join. `figure-check` asks the same function, so the
    way in and the way out cannot disagree about what a bad pairing is — and a curator fixing one
    id at a time learns nothing about the other two, so none of them stops at the first.
    """
    shipped = DossierClaim(
        id="fig-3b", quantity="[liver] curve", conditions="",
        source_location="the archive's own data file", reference_kind=ReferenceKind.NUMERIC,
        reference_data=(1.0, 2.0),
    )
    report = DossierClaim(
        id="fig-3c", quantity="[kidney] curve", conditions="",
        source_location="report 'kidney'", targetable=False,
    )
    faults = pairing_faults(
        [_CLAIMS[0], shipped, report],
        [
            _series([[0, 1.0], [24, 2.0]], claim="fig-7c"),
            _series([[0, 1.0], [24, 2.0]], claim="fig-3b"),
            _series([[0, 1.0], [24, 2.0]], claim="fig-3c"),
        ],
        carrier="your document",
    )
    assert len(faults) == 3
    assert "fig-7c" in faults[0] and "your document does not carry" in faults[0]
    assert "does not replace numbers the paper shipped" in faults[1]
    assert "never staked" in faults[2]
    # The claim that is paired correctly is not among them.
    assert not any("fig-3a" in fault for fault in faults)
    assert pairing_faults(_CLAIMS, [_series([[0, 1.0], [24, 2.0]])]) == ()


def test_a_figure_claim_reaches_a_verdict_it_could_not_reach_before() -> None:
    """The point of all of it: an abstention becomes a judged claim, in the figure's own band.

    The reconstruction here is the same curve the figure was read off, sampled 25% low. Against a
    printed number that is a `partial`; against a figure it is a pass, and the reference kind that
    decides which is carried by the claim rather than chosen at the judge.
    """
    def concentration(t: float) -> float:
        return 8.0 * (math.exp(-0.12 * t) - math.exp(-0.9 * t))

    series = _series([[i * 0.25, concentration(i * 0.25)] for i in range(97)])
    claim = attach_digitized_values(
        _CLAIMS[:1], [series], times=[24.0 * i / 24 for i in range(25)],
    )[0]
    predicted = [0.75 * concentration(t) for t in range(25)]

    judged: ClaimAssessment = judge_curve(
        claim_id=claim.id, quantity=claim.quantity, source_location=claim.source_location,
        reference=claim.reference_data, predicted=predicted,
        reference_kind=claim.reference_kind,
    )
    assert judged.verdict is Verdict.REPRODUCED
    assert judged.reference_kind == ReferenceKind.DIGITIZED_FIGURE.value

    strict = judge_curve(
        claim_id=claim.id, quantity=claim.quantity, source_location=claim.source_location,
        reference=claim.reference_data, predicted=predicted,
        reference_kind=ReferenceKind.NUMERIC,
        attribution=undetermined_shortfall(claim.quantity),
    )
    assert strict.verdict is Verdict.PARTIAL


def test_an_axis_object_states_its_unit() -> None:
    with pytest.raises(ValueError, match="unstated unit"):
        Axis(minimum=0.0, maximum=1.0, unit="  ")
    assert Axis(minimum=0.1, maximum=10.0, unit="mg", scale=AxisScale.LOG10).transform(1.0) == 0.0


def test_claims_arriving_as_a_generator_are_not_consumed_by_the_check() -> None:
    """The pairing is checked before it is applied, and reading it must not empty the input."""
    attached = attach_digitized_values(
        (claim for claim in _CLAIMS), (s for s in [_series([[0, 1.0], [24, 2.0]])]),
        times=[0.0, 24.0],
    )
    assert len(attached) == 2 and attached[0].reference_data


def test_a_point_that_is_not_two_numbers_is_refused_rather_than_read_past() -> None:
    """A three-number point is the digitizer saying something this reader does not understand.

    Error bars, a second series, a label: taking the first two values and moving on is how a
    reference gets built out of the wrong column with nothing anywhere to show it happened.
    """
    with pytest.raises(ValueError, match="not an .x, y. pair"):
        _series([[0, 1.0, 0.2], [6, 2.0, 0.3]])
    with pytest.raises(ValueError, match="not an .x, y. pair"):
        _series([[0], [6, 2.0]])


def test_resampling_onto_an_empty_grid_is_refused() -> None:
    """Otherwise the claim comes back carrying no values — the state it was already in."""
    with pytest.raises(ValueError, match="no samples"):
        resample_series(_series([[0, 1.0], [24, 2.0]]), [])
    with pytest.raises(ValueError, match="no samples"):
        attach_digitized_values(_CLAIMS[:1], [_series([[0, 1.0], [24, 2.0]])], times=[])


def test_a_window_with_no_curve_in_it_is_refused() -> None:
    """Every sample is the initial condition, so the comparison passes whatever the model does."""
    series = _series([[0, 1.0], [24, 2.0]])
    with pytest.raises(ValueError, match="no curve in it"):
        curve_reference(series, duration=0.0, steps=10)
    with pytest.raises(ValueError, match="samples no interval"):
        curve_reference(series, duration=24.0, steps=0)


def test_a_grid_arriving_as_an_iterator_is_not_consumed_by_the_check() -> None:
    """The grid is walked twice — to check it, then to sample it — like the claims before it."""
    series = _series([[0, 1.0], [24, 2.0]])
    assert resample_series(series, iter([0.0, 12.0, 24.0])) == pytest.approx((1.0, 1.5, 2.0))
