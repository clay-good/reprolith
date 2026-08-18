"""The human-facing CLI over the read-only query surface (parity with the MCP surface).

Pure stdlib, no engine: the CLI reads persisted certificates and formats them, computing no
verdict of its own. Each test drives ``run()`` end to end against a temp data directory built
the same way the milestone run writes one, so the loading path is exercised too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    Assumption,
    Catalog,
    ClaimAssessment,
    EnginePin,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    build_certificate,
    certificate_digest,
)
from reprolith.cli import run
from reprolith.mcp_server import dispatch_tool, load_repository


def _write_repo(tmp_path: Path) -> tuple[Path, str]:
    """Write a catalog + one certificate the way the milestone run does; return dir and digest."""
    catalog = Catalog()
    catalog.add(
        Identifiers(title="Two-compartment PK model", doi="10.1/x", accession="ACC1"),
        ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="curation"),
    )
    (tmp_path / "catalog.json").write_text(
        json.dumps(catalog.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    cert = build_certificate(
        paper=PaperIdentity(title="Two-compartment PK model", doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[
            ClaimAssessment(claim_id="AUC", quantity="area under curve", verdict=Verdict.REPRODUCED,
                            source_location="Table 1"),
            ClaimAssessment(claim_id="Cmax", quantity="peak concentration", verdict=Verdict.FAILED,
                            source_location="Fig 2", discrepancy="off by 40%"),
        ],
        assumptions=[Assumption(id="a1", description="dose is the salt form", chosen="free base",
                                basis="convention", attributed_to="reprolith", load_bearing=True)],
    )
    digest = certificate_digest(cert)
    certs = tmp_path / "certificates"
    certs.mkdir()
    (certs / f"{digest}.json").write_text(
        json.dumps(cert.content(), indent=2, sort_keys=True), encoding="utf-8"
    )
    # A dossier and a reconstruction bundle keyed by the entry accession, as the milestone writes.
    for kind in ("dossiers", "bundles"):
        (tmp_path / kind).mkdir()
        (tmp_path / kind / "ACC1.json").write_text(
            json.dumps({"accession": "ACC1", "kind": kind}, sort_keys=True), encoding="utf-8"
        )
    return tmp_path, digest


def test_catalog_lists_entries(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "catalog"]) == 0
    out = capsys.readouterr().out
    assert "ACC1" in out
    assert "Two-compartment PK model" in out
    assert "1 entry" in out


def test_catalog_json_matches_mcp(tmp_path, capsys):
    """--json emits exactly what the MCP tool returns — the two surfaces cannot diverge."""
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "catalog", "--json"]) == 0
    cli_json = json.loads(capsys.readouterr().out)
    query, _ = load_repository(repo)
    assert cli_json == dispatch_tool(query, "list_catalog", {})


def test_certificate_human_render(tmp_path, capsys):
    repo, digest = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "certificate", digest]) == 0
    out = capsys.readouterr().out
    assert "REPRODUCTION CERTIFICATE" in out
    assert "OVERALL: partially-reproduced" in out  # one reproduced + one failed
    assert "SCOPE" in out  # the scope statement is inescapable in the human form


def test_verdict_carries_scope(tmp_path, capsys):
    repo, digest = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "verdict", digest]) == 0
    out = capsys.readouterr().out
    assert "OVERALL: partially-reproduced" in out
    assert "no claim about biological correctness" in out  # scope always travels


def test_gaps_report(tmp_path, capsys):
    repo, digest = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "gaps", digest]) == 0
    out = capsys.readouterr().out
    assert "WHAT WAS MISSING" in out
    assert "off by 40%" in out


def test_backlog_health(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "backlog"]) == 0
    out = capsys.readouterr().out
    assert "1 entries" in out or "1 entry" in out or "Backlog: 1" in out


def test_status_by_accession(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "status", "ACC1"]) == 0
    out = capsys.readouterr().out
    assert "Two-compartment PK model" in out


def test_status_bridges_accession_to_certificate(tmp_path, capsys):
    """status resolves an entry by accession and surfaces its certificate digest — no dead end."""
    repo, digest = _write_repo(tmp_path)  # the catalog entry (ACC1) and the cert share title/doi
    assert run(["--data-dir", str(repo), "status", "ACC1"]) == 0
    out = capsys.readouterr().out
    assert "certificates:" in out
    assert digest in out


def test_certificates_for_by_title(tmp_path, capsys):
    repo, digest = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "certificates-for",
                "Two-compartment PK model", "--by", "title"]) == 0
    assert digest in capsys.readouterr().out


def test_unknown_digest_exits_nonzero(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "verdict", "nope"]) == 1
    assert "unknown digest" in capsys.readouterr().err


def test_unknown_paper_exits_nonzero(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "status", "MISSING"]) == 1
    assert "unknown paper" in capsys.readouterr().err


def test_self_validation_default_view(capsys):
    """The default view (no --data-dir) reports the honest blind track record across classes."""
    assert run(["self-validation"]) == 0
    out = capsys.readouterr().out
    assert "BLIND SELF-VALIDATION" in out
    # every class that shipped a milestone appears
    for label in ("constraint-based", "kinetic", "logical", "ode-pkpd", "spatial", "stochastic"):
        assert label in out
    # abstentions are named as such, never folded into "wrong"
    assert "honest abstentions" in out
    assert "not a wrong verdict" in out


def test_self_validation_json_splits_abstentions(capsys):
    assert run(["self-validation", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    overall = report["overall"]
    # matched + abstentions + other must partition the labelled entries exactly
    assert (overall["agreements"] + overall["abstentions"] + overall["other_disagreements"]
            == overall["labelled_entries"])
    # a single blended agreement_rate must NOT be presented — it would misrepresent abstentions
    assert "agreement_rate" not in overall
    # PK/PD's disagreements are abstentions, not wrong verdicts (the "0 wrong verdicts" story)
    pkpd = report["by_class"]["ode-pkpd"]
    assert pkpd["agreements"] == 0
    assert overall["abstentions"] >= 30


def test_presubmission_report(tmp_path, capsys):
    repo, digest = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "presubmission", digest]) == 0
    report = json.loads(capsys.readouterr().out)
    # a partial certificate is never reported ready to submit, and scope always travels
    assert report["ready_to_submit"] is False
    assert "clinical" in json.dumps(report).lower()


def test_presubmission_unknown_digest_exits_nonzero(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "presubmission", "nope"]) == 1
    assert "unknown digest" in capsys.readouterr().err


def test_dossier_and_bundle(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "dossier", "ACC1"]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "dossiers"
    assert run(["--data-dir", str(repo), "bundle", "ACC1"]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "bundles"


def test_dossier_unknown_accession_exits_nonzero(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "dossier", "MISSING"]) == 1
    assert "no dossier" in capsys.readouterr().err


def test_command_required(capsys):
    with pytest.raises(SystemExit):
        run([])


def test_package_is_runnable_as_a_module() -> None:
    # `python -m reprolith` must reach the same entry point as the console script, so the terminal
    # surface works without the installed script on PATH.
    import reprolith.__main__ as entry
    from reprolith.cli import main

    assert entry.main is main


def test_every_read_command_accepts_the_documented_json_flag(tmp_path, capsys):
    """The docs promise --json on any read command; three of them used to exit 2 on it."""
    repo, digest = _write_repo(tmp_path)
    for argv in (
        ["presubmission", digest], ["dossier", "ACC1"], ["bundle", "ACC1"],
        ["catalog"], ["backlog"], ["self-validation"], ["certificate", digest],
        ["verdict", digest], ["gaps", digest], ["status", "ACC1"], ["certificates-for", "ACC1"],
    ):
        assert run(["--data-dir", str(repo), *argv, "--json"]) == 0, argv
        json.loads(capsys.readouterr().out)  # and what it prints is really JSON


def test_gaps_prints_the_scope_even_when_nothing_was_missing(capsys, tmp_path) -> None:
    """"Nothing was missing" was the one published line that stood alone, without its scope."""
    cert = build_certificate(
        paper=PaperIdentity(title="clean", doi="10.0/c"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[
            ClaimAssessment(claim_id="AUC", quantity="area under curve",
                            verdict=Verdict.REPRODUCED, source_location="Table 1"),
        ],
    )
    digest = certificate_digest(cert)
    (tmp_path / "catalog.json").write_text('{"entries": []}', encoding="utf-8")
    (tmp_path / "certificates").mkdir()
    (tmp_path / "certificates" / f"{digest}.json").write_text(
        json.dumps(cert.content(), indent=2, sort_keys=True), encoding="utf-8"
    )
    assert run(["--data-dir", str(tmp_path), "gaps", digest]) == 0
    out = capsys.readouterr().out
    assert "nothing was missing" in out
    assert "no claim about biological correctness" in out
