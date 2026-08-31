"""The figure-digitization guide, checked against the thing it documents.

[`docs/figure-values.md`](../docs/figure-values.md) is written for a curator who has read a curve
off a picture and will copy from this page: the command lines, the file shape, and the import line.
Each of those fails invisibly — a renamed command still reads fine, a schema drifts one field at a
time, and a moved import is a page that is right about everything except how to run it.

The same fence `tests/test_author_doc.py` puts around the author guide, on the page beside it.
Pure stdlib: nothing here runs a model.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import reprolith
from reprolith import read_digitized_figure, series_resolution
from reprolith.cli import build_parser, run

_ROOT = Path(__file__).parent.parent
_DOC = (_ROOT / "docs" / "figure-values.md").read_text(encoding="utf-8")


def test_every_command_line_the_guide_shows_parses() -> None:
    """A curator copying a line from the page should not be the one who finds out it moved."""
    parser = build_parser()
    lines = [line.strip() for line in re.findall(r"^reprolith .+$", _DOC, re.MULTILINE)]
    assert lines, "the guide shows no commands; this check would pass vacuously"
    commands = set()
    for line in lines:
        # `#` starts a comment in the shell block, not an argument.
        argv = line.split("#")[0].split()[1:]
        commands.add(parser.parse_args(argv).command)  # raises SystemExit if the guide is wrong
    # Both halves of the loop the page describes are shown: the file is written, then read.
    assert commands == {"figure-template", "figure-check"}


def _the_digitization() -> str:
    blocks = [b for b in re.findall(r"```json\n(.*?)```", _DOC, re.DOTALL) if '"digitizer"' in b]
    assert len(blocks) == 1, f"expected exactly one digitization in the guide, found {len(blocks)}"
    return blocks[0]


def test_the_file_the_guide_shows_is_a_file_this_reader_accepts() -> None:
    """A schema drifts one field at a time, and every field here is required or defaulted."""
    (series,) = read_digitized_figure(_the_digitization())
    assert series.claim_id == "fig3a-plasma"
    assert series.figure == "Figure 3A" and series.digitizer.startswith("WebPlotDigitizer")
    # The log axis is the point of the example, and the interpolation the page promises is the
    # one this scale selects.
    assert series.y_axis.scale.value == "log10"


def test_the_file_the_guide_shows_passes_the_check_the_guide_runs_on_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """The page shows a file and then shows the command that reads it. It has to survive that.

    It also has to cover its own axis from the start: the guide now says a reading that begins
    after the run does is refused, and an example that did exactly that was the page arguing
    against itself in two places.
    """
    path = tmp_path / "figure3a.json"
    path.write_text(_the_digitization(), encoding="utf-8")
    assert run(["figure-check", "--series", str(path)]) == 0
    assert "no model was run" in capsys.readouterr().out

    (series,) = read_digitized_figure(_the_digitization())
    x_low = min(x for x, _ in series.points)
    assert x_low == series.x_axis.minimum, (
        "the example is read from the start of its own axis, so a run over that window needs "
        "nothing extrapolated"
    )
    assert series_resolution(series)["points"] == 3


def test_the_import_line_the_guide_shows_imports() -> None:
    """A page that is right about everything except how to call it is a page nobody can follow."""
    (line,) = re.findall(r"^from reprolith import (.+)$", _DOC, re.MULTILINE)
    for name in (n.strip() for n in line.split(",")):
        assert hasattr(reprolith, name), f"the guide imports {name}, which the package does not export"


def test_the_marker_the_guide_prints_is_the_marker_the_renderer_writes() -> None:
    """The whole point of the join is that a reader can see the number came off a picture."""
    assert "[figure-reading]" in _DOC
    render = (_ROOT / "python" / "reprolith" / "render.py").read_text(encoding="utf-8")
    assert '" [figure-reading]"' in render, (
        "the guide shows a claim line marked [figure-reading]; the renderer no longer writes it"
    )
