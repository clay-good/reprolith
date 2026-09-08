"""Every tool the server offers has a row in the page that describes the server, and vice versa.

`docs/mcp-server.md` is how an agent's operator finds out what this server can do. It was accurate
— and accurate by care rather than by check: a tool added without a row is a capability no reader
can find, and a row for a tool that no longer exists is a promise the server does not keep. This
repository has shipped the first of those more than once, which is why the claim-type catalogue and
the public-API surface are both held to the code the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

from reprolith.mcp_server import EFFECTFUL_TOOLS, TOOL_DEFINITIONS

_DOC = (Path(__file__).parent.parent / "docs" / "mcp-server.md").read_text(encoding="utf-8")
#: A row in either tool table starts with the tool's own name in backticks.
_ROWS = set(re.findall(r"^\| `(\w+)`", _DOC, re.MULTILINE))


def _registered() -> set[str]:
    return {tool["name"] for tool in TOOL_DEFINITIONS} | {tool["name"] for tool in EFFECTFUL_TOOLS}


def test_every_tool_the_server_offers_is_documented() -> None:
    missing = sorted(_registered() - _ROWS)
    assert not missing, (
        "docs/mcp-server.md has no row for: " + ", ".join(missing) +
        " — an agent's operator finds out what this server can do from that page"
    )


def test_every_documented_tool_exists() -> None:
    """The other direction: a row is a promise, and a removed tool leaves one behind."""
    # Rows in these tables are tool names; other backticked cells in the file are arguments and
    # commands, which is why this reads the first cell of a row only.
    named = {row for row in _ROWS if row.islower()}
    unknown = sorted(named - _registered() - _COMMANDS)
    assert not unknown, f"docs/mcp-server.md describes tools the server does not offer: {unknown}"


#: The page also documents the *terminal* commands beside the tools they pair with, and one command
#: that deliberately has no tool. They are not tools and are checked as commands by
#: `tests/test_cli.py`, so they are named here rather than silently allowed through the check above.
_COMMANDS = {"issue_reconcile", "issue-reconcile"}


def test_the_inline_surface_says_what_it_does_not_cover() -> None:
    """Seven quantities can be linted and seventeen kinds of claim can be certified.

    A reader who meets a `lint_*` tool per class reasonably infers there is one per claim type.
    There is not, and the boundary is stated rather than left to be discovered by an agent that
    goes looking for `lint_basin`.
    """
    assert "not every claim type has a lint" in _DOC
