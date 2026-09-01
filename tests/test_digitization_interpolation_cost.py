"""What a *perfect* reading of a figure costs, before the model disagrees at all.

The digitized-figure tolerance is three to five times a printed number's, and the loop record calls
it declared rather than measured: no certified claim has used one, so nothing has exercised the
widening. One component of it can be measured today, with no paper and no picture — the part the
curator's straight lines spend.

A curve is judged on the run's own samples, and between two read points the reference is a straight
line in the axis's own scale. So take a function whose value at every point is known, read it at K
points the way a curator would, resample it onto the run's grid, and compare it against the
function itself. Whatever distance comes back is what a flawless reading costs: no digitizer error,
no model, no paper.

The answer is not "negligible", which is why this is a test and not a footnote.
"""

from __future__ import annotations

import json
import math

import pytest
from reprolith.digitization import (
    DigitizedSeries,
    interpolation_cost,
    read_digitized_figure,
    resample_series,
    series_resolution,
)
from reprolith.oracle import normalized_curve_distance, worst_point_deviation

#: The class default for a curve read off a figure: pass at 0.20, partial at 0.40.
_PASS, _PARTIAL = 0.20, 0.40
_SAMPLES = 100  # the run's grid: 101 samples, the shape `curve_reference` builds


def _reading_cost(
    fn, points_read: int, *, scale: str = "linear", window: float = 24.0
) -> tuple[float, float]:
    """The distance between a flawless K-point reading of ``fn`` and ``fn`` itself.

    Both statistics `judge_curve` uses: the normalized distance and the worst single point.
    """
    read_at = [window * i / (points_read - 1) for i in range(points_read)]
    read = [[x, fn(x)] for x in read_at]
    exact = [fn(window * i / _SAMPLES) for i in range(_SAMPLES + 1)]
    low, high = min(exact), max(exact)
    document = json.dumps({
        "figure": "a function whose value is known everywhere",
        "digitizer": "none: these points are exact",
        "x_axis": {"minimum": 0, "maximum": window, "unit": "h"},
        "y_axis": {
            # A log axis cannot start at zero, and half the smallest value is the tightest frame
            # that holds every point read.
            "minimum": low * 0.5 if scale == "log10" else 0.0,
            "maximum": high * 1.5, "unit": "u", "scale": scale,
        },
        "series": [{"claim": "c", "curve": "q", "points": read}],
    })
    (series,) = read_digitized_figure(document)
    reference = list(resample_series(series, [window * i / _SAMPLES for i in range(_SAMPLES + 1)]))
    return normalized_curve_distance(exact, reference), worst_point_deviation(exact, reference)


def _decay(t: float) -> float:
    return 10.0 * math.exp(-0.25 * t)


def _oral_pk(t: float) -> float:
    """The shape most of this literature plots: absorption up, elimination down."""
    return 8.0 * (math.exp(-0.12 * t) - math.exp(-0.9 * t))


def test_an_exponential_read_off_a_log_axis_is_recovered_exactly() -> None:
    """The claim the axis-scale interpolation rests on, measured rather than asserted.

    An exponential is a straight line on a log axis, so joining two readings in that axis's own
    scale reproduces it — at five points or at forty. Read the same five points as if the axis
    were linear and the cost is a quarter of the whole pass budget.
    """
    for points in (5, 10, 40):
        distance, worst = _reading_cost(_decay, points, scale="log10")
        assert distance < 1e-12 and worst < 1e-12

    linear, _ = _reading_cost(_decay, 5, scale="linear")
    assert 0.04 < linear < 0.06  # 0.0526: a quarter of the 0.20 pass budget, spent on nothing


def test_a_coarse_reading_of_a_pk_curve_spends_the_whole_budget_on_itself() -> None:
    """The number worth publishing: a *flawless* reading of the shape this literature plots, read
    at five points, misses the curve it was read off by more than the pass tolerance.

    Nothing is wrong with the model in this comparison, because there is no model. The distance is
    the curator's own straight lines, and at five points they cost 0.25 against a 0.20 budget.
    """
    distance, _ = _reading_cost(_oral_pk, 5)
    assert distance > _PASS

    # At ten points the average is inside the budget and the worst point is not far off it: the
    # verdict answers to both, and `judge_curve` rescales the worst onto the pass threshold.
    distance, worst = _reading_cost(_oral_pk, 10)
    assert 0.08 < distance < 0.10
    assert worst * (_PASS / _PARTIAL) > 0.9 * _PASS


def test_the_cost_falls_with_the_reading_and_is_small_by_twenty_points() -> None:
    """What a curator can act on: read the bends, not the ends.

    This is the quantity `figure-check` already reports a proxy for — the widest gap between
    readings — and the reason it reports it rather than judging it.
    """
    costs = [_reading_cost(_oral_pk, points)[0] for points in (5, 10, 20, 40)]
    assert costs == sorted(costs, reverse=True)
    assert costs[2] < 0.15 * _PASS   # 0.025 at twenty points
    assert costs[3] < 0.05 * _PASS   # 0.006 at forty


