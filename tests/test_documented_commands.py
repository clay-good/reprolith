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


def _documents() -> list[Path]:
    return sorted(
        path for path in REPO.rglob("*.md")
        if ".venv" not in path.parts and "node_modules" not in path.parts
    )


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
        found.append(_PLACEHOLDER.sub("X", line).strip())
    return found


def test_every_documented_command_line_parses() -> None:
    parser = build_parser()
    checked = 0
    for path in _documents():
        for line in _lines(path.read_text(encoding="utf-8")):
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
        if _lines(path.read_text(encoding="utf-8"))
    }
    assert {"README.md", "docs/author-check.md", "docs/figure-values.md"} <= with_commands
