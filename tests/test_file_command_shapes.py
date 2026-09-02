"""What a script reading the author-facing commands' `--json` receives, pinned.

Every *read* command's `--json` is held to the object its MCP tool returns, so the two surfaces
cannot drift apart. The eleven commands that read files of the caller's own have no tool — that is
the decision `docs/mcp-server.md` argues one by one — so for them the equivalent guard is here or
nowhere. `figure-check` got one when that argument was first made; the other file-based commands
did not, and a renamed key would break every script consuming them with nothing going red.

Shapes only: what each object's top level promises. The contents are checked where the behaviour
is, and a test that restated them here would go stale against the thing it duplicates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith.cli import run

_REPO = Path(__file__).resolve().parents[1]
_WORKED = _REPO / "datasets" / "worked_examples"
_MANUSCRIPTS = _REPO / "datasets" / "manuscripts"
_MODEL = str(_WORKED / "Zake2021_metformin_human_single_PO.xml")
_SEDML = str(_WORKED / "Zake2021_metformin_human_single_PO.sedml")
_TABLES = str(_MANUSCRIPTS / "BIOMD0000001028_tables.json")
_CLAIMS = str(_REPO / "datasets" / "pkpd_claims.json")
_PARAMETERS = str(_REPO / "datasets" / "pkpd_parameters.json")
_ACCESSION = "BIOMD0000001028"


def _emitted(capsys, argv: list[str]) -> dict:
    assert run(argv) in (0, 1), argv  # a finding is a valid outcome; a crash is not
    return json.loads(capsys.readouterr().out)


def test_claims_check_shape(capsys) -> None:
    payload = _emitted(capsys, [
        "claims-check", "--claims", _CLAIMS, "--accession", _ACCESSION,
        "--tables", _TABLES, "--json",
    ])
    assert set(payload) == {"checks", "units", "units_in_tables"}
    assert {"claim_id", "reported", "found", "detail"} <= set(payload["checks"][0])


def test_params_check_shape(capsys) -> None:
    payload = _emitted(capsys, [
        "params-check", "--model", _MODEL, "--parameters", _PARAMETERS,
        "--accession", _ACCESSION, "--json",
    ])
    assert set(payload) == {"checks", "not_reported_by_the_paper"}
    assert {"parameter", "reported", "carried", "agrees", "detail", "units"} == set(
        payload["checks"][0]
    )
    # Grouped by kind, never a flat list: a compartment reported under "parameters" answers about
    # the wrong thing.
    assert isinstance(payload["not_reported_by_the_paper"], dict)


def test_archive_check_shape(capsys) -> None:
    # The only shape here whose command ingests a model, which needs the engine extra. The rest of
    # this file runs on the dependency-free gate, as the commands themselves do.
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    payload = _emitted(capsys, [
        "archive-check", str(_WORKED / "metformin_reconstruction.omex"), "--json",
    ])
    assert set(payload) == {"ready_to_submit", "readiness", "fix_list", "found", "note"}
    assert {"readable", "files", "claims", "adoptable_recipes", "run_time_unit"} <= set(
        payload["found"]
    )


@pytest.mark.parametrize(("argv", "keys"), [
    (["claims-propose", "--tables", _TABLES],
     {"description", "candidates", "tables_read", "notes"}),
    (["params-propose", "--tables", _TABLES], {"description", "parameters", "notes"}),
    (["claims-template", "--model", _MODEL, "--sedml", _SEDML],
     {"description", "claims", "readable_outputs", "settable_parameters",
      "model_determines", "notes"}),
    (["params-template", "--model", _MODEL],
     {"parameters", "model_determines", "fill_in"}),
])
def test_the_files_the_templates_and_proposals_write(argv, keys, capsys) -> None:
    payload = _emitted(capsys, argv)
    assert set(payload) == keys, argv