# --- What the *reading* can say about its own cost, with no function behind it -----------------
#
# Everything above needs a function whose value is known everywhere, which is exactly what a
# curator does not have. `interpolation_cost` estimates the same quantity from the reading alone:
# drop each interior point, rejoin its neighbours the way the reference is joined, and measure the
# residual. These tests establish what that estimate is worth.


def _measured(fn, points_read: int, *, scale: str = "linear", window: float = 24.0):
    """The reading's self-estimate beside the truth it is estimating."""
    read_at = [window * i / (points_read - 1) for i in range(points_read)]
    exact = [fn(window * i / _SAMPLES) for i in range(_SAMPLES + 1)]
    low, high = min(exact), max(exact)
    document = json.dumps({
        "figure": "a function whose value is known everywhere",
        "digitizer": "none: these points are exact",
        "x_axis": {"minimum": 0, "maximum": window, "unit": "h"},
        "y_axis": {
            "minimum": low * 0.5 if scale == "log10" else 0.0,
            "maximum": high * 1.5, "unit": "u", "scale": scale,
        },
        "series": [{"claim": "c", "curve": "q", "points": [[x, fn(x)] for x in read_at]}],
    })
    (series,) = read_digitized_figure(document)
    _distance, worst = _reading_cost(fn, points_read, scale=scale, window=window)
    # The truth, expressed the way `judge_curve` expresses a worst point: rescaled onto the pass
    # threshold and taken as a fraction of it, which is what `budget_share` reports.
    truth = worst * (_PASS / _PARTIAL) / _PASS
    return interpolation_cost(series), truth


def test_the_reading_never_under_states_what_its_own_straight_lines_cost() -> None:
    """The property the estimate has to have to be worth printing, and the direction that matters.

    A leave-one-out join spans two gaps where the reference spans one, so it costs more than the
    joins actually used. Over three shapes and four point counts it is never below the truth — which
    is why nothing divides it down.
    """
    for fn, scale in ((_oral_pk, "linear"), (_decay, "linear"), (_decay, "log10")):
        for points in (5, 10, 20, 40):
            cost, truth = _measured(fn, points, scale=scale)
            assert cost["budget_share"] >= truth - 1e-12, (fn, scale, points)


def test_the_over_statement_is_not_a_constant_and_so_is_not_corrected_for() -> None:
    """Why the number is published raw. A smooth curve predicts a factor of four, and a coarse
    reading does not get one: the doubled gap covers a different shape, so the estimate runs from
    1.0x the true worst-point error at five points to 3.9x at forty. A fixed divisor would
    under-state the cost four-fold exactly where the reading is worst.
    """
    ratios = []
    for points in (5, 10, 20, 40):
        cost, truth = _measured(_oral_pk, points)
        ratios.append(cost["budget_share"] / truth)
    assert 1.0 <= ratios[0] < 1.1
    assert 3.0 < ratios[-1] < 4.0
    assert ratios == sorted(ratios)


def test_it_sees_the_curvature_the_widest_gap_cannot() -> None:
    """The false alarm the gap heuristic could not avoid.

    A straight line and an exponential on a log axis are joined *exactly* by the reference's own
    interpolation, however coarsely they are read. The widest gap says 33% of the comparison is
    interpolated in both cases; the cost says that interpolation is free, and it is right.
    """
    for fn, scale in (((lambda t: 2.0 + 0.3 * t), "linear"), (_decay, "log10")):
        cost = _measured(fn, 4, scale=scale)[0]
        assert cost["budget_share"] < 1e-12
        assert cost["worst_residual"] < 1e-12

    # And the shape that is not free is not called free.
    assert _measured(_oral_pk, 4)[0]["budget_share"] > 1.0


def test_the_estimate_falls_with_the_reading_and_clears_the_budget_by_twenty_points() -> None:
    """The guidance, re-derived from the curator's own data rather than from an assumed shape.

    `figure-check` already told curators to read about twenty points, on the strength of a cost
    measured against a function nobody has. The same advice now falls out of the reading itself.
    """
    shares = [_measured(_oral_pk, points)[0]["budget_share"] for points in (5, 10, 20, 40)]
    assert shares == sorted(shares, reverse=True)
    assert shares[0] > 1.0 and shares[1] > 1.0   # five and ten points: over the whole budget
    assert shares[2] < 1.0                        # twenty: inside it, with the over-statement kept


