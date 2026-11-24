"""Read the curves off a published figure's panels: a curator's plot digitizer, not Reprolith's.

Reprolith reads no pixels (`docs/figure-values.md`): a reading is a curator's act, and what the
package handles is whether that reading can be trusted and how it is put on a run's grid. This
script is the curator's side of that line, kept in the repository so the reading it produced can
be re-derived from the published image rather than taken on trust. Nothing under `python/` imports
it, and its output goes through exactly the reader and checks a WebPlotDigitizer file does.

What it reads and what it does not:

* **The calibration comes from the picture.** Each panel's frame and tick marks are located in the
  image, to a fraction of a pixel, and the pixel-to-value map is a least-squares line through the
  ticks. A tick count that disagrees with the labels, or ticks that are not evenly spaced, stop the
  reading — that is a mis-calibration, the failure that produces values ordered, smooth, plausible
  and off by a constant factor.
* **The tick labels do not.** Which number is written under each tick is read by eye and stated in
  the manifest, as it would be typed into any plot digitizer. That is the one human step.
* **Each curve is read by its colour**, column by column: every pixel whose colour is the line's
  colour laid over the white background (anti-aliased edges included) is weighed by how much of the
  line it holds, and the column's value is the weighted centre. Each pixel goes only to the colour
  it fits best. Where a line is wholly or partly under one drawn after it and both strokes are
  thin, they coincide to within a stroke width and share a position; where the covering stroke is
  steep the column is skipped and the reading interpolates across it. The printed report counts
  the columns of each kind.
* **Where every line starts**, for a panel the manifest says has a common origin: its value is
  measured from the first inked column, and it is placed on the tick the manifest names only if
  that ink is within two pixels of it.

Usage::

    python scripts/digitize_figure_panels.py datasets/figures/Zake2021_figure5/manifest.json

It rewrites the readings the manifest names, beside the manifest. Needs Pillow and numpy, neither
of which the package depends on.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import numpy as np

# Imported under its own name: it decodes image bytes, and `open` is what the repository's text
# encoding guard reads as a text file opened at the machine's encoding.
from PIL.Image import open as decode_image

#: Ink darker than this, with little colour, is the frame and its ticks.
_DARK = 0.35
#: A frame line crosses most of its panel; text and ticks do not.
_FRAME_SHARE = 0.6
#: How far a tick may sit from an even spacing, as a share of one step. Shared by both
#: calibrations: see :func:`_calibrate` for why it is a share and not a count of pixels.
_TICK_RESIDUAL_SHARE = 0.03
#: How much of the line's colour a pixel must hold to count as part of the line.
_MIN_COVERAGE = 0.2
#: How far a pixel may sit from "the line's colour over white" and still be that line. A faint
#: edge pixel of one line can sit within 45 of another line's colour at a fifth of its strength —
#: the blue line's edge read as green, a 5% spike at a single column — so every pixel is also given
#: only to the line it fits best.
_MAX_COLOUR_RESIDUAL = 25.0


def _hex(colour: str) -> np.ndarray:
    colour = colour.lstrip("#")
    return np.array([int(colour[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def _runs(profile: np.ndarray, threshold: float) -> list[float]:
    """The weighted centres of each run of ``profile`` above ``threshold``."""
    centres: list[float] = []
    start = None
    for i, value in enumerate(list(profile) + [0.0]):
        if value > threshold and start is None:
            start = i
        elif value <= threshold and start is not None:
            idx = np.arange(start, i)
            weights = profile[start:i]
            centres.append(float((idx * weights).sum() / weights.sum()))
            start = None
    return centres


def _ink(rgb: np.ndarray) -> np.ndarray:
    """How dark and colourless each pixel is: 1 for black, 0 for white or any coloured line."""
    grey = rgb.mean(axis=2)
    colourless = (rgb.max(axis=2) - rgb.min(axis=2)) < 40
    return np.where(colourless, (255.0 - grey) / 255.0, 0.0)


def _frame(ink: np.ndarray) -> tuple[float, float, float, float]:
    """(top, bottom, left, right) of the panel's frame, in crop pixels."""
    height, width = ink.shape
    rows = _runs(ink.sum(axis=1), _FRAME_SHARE * width * 0.5)
    cols = _runs(ink.sum(axis=0), _FRAME_SHARE * height * 0.5)
    if len(rows) < 2 or len(cols) < 2:
        raise ValueError(f"no frame found: rows {rows}, columns {cols}")
    return rows[0], rows[-1], cols[0], cols[-1]


