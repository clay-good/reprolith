"""What reading *one value* off a picture costs, before the model disagrees at all.

The scalar digitized-figure tolerance — 15% pass, 30% partial, against a printed number's 5% and
15% — is declared rather than measured, and the loop record says so. The curve band beside it was
measured twice over: what a flawless reading's straight lines cost, and what a curator's own
reading says about its own curvature. Both of those are about *interpolation between* read points,
and a scalar has none. So the docs said the scalar band is set by "the digitizer's calibration and
the plot's pixel resolution" and left it there.

The pixel resolution half is measurable with no paper and no picture, and it is the half a curator
can act on. Every plot digitizer maps a click through two calibration points, so a click that is
off by a pixel is off by one pixel's worth of the axis. That much is arithmetic. What it buys is
not: on a **linear** axis one pixel is a constant *absolute* error, so what it costs relative to
the value read depends on where in the axis that value sits — and near the floor of a linear axis,
reading a single point is over the pass budget before any model is consulted. On a **log** axis one
pixel is a constant *ratio*, so the same reading costs the same everywhere.

This measures the quantization component only, exactly as the interpolation tests measure the
interpolation component only. A digitizer's calibration error — two axis points clicked wrong — is
not here, and is what the axis-range refusal in `read_digitized_figure` exists to catch instead.
"""

from __future__ import annotations

import math

import pytest

#: The class default for one value read off a figure: pass at 0.15, partial at 0.30.
_PASS = 0.15

#: A plot as journals print one: a single-column figure at 300 dpi is about this many pixels tall.
_HEIGHT_PX = 600


def _linear_cost(value: float, *, low: float, high: float, pixels: int, click_px: float) -> float:
    """The relative error a ``click_px`` misread carries at ``value`` on a linear axis."""
    absolute = click_px * (high - low) / pixels
    return absolute / value


def _log_cost(*, low: float, high: float, pixels: int, click_px: float) -> float:
    """The relative error a ``click_px`` misread carries on a log10 axis — the same everywhere."""
    decades = math.log10(high) - math.log10(low)
    return 10.0 ** (click_px * decades / pixels) - 1.0


def test_one_pixel_costs_a_linear_axis_reading_more_the_lower_it_is_read() -> None:
    """The result worth publishing: where in its own axis a value sits is a term in its cost.

    A concentration axis running 0-10 over 600 px carries 0.0083 units per pixel, and half a pixel
    is the best a click can do. Read at the peak that is 0.08% — nothing. Read at a twentieth of the
    peak it is 11% of the pass budget. Read at a hundredth of the peak it is 56% of it, and below
    0.56% of the axis span a *half*-pixel misread has spent the budget outright: no model, no
    interpolation, and a digitizer that did everything right except click one pixel high.
    """
    def at(value: float, px: float = 0.5) -> float:
        return _linear_cost(value, low=0.0, high=10.0, pixels=_HEIGHT_PX, click_px=px)

    # Half a pixel, the best a click can do: the value has to sit in the top of its axis to be free.
    assert at(10.0) == pytest.approx(0.00083, abs=5e-5)
    assert at(1.0) == pytest.approx(0.0083, abs=5e-4)
    assert at(0.5) / _PASS == pytest.approx(0.111, abs=0.01)
    # A hundredth of the axis: over half the budget on quantization alone.
    assert at(0.1) / _PASS == pytest.approx(0.556, abs=0.01)
    # Below 0.56% of the span, half a pixel has spent the whole budget.
    assert at(0.055) > _PASS

    # One whole pixel, which is what a curve drawn with a line width costs in practice.
    assert at(0.1, px=1.0) > _PASS
    # And the boundary, stated as the fraction of its own axis a value has to clear: one pixel of
    # click error is inside the budget only above 1.1% of the axis span.
    clears = 1.0 / (_PASS * _HEIGHT_PX)
    assert clears == pytest.approx(0.0111, abs=0.001)
    assert at(clears * 10.0, px=1.0) == pytest.approx(_PASS, rel=0.02)


def test_a_log_axis_costs_the_same_wherever_the_value_is_read() -> None:
    """Half of pharmacokinetic figures are drawn on log axes, and this is what that buys.

    One pixel of a log axis is a constant ratio, so a reading at the bottom of a three-decade axis
    costs exactly what one at the top costs: 0.58% of the value, a twenty-fifth of the pass budget.
    The same three decades drawn linearly put the bottom decade beyond the budget entirely.
    """
    log = _log_cost(low=0.01, high=10.0, pixels=_HEIGHT_PX, click_px=0.5)
    assert log == pytest.approx(0.00577, abs=5e-5)
    assert log / _PASS < 0.05

    # The same axis read linearly, at the same value: two orders of magnitude worse at the bottom.
    linear = _linear_cost(0.01, low=0.0, high=10.0, pixels=_HEIGHT_PX, click_px=0.5)
    assert linear / log > 100.0
    assert linear > _PASS

    # Doubling the plot's height halves a linear reading's cost and only halves the log axis's
    # exponent — which at this size is the same thing, since the ratio is near 1.
    finer = _log_cost(low=0.01, high=10.0, pixels=2 * _HEIGHT_PX, click_px=0.5)
    assert finer == pytest.approx(log / 2.0, rel=0.01)


def test_the_curve_band_is_not_this_and_is_not_borrowed_from_it() -> None:
    """Stated as a test so a later reader does not merge the two numbers.

    A curve is judged by normalized distance against its own range, so one pixel of the axis is one
    pixel of the range it is divided by — the quantization above is a fixed, tiny share of a curve
    verdict wherever the curve sits. A scalar is judged against *itself*, which is why the same
    pixel costs a hundred times more at the bottom of a linear axis than at the top.
    """
    span = 10.0
    one_pixel_of_the_range = (0.5 * span / _HEIGHT_PX) / span
    assert one_pixel_of_the_range < 0.001
    # Against the curve band's 0.20, a pixel is under half a percent of the budget, wherever read.
    assert one_pixel_of_the_range / 0.20 < 0.005
