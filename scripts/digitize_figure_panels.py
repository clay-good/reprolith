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
#: Ticks evenly spaced to within this many pixels, or the calibration is refused.
_TICK_RESIDUAL_PX = 0.5
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
    """Least-squares value = a + b * pixel through the ticks, refusing an uneven or miscounted set."""
    if len(ticks) != len(labels):
        raise ValueError(
            f"{axis}: {len(ticks)} tick marks found in the image and {len(labels)} labels stated"
        )
    pixels, values = np.array(ticks), np.array(labels, dtype=float)
    slope, intercept = np.polyfit(pixels, values, 1)
    residual_px = np.abs((intercept + slope * pixels - values) / slope).max()
    if residual_px > _TICK_RESIDUAL_PX:
        raise ValueError(f"{axis}: ticks are {residual_px:.2f} px from evenly spaced")
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
    first = int(np.nonzero(ink.sum(axis=0) >= 0.5)[0][0])
    column = ink[:, first]
    lowest = int(np.nonzero(column)[0].max())
    # The opening rise is nearly vertical, so that column holds a tall stroke; the start is its
    # lower end, about a stroke's half-width above its lowest inked pixel.
    stroke = np.where(np.arange(column.size) >= lowest - _ORIGIN_STROKE_PX, column, 0.0)
    return first, _centre(rows, stroke)


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
    coverage = _coverage(area, order)
    origin = _origin(rows, area) if "common_origin" in panel else None

    series_out, report = [], {"panel": panel["panel"], "frame_px": [top, bottom, left, right],
                              "x_ticks_px": x_ticks, "y_ticks_px": y_ticks, "series": []}
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
            if reach > _ORIGIN_REACH_PX:
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


def _pixels(path: Path) -> np.ndarray:
    """The image's RGB pixels, decoded from its bytes: an image has no text encoding to choose."""
    with decode_image(io.BytesIO(path.read_bytes()), formats=["PNG"]) as picture:
        return np.asarray(picture.convert("RGB"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    folder = args.manifest.parent
    image = _pixels(folder / manifest["image"])
    for panel in manifest["panels"]:
        reading, report = read_panel(image, {**manifest["defaults"], **panel})
        (folder / panel["reading"]).write_text(
            json.dumps(reading, indent=1) + "\n", encoding="utf-8"
        )
        print(json.dumps(report))


if __name__ == "__main__":
    main()