def _calibrate(ticks: list[float], labels: list[float], axis: str) -> tuple[float, float]:
    """Least-squares value = a + b * pixel through the ticks, refusing an uneven or miscounted set.

    Evenness is bounded as a **share of one tick step**, which is the rule the grey-tick
    calibration below has always used and the reason it gives: a figure re-rendered or scaled from
    the size it was drawn at carries the original's whole-pixel tick positions, a pixel or two
    either way, and an absolute bound in pixels calls that a mis-calibration on a wide axis while
    letting a genuinely crooked narrow one through. The two calibrations held one measurement to
    two different rules until 2026-11-24; they hold it to the same one now, and the number lives
    in one place.
    """
    if len(ticks) != len(labels):
        raise ValueError(
            f"{axis}: {len(ticks)} tick marks found in the image and {len(labels)} labels stated"
        )
    pixels, values = np.array(ticks), np.array(labels, dtype=float)
    slope, intercept = np.polyfit(pixels, values, 1)
    residual_px = np.abs((intercept + slope * pixels - values) / slope).max()
    spacing = float(np.median(np.diff(np.sort(pixels)))) if len(pixels) > 1 else 0.0
    if spacing <= 0.0 or residual_px > _TICK_RESIDUAL_SHARE * spacing:
        raise ValueError(
            f"{axis}: ticks are {residual_px:.2f} px from evenly spaced, "
            f"{residual_px / spacing:.1%} of a step" if spacing > 0.0
            else f"{axis}: the ticks found share one position, so they state no scale"
        )
    return float(intercept), float(slope)


def _coverage(rgb: np.ndarray, colours: list[str]) -> dict[str, np.ndarray]:
    """How much of each line colour every pixel holds, given only to the colour it fits best.

    A pixel is a line's colour laid over white at some strength; the strength is the least-squares
    share of the line's ink, and the residual is how far the pixel sits from that. A pixel that is
    no line's colour within the tolerance belongs to none of them.
    """
    ink = 255.0 - rgb
    shares, residuals = [], []
    for colour in colours:
        full = 255.0 - _hex(colour)
        share = (ink @ full) / float(full @ full)
        shares.append(share)
        residuals.append(np.abs(ink - share[..., None] * full).max(axis=2))
    best = np.argmin(np.stack(residuals), axis=0)
    return {
        colour: np.where(
            (best == index) & (shares[index] >= _MIN_COVERAGE)
            & (residuals[index] <= _MAX_COLOUR_RESIDUAL),
            shares[index], 0.0,
        )
        for index, colour in enumerate(colours)
    }


#: Two strokes this close are touching, and the one drawn later may be covering part of the other.
_TOUCHING_PX = 2
#: Rows of a stroke's lower end that hold its centre: a line here is about three pixels wide.
_ORIGIN_STROKE_PX = 2
#: How far the first column of ink may sit from the tick the lines are said to start at.
_ORIGIN_REACH_PX = 2.0
#: A column inked over this share of the panel's height is the frame rather than a line. A steep
#: opening rise is the closest a line comes: on the figures here it reaches 83% of the height,
#: while a frame edge reaches 95% and over.
_FRAME_COLUMN_SHARE = 0.9
#: A stroke no taller than this in one column is a flat stretch of line, a few pixels wide; a
#: taller one is a steep stretch, and a line hidden under it could be anywhere along it.
_THIN_PX = 6


def _centre(rows: np.ndarray, weights: np.ndarray) -> float:
    return float((rows * weights).sum() / weights.sum())


def _extent(weights: np.ndarray) -> int:
    filled = np.nonzero(weights)[0]
    return int(filled.max() - filled.min() + 1)


def _column(
    rows: np.ndarray, own: np.ndarray, over: np.ndarray, last: float | None
) -> tuple[float | None, str]:
    """Where one line crosses one column: from its own pixels, shared with a line over it, or not.

    A line wholly or partly under a line drawn after it still has a position, and the two strokes
    coincide there to within a stroke width — but only where both are flat. On a steep stretch the
    covering stroke is tall, the hidden line could be anywhere along it, and the column is skipped
    rather than given a value the picture does not show; the reading interpolates across it.
    """
    near = np.zeros_like(over)
    if own.sum() >= 0.5:
        centre = _centre(rows, own)
        mine = np.nonzero(own)[0]
        touching = np.nonzero(over)[0]
        if touching.size == 0 or np.abs(touching[:, None] - mine[None, :]).min() > _TOUCHING_PX:
            return centre, "own"
        window = np.abs(rows - centre) <= _THIN_PX
    elif last is not None:
        window = np.abs(rows - last) <= _THIN_PX
    else:
        window = np.ones_like(over, dtype=bool)
    near[window] = over[window]
    if near.sum() < 0.5:
        return None, "skipped"
    shared = own + near
    if _extent(near) > _THIN_PX or _extent(shared) > _THIN_PX + 2:
        return None, "skipped"
    return _centre(rows, shared), "shared"


