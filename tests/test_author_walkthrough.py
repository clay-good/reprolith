"""The author's path, run end to end on the files this repository ships.

`tests/test_documented_commands.py` parses every command line the guide prints; parsing is not
running. A flag can parse and then be refused, a file shape can drift out from under a documented
step, and the exit status a pre-submission hook is wired to can change without a single line of
prose looking wrong.

So this walks the whole author-facing path on the committed worked example — the archive, the two
loose files, the claims a curator wrote, the tables the paper prints, and the parameters they were
paired with — and asserts what each step returns. It runs no model: every command here reads files
and formats what it finds, which is the contract the author path is built on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith.cli import run

_REPO = Path(__file__).resolve().parents[1]
_WORKED = _REPO / "datasets" / "worked_examples"
_MODEL = _WORKED / "Zake2021_metformin_human_single_PO.xml"
_SEDML = _WORKED / "Zake2021_metformin_human_single_PO.sedml"
_ARCHIVE = _WORKED / "metformin_reconstruction.omex"
_CLAIMS = _REPO / "datasets" / "pkpd_claims.json"
_TABLES = _REPO / "datasets" / "manuscripts" / "BIOMD0000001028_tables.json"
_PARAMETERS = _REPO / "datasets" / "pkpd_parameters.json"
_ACCESSION = "BIOMD0000001028"


def test_the_templates_write_files_the_checks_can_read(tmp_path, capsys) -> None:
    """Step one of the guide, and the only step that writes what the next one reads."""
    claims = tmp_path / "claims.json"
    assert run(["claims-template", "--model", str(_MODEL), "--sedml", str(_SEDML),
                "--out", str(claims)]) == 0
    capsys.readouterr()
    written = json.loads(claims.read_text(encoding="utf-8"))
    assert written["claims"], "the template wrote no stubs from a document that plots curves"

    parameters = tmp_path / "parameters.json"
    assert run(["params-template", "--model", str(_MODEL), "--out", str(parameters)]) == 0
    capsys.readouterr()
    assert json.loads(parameters.read_text(encoding="utf-8"))["parameters"]

    # And an unedited template reaches the check that reads it, reported as unfilled — and
    # refused, which this asserted the opposite of until 2026-09-02. The two author-facing checks
    # met the identical situation and answered it oppositely: an unedited *claims* template has
    # always been refused by name, while an unedited *parameters* template printed "41
    # PARAMETER(S) CHECKED" over 41 rows it skipped and exited 0. This command's exit status is
    # documented as droppable into a pre-submission hook, where that 0 says the model carries the
    # paper's values — over a file the tool had just told the author to go and fill in.
    #
    # It is the ordinary mistake, and the guide sends an author straight from one command to the
    # other, so the message still says "unfilled" rather than accusing the model of anything. Only
    # the status changed, and only for a file where *nothing* was compared and every row is blank.
    assert run(["params-check", "--model", str(_MODEL), "--parameters", str(parameters)]) == 1
    captured = capsys.readouterr()
    assert "not compared" in captured.out
    assert "NOTHING WAS COMPARED" in captured.err
    assert "still has the blanks params-template leaves for you" in captured.err


def test_an_unedited_proposal_is_reported_as_unfinished_not_as_a_failure(capsys, tmp_path) -> None:
    """The state a curator's file is in first, at the surface they see it on.

    Both proposals leave the pairing to the reader — `params-propose` the model element,
    `claims-propose` the model output — and running one straight into the check it feeds is the
    first thing anybody does. Each of those checks answered with a confident accusation until
    today: 169 lines of `MISMATCH: the model declares no parameter ''`, and a candidate from a
    "Tmax, h" column reported as being in the wrong unit for the peak column it never named.

    Held here as well as in the unit tests, because what a curator meets is the message, not the
    function.
    """
    tables = str(_REPO / "datasets" / "manuscripts" / "BIOMD0000001027_tables.json")
    mouse = str(_WORKED / "Zake2021_Metformin_Mice_PO.xml")

    parameters = tmp_path / "proposed_parameters.json"
    assert run(["params-propose", "--tables", tables, "--out", str(parameters)]) == 0
    capsys.readouterr()
    assert run(["params-check", "--model", mouse, "--parameters", str(parameters)]) == 0
    printed = capsys.readouterr().out
    assert "MISMATCH" not in printed
    assert "names no model element yet" in printed

    candidates = tmp_path / "candidates.json"
    assert run(["claims-propose", "--tables", tables, "--out", str(candidates)]) == 0
    capsys.readouterr()
    assert run([
        "claims-check", "--claims", str(candidates), "--tables", tables, "--model", mouse,
    ]) == 0
    printed = capsys.readouterr().out
    assert "NOT FOUND" not in printed and "ANOTHER UNIT" not in printed
    # The rows a curator has not paired yet say which half is missing, in the file's own terms.
    assert "names no model output yet" in printed
    assert "states no metric" in printed


def test_the_archive_check_finds_exactly_what_the_export_said_it_could_not_write(capsys) -> None:
    """Two sides of one fact, reached by different code.

    The committed archive is Reprolith's own export, and the exporter names the claims it could not
    state: the three that run after a prior administration, which a uniform time course cannot
    express. Reading that archive back with the paper's claims, the check finds those three and
    only those three missing — the exporter's list and the checker's list are produced by different
    modules from different inputs, and they agree.
    """
    # Reading an archive means ingesting its model, which needs the engine extra. Every other step
    # of this walk is dependency-free, which is the contract the author path is built on.
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    unexpressed = ("Cmax-250mg-Chung", "Cmax-750mg-Wen", "Cmax-500mg-El-Messaoudi")

    code = run(["archive-check", str(_ARCHIVE), "--claims", str(_CLAIMS),
                "--accession", _ACCESSION])
    printed = capsys.readouterr().out
    assert code == 1
    assert "FIX BEFORE YOU SUBMIT" in printed
    for claim_id in unexpressed:
        assert f"claim '{claim_id}'" in printed
    # And no other claim is named as missing: the export wrote the other thirty.
    claims = json.loads(_CLAIMS.read_text(encoding="utf-8"))["entries"][_ACCESSION]["claims"]
    for other in (c["claim_id"] for c in claims if c["claim_id"] not in unexpressed):
        assert f"claim '{other}'" not in printed, other


def test_the_claims_and_the_parameters_check_clean_against_the_paper(capsys) -> None:
    """Both directions of "does this match the paper", on the committed corpus.

    A value the cited table does not print fails the first; a model not carrying a value its paper
    reports fails the second. Neither fires here, and the walk asserts that: this is the shape a
    correct submission returns, and a check that could only ever fail would be no gate at all.
    """
    assert run(["claims-check", "--claims", str(_CLAIMS), "--tables", str(_TABLES),
                "--accession", _ACCESSION]) == 0
    assert "NOT FOUND" not in capsys.readouterr().out

    # With the model, each claim's stated unit is checked against the unit the model reads that
    # output in — every committed claim of this entry reads a peak, and every one agrees.
    assert run(["claims-check", "--claims", str(_CLAIMS), "--tables", str(_TABLES),
                "--accession", _ACCESSION, "--model", str(_MODEL)]) == 0
    printed = capsys.readouterr().out
    assert "UNITS CHECKED AGAINST" in printed and "ANOTHER UNIT" not in printed

    assert run(["params-check", "--model", str(_MODEL), "--parameters", str(_PARAMETERS),
                "--accession", _ACCESSION]) == 0
    printed = capsys.readouterr().out
    assert "MISMATCH" not in printed
    # And it names what it could not check, which is the number this project is about.
    assert "settable value(s) your paper does not report" in printed


def test_the_export_writes_an_archive_the_check_reads_back(tmp_path, capsys) -> None:
    """The one writing command, and the loop closing on its own output."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    out = tmp_path / "reconstruction.omex"
    assert run(["export", _ACCESSION, "--model", str(_MODEL), "--out", str(out)]) == 0
    capsys.readouterr()
    assert out.exists()

    # Reprolith's own archive, read by Reprolith's own check: it is the positive control the
    # fast-path document names, and its one finding is the deliberate one — the document reports
    # rather than plots, so it states no published result.
    code = run(["archive-check", str(out)])
    printed = capsys.readouterr().out
    assert code == 1
    assert "states no published result" in printed


@pytest.mark.parametrize("argv", [
    ["figure-template", "--sedml", str(_SEDML), "--plot", "plot_5_task2"],
    ["claims-propose", "--tables", str(_TABLES)],
])
def test_the_remaining_author_commands_run_on_the_shipped_files(argv, capsys) -> None:
    assert run(argv) == 0
    assert capsys.readouterr().out.strip()
