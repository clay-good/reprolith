"""The front page, checked against the surface it advertises.

The README's command block is where a reader learns what the CLI can do. A command added
without a line here is a command nobody finds; a line that outlives its command sends a reader to
an error. Neither shows up in any other test, and both are one commit away at all times.

Pure stdlib: this reads two files.
"""

from __future__ import annotations

import re
from pathlib import Path

from reprolith.cli import build_parser

_README = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")


def _commands_in_readme() -> set[str]:
    return {line.split()[0] for line in re.findall(r"^reprolith ([a-z-]+.*)$", _README, re.M)}


def test_the_front_page_shows_every_command_the_cli_has() -> None:
    """Three were missing when this was written — `presubmission`, `dossier` and `bundle` — so
    the front page described a smaller tool than the one installed."""
    parser = build_parser()
    (subcommands,) = [
        action.choices for action in parser._subparsers._group_actions  # noqa: SLF001
    ]
    assert set(subcommands) == _commands_in_readme()