def test_a_two_point_reading_has_nothing_to_check_itself_against() -> None:
    """Reported as not measurable, never as zero: a reading with no interior point does not agree
    with itself, it has nothing to agree with. `figure-check` falls back to the gap there."""
    document = json.dumps({
        "figure": "f", "digitizer": "none",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "u"},
        "series": [{"claim": "c", "curve": "q", "points": [[0, 1.0], [24, 9.0]]}],
    })
    (series,) = read_digitized_figure(document)
    cost = interpolation_cost(series)
    assert cost["measurable"] is False and cost["points"] == 2
    assert cost["budget_share"] is None and cost["worst_residual"] is None


def test_it_catches_a_reading_the_gap_heuristic_calls_fine() -> None:
    """The half worth more than removing the false alarm: the false *reassurance*.

    `figure-check` warns above a 20% widest gap. Ten evenly spaced points span 11% each, so a
    ten-point reading of an oral PK curve drew no warning at all — and it spends about one and a
    half times the whole pass budget on its own straight lines. Geometry could not see that,
    because the cost is in the bend and the gap is not.
    """
    cost, truth = _measured(_oral_pk, 10)
    assert cost["budget_share"] > 1.0 and truth > 0.9
    # The gap that said nothing about it.
    (series,) = read_digitized_figure(json.dumps({
        "figure": "f", "digitizer": "none",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "u"},
        "series": [{"claim": "c", "curve": "q",
                    "points": [[24 * i / 9, _oral_pk(24 * i / 9)] for i in range(10)]}],
    }))
    assert series_resolution(series)["widest_gap_fraction"] < 0.20


def test_a_reading_wider_than_the_run_is_measured_over_the_window_the_verdict_uses() -> None:
    """The one direction this number could under-state, closed by being told the run.

    The residual is normalized by the range of everything the curator read. The claim is judged
    over the run's window, which `window_faults` requires the reading to *cover* — and therefore
    permits it to exceed. Read a curve that barely moves over the judged half and swings over the
    unjudged one, and without the window the same bend is divided by a much larger number than the
    verdict will ever use.

    Given the window, the whole reading costs exactly what the same readings over the judged half
    cost: only the bends inside it are measured, and only the reference inside it sets the scale.
    """
    def two_halves(t: float) -> float:
        # Flat-ish with one bend before 12 h; a large excursion after it that no run will judge.
        return 1.0 + 0.4 * math.sin(math.pi * t / 12.0) if t <= 12.0 else 1.0 + 3.0 * (t - 12.0)

    read_at = [24.0 * i / 8 for i in range(9)]
    judged_at = [t for t in read_at if t <= 12.0]

    def series_over(points: list[float]) -> DigitizedSeries:
        high = max(two_halves(t) for t in points)
        (series,) = read_digitized_figure(json.dumps({
            "figure": "f", "digitizer": "none",
            "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
            "y_axis": {"minimum": 0.0, "maximum": high * 1.5, "unit": "u"},
            "series": [{"claim": "c", "curve": "q", "points": [[t, two_halves(t)] for t in points]}],
        }))
        return series

    whole = interpolation_cost(series_over(read_at))
    judged = interpolation_cost(series_over(judged_at))
    # The same readings over the judged half cost 2.3x what the full reading reported (0.73 against
    # 0.32), because the full reading's range is set by an excursion the verdict never sees.
    assert judged["budget_share"] > 2 * whole["budget_share"]

    # Told the run, the full reading reports the judged number — the same bends against the same
    # scale — rather than the one diluted by the half nothing is judged over.
    windowed = interpolation_cost(series_over(read_at), window=(0.0, 12.0))
    assert windowed["window"] == [0.0, 12.0]
    assert windowed["budget_share"] == pytest.approx(judged["budget_share"])
    assert windowed["worst_at"] == judged["worst_at"]
    # And the whole-reading number is what it always was when no window is given: the reading's own
    # span, so nothing already published moves.
    assert whole["window"] == [0.0, 24.0]


def test_a_window_narrower_than_one_gap_is_reported_as_not_measurable() -> None:
    """A window with no reading strictly inside it has no curvature to measure, and says so.

    The blank is the same shape a two-point reading returns, because it is the same fact: the
    straight lines over this window have nothing inside it to be checked against. Reporting zero
    would say the reading agrees with itself there, which nothing measured.
    """
    (series,) = read_digitized_figure(json.dumps({
        "figure": "f", "digitizer": "none",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0.0, "maximum": 10.0, "unit": "u"},
        "series": [{"claim": "c", "curve": "q", "points": [[t, _oral_pk(t)] for t in (0.0, 8.0, 24.0)]}],
    }))
    assert interpolation_cost(series)["measurable"] is True
    narrow = interpolation_cost(series, window=(0.0, 4.0))
    assert narrow["measurable"] is False
    assert narrow["window"] == [0.0, 4.0]
    assert narrow["budget_share"] is None
