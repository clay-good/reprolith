"""The survey's frame test and the digitizer's must mean the same thing, and once they did not.

`scripts/survey_published_figures.py` measures, for every figure of every blocked paper, whether
the image holds a closed plotting box — and its docstring says it looks for "the same shape
`scripts/digitize_figure_panels.py` looks for". It did not. The digitizer groups adjacent inked
rows into *runs* and requires two of them; the survey counted inked **rows**, so one axis line
drawn two pixels thick counted as two.

That was not academic. Dwivedi et al. 2014's Figure 3 is two panels with L-shaped axes, one above
the other: they share a y-axis column that anti-aliasing spreads over three, and the two x axes
give two rows, so an image with no closed box anywhere measured as framed. On the strength of that
number the paper behind four blocked entries — the largest single block in the backlog — was
written up as its best remaining candidate, and the digitizer's docstring, which had said the
opposite from the start, was "corrected" to match the bug.

So the parity is held here rather than asserted in prose: both implementations are run on the same
two pictures and must agree about them.

Needs Pillow and numpy, which the package does not depend on; skipped on the dependency-free gate.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]

pytest.importorskip("numpy", reason="the digitizer and the survey both need numpy")
pytest.importorskip("PIL", reason="the digitizer and the survey both need Pillow")

import numpy as np  # noqa: E402


def _load(name: str):
    sys.path.insert(0, str(_REPO / "scripts"))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(_REPO / "scripts"))


def _blank(height: int = 300, width: int = 400) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def _l_shaped_axes() -> np.ndarray:
    """One x axis and one y axis, each drawn three pixels thick. No box."""
    picture = _blank()
    picture[250:253, 40:380] = 0   # x axis, three rows of ink
    picture[20:253, 40:43] = 0     # y axis, three columns of ink
    return picture


def _closed_box() -> np.ndarray:
    picture = _blank()
    picture[20:23, 40:380] = 0     # top
    picture[250:253, 40:380] = 0   # bottom
    picture[20:253, 40:43] = 0     # left
    picture[20:253, 377:380] = 0   # right
    return picture


def test_a_thick_axis_line_is_one_line_and_not_two() -> None:
    """The defect itself, at the smallest size that shows it."""
    survey = _load("survey_published_figures")
    assert survey._closed_frame(_l_shaped_axes()) is False
    assert survey._closed_frame(_closed_box()) is True


def test_the_survey_and_the_digitizer_agree_about_the_same_picture() -> None:
    """The parity the survey's docstring claims, checked rather than claimed.

    The digitizer raises when it cannot locate a frame; the survey returns False. Those are the
    two implementations' ways of saying the same thing, and they must say it about the same
    pictures.
    """
    survey = _load("survey_published_figures")
    digitizer = _load("digitize_figure_panels")

    for picture, framed in ((_l_shaped_axes(), False), (_closed_box(), True)):
        ink = digitizer._ink(picture.astype(float))
        try:
            digitizer._frame(ink)
            located = True
        except ValueError:
            located = False
        assert located is framed, "the digitizer disagrees with the picture's own shape"
        assert survey._closed_frame(picture) is located, "the survey disagrees with the digitizer"
