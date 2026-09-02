"""Every command line this repository prints in its own documentation still parses.

Two documents were held to this already — the author guide, and the README's command block — each
by its own check, and a renamed flag anywhere else was found by the reader who copied the line.
The pages that show commands are `README.md`, `docs/author-check.md`, `docs/figure-values.md`,
`docs/mcp-server.md`, and whichever ones are written next; naming them one at a time is how the
third page summarizing one run drifted while the first two were pinned.

So the sweep is over the files, not over a list: every `reprolith …` line in any Markdown file in
the repository is parsed against the real parser. A line that shows a placeholder in angle brackets
is normalized, because `<digest>` is not an argument anyone types.
"""

from __future__ import annotations

import contextlib
import html
import io
import re
from pathlib import Path

import pytest
from reprolith.cli import build_parser

REPO = Path(__file__).resolve().parents[1]

#: What a placeholder stands in for. The parser needs a token, not a real path, and `<file.omex>`
#: would be read as a shell redirect by anyone pasting it — the docs use it as prose.
_PLACEHOLDER = re.compile(r"<[^>]+>")


def _shown(text: str) -> list[str]:
    """Every `reprolith …` command a page shows, joined across its wrapped lines.

    Read line by line rather than by one regex: these blocks put an explanatory `#` comment after
    the wrapping backslash, so a pattern that stops at the comment loses the continuation and then
    fails the command for the arguments that were on it.
    """
    shown: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped.startswith("reprolith "):
            index += 1
            continue
        parts = []
        while index < len(lines):
            body = lines[index].split("#", 1)[0].rstrip()
            parts.append(body.rstrip("\\").strip())
            index += 1
            if not body.endswith("\\"):
                break
        shown.append(" ".join(part for part in parts if part))
    return shown


def _install_lines(text: str) -> list[str]:
    """Every `pip install …` a surface shows, whatever it is written in.

    A rendered page has no line breaks to read: the registry is one line of HTML, and the banner
    that produces it is a Python string split across source lines with its own escapes. So the
    install command is found wherever it appears rather than at the start of a line, and the HTML
    around it is stripped — a check that only recognizes an instruction when it is formatted as
    Markdown is a check on Markdown, not on what a reader is told.
    """
    found = []
    for match in re.finditer(r"pip install[^<\\\n\"`]*", text):
        command = html.unescape(match.group(0)).split("#", 1)[0].strip().rstrip("&").strip()
        # Only the lines that install *this* package. `python -m pip install --upgrade pip` is a
        # pip install and is not one of them, and demanding `-e` of it would be nonsense.
        if "reprolith" in command:
            found.append(command)
    return found


def _documents() -> list[Path]:
    # The rendered registry is in the sweep for the same reason its install line is: it shows
    # commands to a stranger who never opens this repository, and it is the one surface where a
    # command that does not parse is discovered by that stranger rather than by a test. Its
    # `reprolith …` lines sit on their own lines inside the page's `<code>` block, so the same
    # reader finds them.
    return sorted(
        path for path in REPO.rglob("*.md")
        if ".venv" not in path.parts and "node_modules" not in path.parts
    ) + [REPO / "datasets" / "registry.html"]


