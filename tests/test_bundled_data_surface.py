"""The commands a reader types first, on the data this repository actually ships.

Every other CLI test builds its own repository in a temp directory and passes `--data-dir` at it.
That exercises the loading path and nothing about the *committed* state: a data file that gained a
field the loader refuses, a directory that moved, a certificate whose digest no longer resolves —
all of it passes a suite that only ever reads what it just wrote, and fails the first command a
reader types.

So this walks the read surface with no `--data-dir` at all, against the bundled milestone run, and
holds what it prints to the committed data rather than to a literal here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith.cli import run

_REPO = Path(__file__).resolve().parents[1]
_DATASETS = _REPO / "datasets"


def _seeded() -> list[str]:
    entries = json.loads(
        (_DATASETS / "pkpd_test_set.json").read_text(encoding="utf-8")
    )["entries"]
    return [entry["accession"] for entry in entries]


def test_the_catalog_a_reader_sees_is_the_seeded_set(capsys) -> None:
    assert run(["catalog"]) == 0
    printed = capsys.readouterr().out
    accessions = _seeded()
    assert accessions, "the seeded set is empty; this check would pass vacuously"
    for accession in accessions:
        assert accession in printed, accession


def test_every_committed_certificate_is_reachable_by_the_commands_that_read_one(capsys) -> None:
    """A digest that does not resolve is invisible to a suite that writes its own certificates."""
    certified = sorted({
        path.stem for path in (_DATASETS / "milestone" / "certificates").glob("*.json")
    })
    assert certified, "no committed PK/PD certificates found"

    for accession in certified:
        assert run(["certificates-for", accession]) == 0, accession
        digests = capsys.readouterr().out.split()
        assert digests, accession
        for command, expected in (
            ("certificate", "REPRODUCTION CERTIFICATE"),
            ("verdict", "OVERALL:"),
            ("gaps", "WHAT WAS MISSING"),
            ("presubmission", "PRE-SUBMISSION REPRODUCIBILITY CHECK"),
        ):
            assert run([command, digests[0]]) == 0, (accession, command)
            assert expected in capsys.readouterr().out, (accession, command)


@pytest.mark.parametrize("command", ["dossier", "bundle"])
def test_the_ingested_and_reconstructed_views_load_for_a_certified_entry(command, capsys) -> None:
    accession = sorted(
        path.stem for path in (_DATASETS / "milestone" / "certificates").glob("*.json")
    )[0]
    assert run([command, accession]) == 0
    assert capsys.readouterr().out.strip()


def test_the_blind_track_record_reads_the_committed_report(capsys) -> None:
    """The one number a reader is likeliest to quote, from the data rather than from a literal."""
    assert run(["self-validation", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    committed = json.loads(
        (_DATASETS / "milestone" / "agreement_report.json").read_text(encoding="utf-8")
    )
    # The PK/PD class's own row is the report this directory holds; the overall block aggregates
    # all six, so only this row is comparable against it.
    pkpd = printed["by_class"]["ode-pkpd"]
    assert pkpd["total"] == committed["total"]
    assert pkpd["agreements"] == committed["agreements"]
    assert pkpd["disagreements"] == committed["disagreements"]
    assert pkpd["confusion"] == committed["confusion"]


def test_the_backlog_reads_without_a_data_dir(capsys) -> None:
    assert run(["backlog"]) == 0
    assert capsys.readouterr().out.strip()
