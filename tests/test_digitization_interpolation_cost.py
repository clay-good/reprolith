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

from reprolith.digitization import read_digitized_figure, resample_series
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