def _surface_text(path: Path) -> str:
    """A page's text as a reader sees it — markup removed where the page is markup.

    A rendered page puts its closing tags on the same line as the last command in a block, so a
    command read straight out of the HTML runs on into the rest of the document. Tags become line
    breaks and entities become the characters they stand for, which is exactly what the reader's
    browser does; angle-bracket placeholders survive, because in HTML they arrive escaped.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".html":
        return text
    return html.unescape(re.sub(r"<[^>]+>", "\n", text))


def _lines(text: str) -> list[str]:
    found = []
    for line in _shown(text):
        # `|` is prose in these blocks: "<file.omex> | --model <model.xml> --parameters <…>" shows
        # two ways of naming the model, and the arguments after it belong to both. Dropping the bar
        # rather than the text after it keeps them — the command's own check is what refuses naming
        # two models, and this asks only whether the line parses.
        line = line.replace("|", " ")
        # Optional arguments are shown in square brackets; a reader types one or the other.
        line = re.sub(r"\[[^\]]*\]", " ", line)
        # "1" rather than a letter: a placeholder can stand in for a number as well as a path
        # (`--budget <n>`), and a non-numeric stand-in failed a documented line that parses fine.
        found.append(_PLACEHOLDER.sub("1", line).strip())
    return found


def test_every_documented_command_line_parses() -> None:
    parser = build_parser()
    checked = 0
    for path in _documents():
        for line in _lines(_surface_text(path)):
            argv = line.split()[1:]
            if not argv:
                continue
            try:
                parser.parse_args(argv)
            except SystemExit:  # argparse's way of saying the line is wrong
                pytest.fail(f"{path.relative_to(REPO)} shows a command that does not parse: {line}")
            checked += 1
    assert checked >= 20, f"only {checked} command lines found; this check would pass vacuously"


def test_the_sweep_covers_the_pages_that_show_commands() -> None:
    """The population must not be defined by what the check is looking for.

    Enumerated by file, so a page that shows commands is covered the day it is written. This names
    the ones that carry them today only to fail if the walk stops finding them at all.
    """
    with_commands = {
        path.relative_to(REPO).as_posix()
        for path in _documents()
        if _lines(_surface_text(path))
    }
    assert {
        "README.md",
        "docs/author-check.md",
        "docs/figure-values.md",
        # The published page. It carries commands and was outside every sweep in this file until
        # the day its install line was found broken on it.
        "datasets/registry.html",
    } <= with_commands


def test_no_document_promises_an_install_route_that_does_not_exist() -> None:
    """`pip install reprolith` opened the author-facing guide and does not work.

    That guide is the one page written for a stranger — an author who is not a contributor, who
    arrives from a paper rather than from the repository — and its first line failed. The package
    is not published on PyPI; every other page in this repository says `pip install -e .` from a
    checkout, and only this one did not.

    Pinned rather than fixed-and-forgotten because the fix will need reverting the day the package
    *is* published, and a stale clone-first instruction is the same defect in the other direction.

    The sweep read Markdown, and the *public registry page* is Python — a string in `render.py`,
    published to strangers who arrive from a paper and never see this repository's documents, and
    it opened with `pip install reprolith` for as long as this test has existed. A guard written
    for the one page a stranger reads, that could not see the other page a stranger reads. So it
    now covers every surface that ships an install line: the documents, the rendered registry, and
    the source that renders it.
    """
    root = Path(__file__).resolve().parents[1]
    pages = [root / "README.md", root / "CONTRIBUTING.md", *sorted((root / "docs").glob("*.md"))]
    pages += [root / "datasets" / "registry.html", root / "python" / "reprolith" / "render.py"]
    for page in pages:
        for number, line in enumerate(_install_lines(page.read_text(encoding="utf-8")), start=1):
            stripped = line.strip().lstrip("$ ").strip("`")
            assert "-e" in stripped or "--editable" in stripped, (
                f"{page.name} (install line {number}) tells a reader to `{stripped}`, which does "
                "not work: "
                "reprolith is not published, and this repository installs from a checkout"
            )


def test_the_selection_guide_prints_the_numbers_the_command_prints() -> None:
    """The doc's worked example makes a specific claim — that choosing as a set beats reading a
    ranking, by these numbers on this paper — and prose cannot keep that true. A footprint depth,
    an objective weight or one more curated claim would all change it silently."""
    from reprolith.cli import run as run_cli

    page = (REPO / "docs" / "claim-selection.md").read_text(encoding="utf-8")
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        assert run_cli(["select-claims", "BIOMD0000001028", "--budget", "3"]) == 0
    for line in printed.getvalue().splitlines():
        stripped = line.strip()
        # The note and the header wrap in prose; the numbers are what has to match.
        if stripped.startswith(("independent evidential", "witnesses", "and scored", "SELECTED")):
            assert stripped in page, f"docs/claim-selection.md does not show: {stripped}"
