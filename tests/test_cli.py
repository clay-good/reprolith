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


def test_command_required(capsys):
    with pytest.raises(SystemExit):
        run([])