def _stroke_width(coverage: dict[str, np.ndarray]) -> float:
    """The median vertical extent of a line's own ink, in pixels, across this panel.

    What it is for: an allowance stated in pixels is really an allowance in *stroke widths*, and
    the two stop agreeing the moment a figure is drawn at a different weight. Taken over every
    column of every colour, so a panel is measured by its own lines.
    """
    extents: list[int] = []
    for share in coverage.values():
        for column in range(share.shape[1]):
            own = share[:, column]
            if own.sum() >= 0.5:
                extents.append(_extent(own))
    if not extents:
        return 1.0
    extents.sort()
    return float(extents[len(extents) // 2])


def _origin(rows: np.ndarray, area: np.ndarray) -> tuple[int, float]:
    """(column, row) of the point every line in the panel starts from.

    Only for a panel the manifest says has one (``common_origin``): curves that begin at the same
    value — a single dose into a body holding none — leave from a single stroke. It is measured, not
    assumed to be zero: the first column holding line ink, and the centre of the lower end of the
    stroke in it, which is where the lines' common start is drawn. Ink of any colour counts here,
    because where every line is drawn over the others the pixels are a blend that fits none of
    them; inside the frame there is nothing but lines on white.
    """
    ink = (255.0 - area.min(axis=2)) / 255.0
    ink = np.where(ink >= 0.1, ink, 0.0)
    # A column inked down most of the panel is the frame, not a line. Its own anti-aliased edge
    # survives inside the plotting area whenever the frame is drawn thicker than the pixel and a
    # half the crop allows for, and the origin was then measured from it: on Benson et al. 2014
    # the first three columns of the area carry five hundred dark pixels each — out of five
    # hundred and thirty-one rows — and the origin came out twenty-one pixels from the tick the
    # curves visibly leave. Nothing else here is changed by this: a line's column is inked over a
    # stroke's width and a steep rise's over part of the range, never over nearly all of it.
    rows_count = ink.shape[0]
    inked = [
        column for column in range(ink.shape[1])
        if ink[:, column].sum() >= 0.5
        and int((ink[:, column] > 0).sum()) < _FRAME_COLUMN_SHARE * rows_count
    ]
    if not inked:
        raise ValueError(
            "every inked column in the plotting area runs its full height, so there is no line "
            "here to take a common origin from"
        )
    first = int(inked[0])
    column = ink[:, first]
    lowest = int(np.nonzero(column)[0].max())
    # The opening rise is nearly vertical, so that column holds a tall stroke; the start is its
    # lower end, about a stroke's half-width above its lowest inked pixel.
    stroke = np.where(np.arange(column.size) >= lowest - _ORIGIN_STROKE_PX, column, 0.0)
    return first, _centre(rows, stroke)


def _blank_regions(
    area: np.ndarray, regions: Any, *, origin: tuple[int, int], colours: list[str]
) -> list[dict[str, Any]]:
    """Paint ``regions`` white in ``area``, and report what each one removed.

    ``regions`` are ``[x0, y0, x1, y1]`` rectangles in *crop* pixels, which is what a curator reads
    off the image. A rectangle entirely outside the plotting area is refused rather than ignored:
    it means the curator measured it against something other than this panel, and a blank that
    silently does nothing is worse than no blank at all.
    """
    r_lo, c_lo = origin
    removed: list[dict[str, Any]] = []
    for x0, y0, x1, y1 in regions:
        rows = slice(max(int(y0) - r_lo, 0), max(int(y1) - r_lo, 0))
        cols = slice(max(int(x0) - c_lo, 0), max(int(x1) - c_lo, 0))
        patch = area[rows, cols]
        if patch.size == 0:
            raise ValueError(
                f"the blank region [{x0}, {y0}, {x1}, {y1}] covers none of the plotting area "
                f"(rows {r_lo}+, columns {c_lo}+): it is measured against a different picture"
            )
        counts = {
            colour: int((share > _MIN_COVERAGE).sum())
            for colour, share in _coverage(patch, colours).items()
        }
        area[rows, cols] = 255.0
        removed.append({"region": [int(x0), int(y0), int(x1), int(y1)], "pixels": counts})
    return removed


def read_panel(image: np.ndarray, panel: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """One panel's reading in the repository's digitization format, and what it cost to take."""
    x0, y0, x1, y1 = panel["crop"]
    crop = image[y0:y1, x0:x1].astype(float)
    ink = _ink(crop)
    top, bottom, left, right = _frame(ink)

    # Ticks sit just outside the frame: left of it for y, below it for x.
    lo, hi = int(round(top)) + 2, int(round(bottom)) - 1
    y_ticks = [lo + c for c in _runs(ink[lo:hi, int(left) - 4:int(left)].sum(axis=1), 0.8)]
    lo, hi = int(round(left)) + 2, int(round(right)) - 1
    below = int(round(bottom)) + 1
    x_ticks = [lo + c for c in _runs(ink[below:below + 4, lo:hi].sum(axis=0), 0.8)]
    xa, xb = _calibrate(x_ticks, panel["x_ticks"], f"panel {panel['panel']} x")
    # Image rows grow downward, so the labels pair with the ticks bottom-up.
    ya, yb = _calibrate(sorted(y_ticks, reverse=True), panel["y_ticks"], f"panel {panel['panel']} y")

    # The plotting area, inside the frame lines, as whole columns and rows.
    c_lo, c_hi = int(np.ceil(left + 1.5)), int(np.floor(right - 1.5))
    r_lo, r_hi = int(np.ceil(top + 1.5)), int(np.floor(bottom - 1.5))
    area = crop[r_lo:r_hi, c_lo:c_hi]
    rows = np.arange(r_lo, r_hi, dtype=float) + 0.5

    order = [series["colour"] for series in panel["series"]]
    # A legend drawn *inside* the frame is a row of short segments in exactly the line colours this
    # separates by, so every column under it reports two places for one curve and the weighted
    # centre lands between them. The curator states where the legend is and it is painted out —
    # which is a statement about the picture, like the tick labels, and is recorded as one: the
    # report says how many pixels of each colour went with it, so a rectangle that swallowed part
    # of a curve is visible rather than silent.
    blanked = _blank_regions(area, panel.get("blank", ()), origin=(r_lo, c_lo), colours=order)
    coverage = _coverage(area, order)
    origin = _origin(rows, area) if "common_origin" in panel else None

    series_out, report = [], {"panel": panel["panel"], "frame_px": [top, bottom, left, right],
                              "x_ticks_px": x_ticks, "y_ticks_px": y_ticks,
                              "blanked": blanked, "series": []}
    for index, series in enumerate(panel["series"]):
        colour = series["colour"]
        own = coverage[colour]
        # Everything drawn after this line, which is everything that can be covering it.
        over = sum((coverage[c] for c in order[index + 1:]), np.zeros_like(own))
        points: list[list[float]] = []
        counts = {"own": 0, "shared": 0, "skipped": 0}
        last: float | None = None
        for j in range(area.shape[1]):
            row, how = _column(rows, own[:, j], over[:, j], last)
            if row is None:
                counts["skipped"] += 1
                continue
            counts[how] += 1
            last = row
            x = xa + xb * (c_lo + j + 0.5)
            if x < panel.get("x_from", float("-inf")):
                continue
            points.append([round(x, 4), round(ya + yb * row, 5)])
        if origin is not None:
            # Where every line starts. The first column a line can be traced in is often a few
            # tenths of an hour in, because on the opening rise it is under a steeper line drawn
            # after it, and a reading that starts there cannot be resampled at t=0 at all.
            # The lines are drawn from their first sample, so they leave from the tick the manifest
            # names; the first column holding their ink must be within reach of it, or the snap is
            # refused rather than moving a point the picture puts somewhere else.
            j0, row0 = origin
            x_start = float(panel["common_origin"])
            reach = abs(c_lo + j0 + 0.5 - (x_start - xa) / xb)
            # Half a stroke, plus one pixel for the encoder. A line of width w drawn *from* the
            # tick puts its leftmost ink half a width before it, so a fixed allowance in pixels
            # calls a thick-lined figure mis-drawn and lets a hairline one off: Benson et al. 2014
            # draws at four pixels and its ink begins 2.4 px early, which is exactly half a stroke
            # and a little JPEG bleed. Measured from this panel's own lines rather than stated.
            if reach > _stroke_width(coverage) / 2.0 + 1.0:
                raise ValueError(
                    f"panel {panel['panel']}: the lines' first ink is {reach:.1f} px from the tick "
                    f"at {x_start:g}, not where a curve starting there would begin"
                )
            if not points or points[0][0] > x_start:
                points.insert(0, [x_start, round(ya + yb * row0, 5)])
                counts["origin"] = 1
        series_out.append({"claim": series["claim"], "curve": series["curve"], "points": points})
        report["series"].append({"curve": series["curve"], "points": len(points), **counts})

    reading = {
        "figure": panel["figure"],
        "digitizer": panel["digitizer"],
        "x_axis": {"minimum": round(xa + xb * left, 4), "maximum": round(xa + xb * right, 4),
                   "unit": panel["x_unit"]},
        "y_axis": {"minimum": round(ya + yb * bottom, 4), "maximum": round(ya + yb * top, 4),
                   "unit": panel["y_unit"]},
        "series": series_out,
    }
    return reading, report


# ---------------------------------------------------------------------------------------------
# A single dark line among dark markers, with grey ticks inside the frame: the other common way a
# model curve is drawn over the data it was fitted to. Colour cannot separate the line from the
# markers here, so the line is followed by continuity instead.

#: A pixel this dark and this colourless is the line, a marker, or the frame; ticks are grey.
_BLACK = 0.7
#: Grey: lighter than the line, darker than the background. The ticks in such a figure.
_GREY = (0.25, 0.7)
#: How far into the plot a tick reaches before the scan for it stops.
_TICK_REACH_PX = 30
#: Shorter than this, it is a piece of the line or a marker, not a tick.
_MIN_TICK_PX = 7
#: A tick this much longer than the axis's typical one is a major (labelled) one.
_MAJOR_TICK_RATIO = 1.15
#: Columns the line may go unseen — behind a marker, say — before the trace stops.
_LOST_PX = 120
#: Fewer ticks than this on an even spacing, and the calibration is refused.
_MIN_TICKS = 8


def _grey_ticks(band: np.ndarray, along: int) -> list[tuple[float, int]]:
    """(position, length) of each grey tick in a band of pixels running inward from a frame edge.

    ``band`` is indexed [depth, position]: depth 0 is the pixel just inside the frame line.
    """
    grey = (band >= _GREY[0]) & (band <= _GREY[1])
    lengths = np.zeros(band.shape[1], dtype=int)
    for j in range(band.shape[1]):
        n = 0
        while n < band.shape[0] and grey[n, j]:
            n += 1
        lengths[j] = n
    ticks = []
    j = 0
    while j < lengths.size:
        if lengths[j] >= 3:
            k = j
            while k < lengths.size and lengths[k] >= 3:
                k += 1
            weights = lengths[j:k].astype(float)
            ticks.append((along + float((np.arange(j, k) * weights).sum() / weights.sum()) + 0.5,
                          int(lengths[j:k].max())))
            j = k
        else:
            j += 1
    return ticks


def _calibrate_from_frame(
    ticks: list[tuple[float, int]], frame_edge: float, step: float, major_every: float, axis: str,
    direction: int,
) -> tuple[float, float]:
    """value = a + b * pixel, from ticks a fixed step apart counted outward from a frame edge at 0.

    The frame edge carries the axis's 0 label and each tick is one ``step`` from the last; both are
    read off the picture by eye. Every tick found is placed by its distance from the edge, so a
    tick hidden under the line costs nothing, and the fit is refused unless the ticks are evenly
    spaced and every long (labelled) tick lands on a multiple of ``major_every``.
    """
    # Anything shorter than a tick is a piece of the line or a marker that brushed the band.
    ticks = [(p, n) for p, n in ticks if n >= _MIN_TICK_PX]
    if len(ticks) < 2:
        raise ValueError(f"{axis}: only {len(ticks)} ticks found")
    spacing = float(np.median(np.diff(np.sort([p for p, _ in ticks]))))
    # Ticks sit on a lattice counted from the frame edge; anything off it is not one.
    ticks = [
        (p, n) for p, n in ticks
        if abs((p - frame_edge) / spacing - round((p - frame_edge) / spacing)) < 0.1
    ]
    if len(ticks) < _MIN_TICKS:
        raise ValueError(f"{axis}: only {len(ticks)} ticks on an even spacing from the frame")
    positions = np.array([p for p, _ in ticks])
    index = np.round(direction * (positions - frame_edge) / spacing)
    values = index * step
    slope, intercept = np.polyfit(positions, values, 1)
    residual_px = np.abs((intercept + slope * positions - values) / slope).max()
    # Bounded as a share of a tick step, not in pixels: an image scaled up from the one the plot
    # was drawn at carries the original's whole-pixel tick positions, a pixel or two either way.
    if residual_px > _TICK_RESIDUAL_SHARE * spacing:
        raise ValueError(
            f"{axis}: ticks are {residual_px:.2f} px from evenly spaced, "
            f"{residual_px / spacing:.1%} of a step"
        )
    typical = float(np.median([n for _, n in ticks]))
    for (position, length), value in zip(ticks, values):
        if length >= _MAJOR_TICK_RATIO * typical and abs(value / major_every - round(value / major_every)) > 1e-9:
            raise ValueError(
                f"{axis}: a labelled tick at {position:.1f} px reads {value:g}, not a multiple of "
                f"{major_every:g} — the step is misread"
            )
    return float(intercept), float(slope)


def _dark_runs(column: np.ndarray) -> list[tuple[float, int]]:
    """(centre row, length) of each run of line-dark pixels in one column of the plot area."""
    runs, start = [], None
    for i, dark in enumerate(list(column) + [False]):
        if dark and start is None:
            start = i
        elif not dark and start is not None:
            runs.append(((start + i - 1) / 2.0 + 0.5, i - start))
            start = None
    return runs


def _trace(dark: np.ndarray, seed: int) -> dict[int, float]:
    """Follow one line from column ``seed`` both ways: {column: centre row}.

    In each column the dark run nearest where the line is heading is taken, if it is no longer
    than the line's own slope accounts for. A column where none qualifies — a marker sitting on the
    line, the line merging into the frame — is skipped rather than guessed, and the reading
    interpolates across it.
    """
    runs = _dark_runs(dark[:, seed])
    if len(runs) != 1:
        raise ValueError(f"the seed column holds {len(runs)} dark runs; choose one the line has alone")
    trace = {seed: runs[0][0]}
    for direction in (1, -1):
        path = [(seed, runs[0][0])]
        j = seed + direction
        while 0 <= j < dark.shape[1]:
            (j1, r1) = path[-1]
            # Over the last few columns traced, not the last two: two neighbours on one row say
            # "flat" about a line that is still falling, and after a marker that is enough to lose it.
            (j0, r0) = path[max(0, len(path) - 10)]
            slope = (r1 - r0) / (j1 - j0) if j1 != j0 else 0.0
            predicted = r1 + slope * (j - j1)
            gap = abs(j - j1)
            candidates = [
                (abs(c - predicted), c, n) for c, n in _dark_runs(dark[:, j])
                if abs(c - predicted) <= 6 + (1.5 * abs(slope) + 0.5) * gap
                and n <= 10 + 2 * abs(slope)
            ]
            if candidates:
                _, centre, _ = min(candidates)
                path.append((j, centre))
                trace[j] = centre
            elif gap > _LOST_PX:
                break  # lost for long enough that what follows is not this line
            j += direction
    return trace


def _hollow_squares(dark: np.ndarray, size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """(top, bottom, left, right) of every hollow square marker of a side in ``size`` pixels.

    A marker is two vertical sides of one height on the same rows, a side's width apart, with a
    dark top and bottom edge between them. The line can make a vertical run of that height where it
    is steep, but not two on the same rows with edges joining them.
    """
    low, high = size
    sides: list[tuple[int, int, int]] = []  # (column, top, bottom)
    for c in range(dark.shape[1]):
        start = None
        for i, v in enumerate(list(dark[:, c]) + [False]):
            if v and start is None:
                start = i
            elif not v and start is not None:
                if low <= i - start <= high:
                    sides.append((c, start, i - 1))
                start = None
    boxes = []
    for c, t, b in sides:
        for c2, t2, b2 in sides:
            if low - 4 <= c2 - c <= high + 4 and abs(t2 - t) <= 3 and abs(b2 - b) <= 3:
                top, bottom = min(t, t2), max(b, b2)
                if dark[top:top + 4, c:c2 + 1].any(axis=0).mean() > 0.8 and (
                    dark[bottom - 3:bottom + 1, c:c2 + 1].any(axis=0).mean() > 0.8
                ):
                    boxes.append((top, bottom, c, c2))
    return boxes


def _grey_tick_ink(band: np.ndarray) -> float:
    """The darkest pixel the tick finder counted in ``band`` — a tick's own grey, not a line's.

    What it is for: a figure whose thinnest curve never reaches the ink a thick one is read at
    needs its own threshold, and a threshold low enough to catch a hairline can be low enough to
    catch the ticks as well — which would hand a trace near the bottom of the frame a lattice of
    short vertical strokes to follow. The separation is measured here rather than assumed, and
    the reading is refused when there is none.
    """
    grey = (band >= _GREY[0]) & (band <= _GREY[1])
    darkest = 0.0
    for j in range(band.shape[1]):
        depth = 0
        while depth < band.shape[0] and grey[depth, j]:
            depth += 1
        if depth >= 3:  # the same run the tick finder counts
            darkest = max(darkest, float(band[:depth, j].max()))
    return darkest


def _grey_tick_calibration(
    ink: np.ndarray, panel: dict[str, Any]
) -> tuple[tuple[float, ...], tuple[int, ...], tuple[float, ...], dict[str, Any]]:
    """The frame, the plotting area inside it, and the value map its inner grey ticks give.

    Shared by the two modes that read a figure drawn in black on white: one dark line among dark
    markers, and several dark lines crossing each other. The calibration is the same act in both —
    count the ticks up from the frame edge that carries the axis's 0.
    """
    top, bottom, left, right = _frame(ink)
    thickness = int(panel.get("frame_px", 4))
    inner_top, inner_bottom = int(round(top)) + thickness, int(round(bottom)) - thickness
    inner_left, inner_right = int(round(left)) + thickness, int(round(right)) - thickness
    below = ink[inner_bottom - _TICK_REACH_PX + 1:inner_bottom + 1][::-1]
    x_band = below[:, inner_left:inner_right]
    x_ticks = _grey_ticks(x_band, inner_left)
    beside = ink[inner_top:inner_bottom, inner_left:inner_left + _TICK_REACH_PX].T
    y_ticks = _grey_ticks(beside, inner_top)
    xa, xb = _calibrate_from_frame(
        x_ticks, left, panel["x_step"], panel["x_major_every"], "x", 1)
    ya, yb = _calibrate_from_frame(
        y_ticks, bottom, panel["y_step"], panel["y_major_every"], "y", -1)
    measured = {
        "x_ticks": len(x_ticks), "y_ticks": len(y_ticks),
        "tick_ink": round(max(_grey_tick_ink(x_band), _grey_tick_ink(beside)), 3),
    }
    return (
        (top, bottom, left, right),
        (inner_top, inner_bottom, inner_left, inner_right),
        (xa, xb, ya, yb),
        measured,
    )


def read_line_panel(image: np.ndarray, panel: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """One dark line read off a panel whose markers share its colour."""
    x0, y0, x1, y1 = panel["crop"]
    crop = image[y0:y1, x0:x1].astype(float)
    ink = _ink(crop)
    frame, inner, scale, measured = _grey_tick_calibration(ink, panel)
    top, bottom, left, right = frame
    inner_top, inner_bottom, inner_left, inner_right = inner
    xa, xb, ya, yb = scale
    x_ticks, y_ticks = measured["x_ticks"], measured["y_ticks"]

    area = ink[inner_top:inner_bottom, inner_left:inner_right] >= _BLACK
    boxes = _hollow_squares(area, tuple(panel["marker_px"])) if "marker_px" in panel else []
    for top_, bottom_, left_, right_ in boxes:
        # A marker hides whatever line passes behind it: blanked, so a column through one has no
        # line to offer and is skipped, rather than reading the marker's edge as the line.
        area[max(top_ - 3, 0):bottom_ + 4, max(left_ - 3, 0):right_ + 4] = False
    seed = int(round((panel["seed_x"] - xa) / xb)) - inner_left
    trace = _trace(area, seed)
    points = []
    for j in sorted(trace):
        x = xa + xb * (inner_left + j + 0.5)
        if x < panel.get("x_from", float("-inf")):
            continue
        points.append([round(x, 4), round(ya + yb * (inner_top + trace[j]), 5)])
    origin = None
    if panel.get("starts_at_frame_corner"):
        # The line is drawn from the plot's lower-left corner — its first sample, at the frame's
        # 0 on both axes. Read there, and only if the trace reaches within reach of that edge.
        first = points[0][0]
        if first > panel["corner_reach"]:
            raise ValueError(f"the line is traced from x={first:g}, too far from the corner to join it")
        # The same rounding the axis bounds get, since this point is the frame corner itself.
        origin = [round(xa + xb * left, 4), round(ya + yb * bottom, 4)]
        points.insert(0, origin)
    series = panel["series"][0]
    reading = {
        "figure": panel["figure"],
        "digitizer": panel["digitizer"],
        "x_axis": {"minimum": round(xa + xb * left, 4), "maximum": round(xa + xb * right, 4),
                   "unit": panel["x_unit"]},
        "y_axis": {"minimum": round(ya + yb * bottom, 4), "maximum": round(ya + yb * top, 4),
                   "unit": panel["y_unit"]},
        "series": [{"claim": series["claim"], "curve": series["curve"], "points": points}],
    }
    report = {"panel": panel["panel"], "frame_px": [top, bottom, left, right],
              "x_ticks": x_ticks, "y_ticks": y_ticks,
              "columns": inner_right - inner_left, "traced": len(trace), "origin": origin,
              "markers_blanked": len({(box[0], box[2]) for box in boxes})}
    return reading, report


# ---------------------------------------------------------------------------------------------
# Several dark lines on a white field, crossing each other: a figure that plots a species and its
# metabolites together. Colour cannot separate them and continuity alone cannot either — where two
# lines meet, one stroke is both of them, and a tracer that takes it inherits the other line's
# slope and leaves on the wrong branch. So they are followed *together*: every line predicts where
# it is heading, and a stroke two lines both reach for is read as neither.

#: A line this far from where it is heading is not it. Grows with the gap since the line was last
#: seen — a dashed line is lost for a dash's length — but slowly, so a lost trace stops rather
#: than finding its way onto a neighbour.
_REACH_PX = 4.0
#: Columns a line may go unseen before its trace stops. A dash gap, not a journey.
_DASH_PX = 40


def _trace_together(
    dark: np.ndarray, seed: int, rows: list[float], lost: int = _DASH_PX
) -> list[dict[int, float]]:
    """Follow several lines from one column they are separate in: [{column: centre row}].

    Each line is seeded on the run nearest the row the curator read it at, and the stroke widths
    those seeds give are what each line's own strokes are measured against afterwards. In every
    column each line reaches for the run nearest where it is heading; a run that two lines both
    reach for is where they cross, and neither is given a value there — their traces resume on the
    far side and the reading interpolates across, exactly as the colour mode does for a line drawn
    under another.
    """
    runs = _dark_runs(dark[:, seed])
    if not runs:
        raise ValueError("the seed column holds no dark pixels")
    seeds = []
    for row in rows:
        distance, centre, length = min((abs(c - row), c, n) for c, n in runs)
        if distance > _THIN_PX:
            raise ValueError(
                f"a line is seeded at row {row:.0f}, {distance:.0f} px from the nearest stroke in "
                "the seed column — read the seed off the figure again"
            )
        seeds.append((centre, length))
    if len({centre for centre, _ in seeds}) < len(seeds):
        raise ValueError(
            "two lines are seeded on one stroke; seed them in a column they are drawn apart in"
        )
    traced: list[dict[int, float]] = [{seed: centre} for centre, _ in seeds]
    for direction in (1, -1):
        paths = [[(seed, centre)] for centre, _ in seeds]
        j = seed + direction
        while 0 <= j < dark.shape[1]:
            column = _dark_runs(dark[:, j])
            reached: list[int | None] = []
            for path, (_, stroke) in zip(paths, seeds):
                (j1, r1) = path[-1]
                (j0, r0) = path[max(0, len(path) - 10)]
                slope = (r1 - r0) / (j1 - j0) if j1 != j0 else 0.0
                predicted, gap = r1 + slope * (j - j1), abs(j - j1)
                candidates = [
                    (abs(centre - predicted), index)
                    for index, (centre, length) in enumerate(column)
                    if abs(centre - predicted) <= stroke + _REACH_PX + 0.5 * gap
                    and length <= stroke + 2 + 2 * abs(slope)
                ]
                reached.append(min(candidates)[1] if candidates else None)
            taken = [index for index in reached if index is not None]
            crossing = {index for index in taken if taken.count(index) > 1}
            for line, index in enumerate(reached):
                if index is None or index in crossing:
                    continue
                paths[line].append((j, column[index][0]))
                traced[line][j] = column[index][0]
            if all(abs(j - path[-1][0]) > lost for path in paths):
                break
            j += direction
    return traced


def read_lines_panel(
    image: np.ndarray, panel: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Several dark lines read off one panel, each followed by continuity and jointly at crossings."""
    x0, y0, x1, y1 = panel["crop"]
    ink = _ink(image[y0:y1, x0:x1].astype(float))
    frame, inner, scale, measured = _grey_tick_calibration(ink, panel)
    top, bottom, left, right = frame
    inner_top, inner_bottom, inner_left, inner_right = inner
    xa, xb, ya, yb = scale

    threshold = float(panel.get("line_ink", _BLACK))
    if threshold <= measured["tick_ink"]:
        raise ValueError(
            f"the lines are read at ink {threshold:g} and the axis ticks reach "
            f"{measured['tick_ink']:g}: at that threshold a trace can follow a tick"
        )
    area = ink[inner_top:inner_bottom, inner_left:inner_right] >= threshold
    seed_column = int(round((panel["seed_x"] - xa) / xb)) - inner_left
    seed_rows = [(series["seed_y"] - ya) / yb - inner_top for series in panel["series"]]
    traces = _trace_together(area, seed_column, seed_rows)

    # The two edges the ticks are counted from carry their axis's zero — that is the statement the
    # calibration is built on, and it is read off the picture rather than fitted. The least-squares
    # line through the ticks lands a fraction of a pixel from it either way; on those two edges the
    # statement is taken over the residual, and both numbers are reported so the gap is visible.
    # The other two edges are the fit's, there being nothing stated about them.
    fitted_zero = (xa + xb * left, ya + yb * bottom)
    corners = {
        "upper-left": (0.0, round(ya + yb * top, 4)),
        "lower-left": (0.0, 0.0),
    }
    series_out, counts = [], []
    for series, trace in zip(panel["series"], traces):
        points = [
            [round(xa + xb * (inner_left + j + 0.5), 4), round(ya + yb * (inner_top + trace[j]), 5)]
            for j in sorted(trace)
        ]
        corner = series.get("starts_at")
        if corner is not None:
            # The line is drawn from its first sample, which sits on the frame corner the curator
            # names — the only point of it the trace cannot reach, because there the line runs into
            # the frame. It is read off the calibration, and only if the trace arrives within reach
            # of it; otherwise the snap is refused rather than moving a point the picture places
            # elsewhere.
            if corner not in corners:
                raise ValueError(f"'{corner}' is not a corner of the frame: {sorted(corners)}")
            x_corner, y_corner = corners[corner]
            if points[0][0] - x_corner > float(panel["corner_reach"]):
                raise ValueError(
                    f"'{series['curve']}' is traced from x={points[0][0]:g}, too far from the "
                    f"{corner} corner at x={x_corner:g} to join it"
                )
            points.insert(0, [x_corner, y_corner])
        series_out.append({"claim": series["claim"], "curve": series["curve"], "points": points})
        counts.append({"curve": series["curve"], "points": len(points),
                       "columns_read": len(trace), "starts_at": corner})
    reading = {
        "figure": panel["figure"],
        "digitizer": panel["digitizer"],
        "x_axis": {"minimum": 0.0, "maximum": round(xa + xb * right, 4),
                   "unit": panel["x_unit"]},
        "y_axis": {"minimum": 0.0, "maximum": round(ya + yb * top, 4),
                   "unit": panel["y_unit"]},
        "series": series_out,
    }
    report = {"panel": panel["panel"], "frame_px": [top, bottom, left, right],
              "columns": inner_right - inner_left, "line_ink": threshold,
              "fitted_zero": [round(value, 5) for value in fitted_zero],
              **measured, "series": counts}
    return reading, report


def _pixels(path: Path) -> np.ndarray:
    """The image's RGB pixels, decoded from its bytes: an image has no text encoding to choose.

    The format list is explicit so an unexpected file still fails loudly, and it holds **JPEG as
    well as PNG** for a licensing reason rather than a technical one: a figure under a no-
    derivatives licence is redistributed in the bytes its publisher served, and re-encoding it to
    suit this reader would be the one thing that licence forbids. JPEG costs something in return —
    its ringing puts off-colour pixels along every edge — which the colour separation already has
    a tolerance for, and which the reading's own interpolation cost reports if it ever matters.
    """
    with decode_image(io.BytesIO(path.read_bytes()), formats=["PNG", "JPEG"]) as picture:
        return np.asarray(picture.convert("RGB"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    folder = args.manifest.parent
    image = _pixels(folder / manifest["image"])
    for panel in manifest["panels"]:
        settings = {**manifest["defaults"], **panel}
        reader = {
            "dark-line": read_line_panel, "dark-lines": read_lines_panel,
        }.get(settings.get("mode", ""), read_panel)
        reading, report = reader(image, settings)
        (folder / panel["reading"]).write_text(
            json.dumps(reading, indent=1) + "\n", encoding="utf-8"
        )
        print(json.dumps(report))


if __name__ == "__main__":
    main()
