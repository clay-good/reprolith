"""The terminal and the agent surface answer every read the same way, not just one of them.

Task 6.4 asks for surface parity — "the same entry reports the same verdict through both" — and
one command was checked for it: `catalog`. Eleven read commands offer `--json`, each documented as
emitting what its MCP tool returns, and ten of them were held to that by nothing. A formatter that
drifted on either side would be invisible: the CLI tests read the CLI, the server tests read the
server, and neither reads the other.

Driven from the CLI's own subcommand list rather than from a list written here, so a read command
added without a parity pair fails instead of being skipped.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from reprolith.cli import build_parser, run
from reprolith.mcp_server import dispatch_tool, load_repository
from test_cli import _write_repo  # the same repository the CLI tests build

#: Which MCP tool answers each read command, and the arguments each needs. `{digest}`,
#: `{accession}` and `{item_id}` are filled from the repository the test builds — the last from
#: its own verification queue, since a derived item id is a hash of the question and cannot be
#: written down here.
_PAIRS = {
    "catalog": ("list_catalog", {}),
    "backlog": ("backlog_health", {}),
    "loop-status": ("loop_status", {}),
    "self-validation": ("self_validation", {}),
    "corroboration": ("corroboration", {}),
    "select-claims": ("select_claims", {"accession": "ACC1", "budget": 2}),
    "certificate": ("certificate", {"digest": "{digest}"}),
    "verdict": ("verdict", {"digest": "{digest}"}),
    "gaps": ("gaps", {"digest": "{digest}"}),
    "presubmission": ("presubmission", {"digest": "{digest}"}),
    "verification-queue": ("verification_queue", {}),
    "verification-issue": ("verification_issue", {"item_id": "{item_id}"}),
    "dossier": ("dossier", {"accession": "ACC1"}),
    "bundle": ("bundle", {"accession": "ACC1"}),
    "status": ("status", {"accession": "ACC1"}),
    "certificates-for": ("certificates_for", {"accession": "ACC1"}),
}

#: The commands that read files of the caller's own rather than this repository. The MCP server
#: holds no path to those files, and `docs/mcp-server.md` says so one by one — so they have no
#: tool to be in parity with, and listing them here is what keeps that an explicit decision.
_NO_TOOL = {
    "export", "archive-check", "claims-template", "claims-propose", "claims-check",
    "params-template", "params-propose", "params-check", "figure-template", "figure-check",
}


def test_every_read_command_is_paired_with_a_tool_or_named_as_having_none() -> None:
    subcommands = set(next(
        a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)
    ).choices)
    assert set(_PAIRS) | _NO_TOOL == subcommands, (
        sorted(subcommands - (set(_PAIRS) | _NO_TOOL)),
        sorted((set(_PAIRS) | _NO_TOOL) - subcommands),
    )


@pytest.mark.parametrize("command", sorted(_PAIRS))
def test_the_terminal_emits_what_the_tool_returns(command, tmp_path, capsys) -> None:
    repo, digest = _write_repo(tmp_path)
    tool, arguments = _PAIRS[command]
    # A queue item id is a hash of its own question, so it can only be read off the repository
    # this test just built rather than written into the table above.
    queued = load_repository(Path(repo))[0].verification_queue()["pending"]

    def fill(value: str) -> str:
        if value == "{digest}":
            return digest
        if value == "{item_id}":
            assert queued, "the fixture certificate carries no queued item to pair on"
            return str(queued[0]["id"])
        return value

    _POSITIONAL = ("digest", "accession", "item_id")
    # The one positional each of these takes, in the vocabulary the command uses: a digest for a
    # certificate view, an item id for a queue item, an accession for everything else that names
    # an entry.
    positional = [fill(value) for key, value in arguments.items() if key in _POSITIONAL]
    # Everything the command takes that is not its positional, in the flag spelling the terminal
    # uses. Without this the one command carrying a required option could not be paired at all,
    # and leaving it out of the table is how a surface drifts unnoticed.
    flags = [
        token
        for key, value in arguments.items() if key not in _POSITIONAL
        for token in (f"--{key.replace('_', '-')}", str(value))
    ]
    argv = ["--data-dir", str(repo), command, *positional, *flags, "--json"]
    assert run(argv) == 0, command
    printed = json.loads(capsys.readouterr().out)

    query, _catalog = load_repository(Path(repo))
    filled = {key: fill(value) for key, value in arguments.items()}
    answer = dispatch_tool(query, tool, filled)
    # Not vacuous: two surfaces agreeing that there is nothing to report would pass this check
    # while saying nothing about either, and every one of these views has content in this fixture.
    assert answer, command
    assert printed == answer, command
