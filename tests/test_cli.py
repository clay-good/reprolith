"""The human-facing CLI over the read-only query surface (parity with the MCP surface).

Pure stdlib, no engine: the CLI reads persisted certificates and formats them, computing no
verdict of its own. Each test drives ``run()`` end to end against a temp data directory built
the same way the milestone run writes one, so the loading path is exercised too.
"""

from __future__ import annotations

import json
import zipfile
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
                            source_location="Fig 2", discrepancy="off by 40%",
                            root_cause="parameter-value-mismatch"),
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
    # The root cause, not the discrepancy: the gap report names *why* a claim missed, and every
    # certificate a judge produces carries one (the builder now refuses a non-pass without it), so
    # this fixture previously fell through to the discrepancy only by being unrealistic.
    assert "parameter-value-mismatch" in out


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
    # PK/PD's non-agreements are abstentions or partials, never a verdict contradicting a label.
    # It had one agreement for the first time when the mouse oral-dose entry came back cleanly
    # `reproduced`; before that the class had none, and the two human entries are partial because
    # they rest on a load-bearing assumption. Counted from the report itself, because both of
    # these move as claims land.
    pkpd = report["by_class"]["ode-pkpd"]
    assert pkpd["agreements"] >= 1
    assert pkpd["matched"] + pkpd["abstained"] + pkpd["other"] == pkpd["total"]
    entries = json.loads(
        (Path(__file__).parent.parent / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8")
    )["entries"]
    # Every entry without extracted claims abstains, and every entry with them is certified — so
    # the abstention count is the seeded set minus the claims dataset, and it falls as claims land.
    assert overall["abstentions"] == pkpd["total"] - len(entries)
    assert pkpd["abstained"] == pkpd["total"] - len(entries)


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


def test_status_says_what_a_blocked_paper_is_blocked_on(tmp_path, capsys):
    """`missing_inputs` reached the JSON an agent receives and never the terminal.

    A BLOCKED transition is *required* to carry a non-empty `missing_inputs` — what is missing is
    the whole point of the state — and 30 of the 31 shipped entries are blocked. The human surface
    printed only the transition's `reason`, which for the whole committed corpus is "blind run", so
    a reader at a terminal learned that a paper stalled and could never learn what would unstall it.
    """
    from reprolith.enums import LifecycleState
    from reprolith.enums import ModelClass as _ModelClass

    catalog = Catalog()
    entry = catalog.add(Identifiers(title="A stalled paper", accession="ACC9"), _ModelClass.ODE_PKPD)
    entry.transition(LifecycleState.INGESTING, reason="blind run", at=0.0, actor="test")
    entry.transition(
        LifecycleState.BLOCKED,
        reason="blind run",
        at=1.0,
        actor="test",
        missing_inputs=("the paper's targetable claims were never extracted",),
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "catalog.json").write_text(json.dumps(catalog.to_dict()), encoding="utf-8")

    assert run(["--data-dir", str(repo), "status", "ACC9"]) == 0
    out = capsys.readouterr().out
    assert "the paper's targetable claims were never extracted" in out


_EXPORT_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="two_compartment">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="central" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.3" constant="true"/></listOfParameters>
  </model>
</sbml>
"""


def _write_exportable_bundle(repo: Path) -> Path:
    """Replace the stub bundle with a real one, and drop the model it names beside it."""
    from reprolith import ModelArtifact, RecipeStep, ReconstructionBundle

    model = repo / "two_compartment.xml"
    model.write_text(_EXPORT_MODEL, encoding="utf-8")
    bundle = ReconstructionBundle(
        entry="ACC1",
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        model=ModelArtifact(filename="models/two_compartment.xml", detected_format="sbml"),
        recipe=(
            RecipeStep(claim_id="AUC", protocol="Table 1", output="[central]",
                       time_span="0-24.0", steps=480),
            RecipeStep(claim_id="Cmax", protocol="Fig 2", output="[central]",
                       time_span="0-24.0", steps=480, parameter_overrides=(("k", 0.6),)),
        ),
    )
    (repo / "bundles" / "ACC1.json").write_text(
        json.dumps(bundle.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return model


def test_export_writes_a_runnable_archive(tmp_path, capsys):
    """The one command that writes: a published reconstruction becomes a file any tool can open."""
    repo, _ = _write_repo(tmp_path)
    model = _write_exportable_bundle(repo)
    out = tmp_path / "reconstruction.omex"

    assert run(["--data-dir", str(repo), "export", "ACC1",
                "--model", str(model), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "claims expressed: AUC, Cmax" in printed
    assert "not expressed" not in printed

    import zipfile

    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import ingest_omex, parse_sedml_recipes
    with zipfile.ZipFile(out) as archive:
        members = set(archive.namelist())
        sedml = archive.read("experiment.sedml").decode("utf-8")
    # The archive names the model by the file the *bundle* records, not by where the caller keeps it.
    assert members == {"manifest.xml", "two_compartment.xml", "experiment.sedml"}
    assert [r.duration for r in parse_sedml_recipes(sedml)] == [24.0]
    assert ingest_omex(out.read_bytes(), entry="ACC1").state_variables == ("central",)


def test_export_json_reports_what_it_wrote_and_what_it_could_not(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    model = _write_exportable_bundle(repo)
    out = tmp_path / "r.omex"

    assert run(["--data-dir", str(repo), "export", "ACC1",
                "--model", str(model), "--out", str(out), "--json"]) == 0
    reported = json.loads(capsys.readouterr().out)
    assert reported["expressed"] == ["AUC", "Cmax"]
    assert reported["unexpressed"] == []
    assert reported["bytes"] == out.stat().st_size


def test_export_refuses_a_model_the_bundle_was_not_built_from(tmp_path, capsys):
    """An archive built from another model packages a run the certificate never judged."""
    repo, _ = _write_repo(tmp_path)
    _write_exportable_bundle(repo)
    other = tmp_path / "something_else.xml"
    other.write_text(_EXPORT_MODEL, encoding="utf-8")

    assert run(["--data-dir", str(repo), "export", "ACC1",
                "--model", str(other), "--out", str(tmp_path / "r.omex")]) == 1
    assert "never judged" in capsys.readouterr().err
    assert not (tmp_path / "r.omex").exists()


def test_export_of_an_unknown_accession_says_so(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    model = _write_exportable_bundle(repo)
    assert run(["--data-dir", str(repo), "export", "NOPE",
                "--model", str(model), "--out", str(tmp_path / "r.omex")]) == 1
    assert "no bundle for accession: NOPE" in capsys.readouterr().err


def test_export_of_an_unreadable_model_is_a_message_not_a_traceback(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    _write_exportable_bundle(repo)
    assert run(["--data-dir", str(repo), "export", "ACC1",
                "--model", str(tmp_path / "two_compartment.xml") + ".missing",
                "--out", str(tmp_path / "r.omex")]) == 1
    assert "cannot read the model" in capsys.readouterr().err


def test_archive_check_reports_and_exits_on_readiness(tmp_path, capsys):
    """The exit code answers the question the command asks: an author wiring this into a
    pre-submission hook needs "is this ready" to be actionable."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml, build_omex_archive

    model = _EXPORT_MODEL
    archive = tmp_path / "a.omex"
    archive.write_bytes(
        build_omex_archive(model, build_experiment_sedml(model, duration=24.0, steps=240))
    )
    assert run(["archive-check", str(archive)]) == 1  # reports columns, states no published result
    printed = capsys.readouterr().out
    assert "ARCHIVE REPRODUCIBILITY CHECK" in printed
    assert "This certificate attests" not in printed


def test_archive_check_json_is_the_report_object(tmp_path, capsys):
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml, build_omex_archive

    archive = tmp_path / "a.omex"
    archive.write_bytes(
        build_omex_archive(
            _EXPORT_MODEL, build_experiment_sedml(_EXPORT_MODEL, duration=24.0, steps=240)
        )
    )
    assert run(["archive-check", str(archive), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ready_to_submit"] is False
    assert "issues no certificate" in report["note"]


def test_archive_check_reads_the_paper_claims_it_is_given(tmp_path, capsys):
    """The archive runs the model's own dose; a claim at another one is the finding."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml, build_omex_archive

    archive = tmp_path / "a.omex"
    archive.write_bytes(
        build_omex_archive(
            _EXPORT_MODEL, build_experiment_sedml(_EXPORT_MODEL, duration=24.0, steps=240)
        )
    )
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": [{
        "claim_id": "peak", "quantity": "peak", "species": "central", "reported": 1.0,
        "source_location": "Table 1", "parameter_overrides": {"k": 99.0},
    }]}), encoding="utf-8")

    assert run(["archive-check", str(archive), "--claims", str(claims), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["found"]["manuscript_claims_checked"] == 1
    assert [item["kind"] for item in report["fix_list"]].count("manuscript") == 1


def test_archive_check_names_the_papers_when_a_claims_file_holds_several(tmp_path, capsys):
    archive = tmp_path / "a.omex"
    archive.write_bytes(b"not a zip")
    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps({"entries": {"A": {"claims": []}, "B": {"claims": []}}}), encoding="utf-8"
    )
    assert run(["archive-check", str(archive), "--claims", str(claims)]) == 1
    error = capsys.readouterr().err
    assert "--accession" in error and "A, B" in error


def test_archive_check_of_a_missing_claims_file_is_a_message(tmp_path, capsys):
    archive = tmp_path / "a.omex"
    archive.write_bytes(b"not a zip")
    assert run(["archive-check", str(archive), "--claims", str(tmp_path / "nope.json")]) == 1
    assert "cannot read the claims" in capsys.readouterr().err


def test_archive_check_reads_a_loose_document_and_model(tmp_path, capsys):
    """No packaging required: most papers ship the two files loose."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml

    model = tmp_path / "model.xml"
    model.write_text(_EXPORT_MODEL, encoding="utf-8")
    document = tmp_path / "experiment.sedml"
    document.write_text(
        build_experiment_sedml(_EXPORT_MODEL, duration=24.0, steps=240), encoding="utf-8"
    )
    assert run(["archive-check", "--sedml", str(document), "--model", str(model), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["found"]["assembled_from_loose_files"] is True
    assert {a["detected_format"] for a in report["found"]["files"]} == {"sbml", "sed-ml"}


def test_archive_check_wants_either_an_archive_or_both_loose_files(tmp_path, capsys):
    assert run(["archive-check", "--sedml", str(tmp_path / "a.sedml")]) == 1
    assert "either an archive or both" in capsys.readouterr().err


def test_archive_check_of_a_missing_file_is_a_message(tmp_path, capsys):
    assert run(["archive-check", str(tmp_path / "nope.omex")]) == 1
    assert "cannot read the archive" in capsys.readouterr().err


def test_only_the_file_commands_sit_outside_the_query_surface():
    """Parity is the repository's central claim, so its exceptions are pinned rather than assumed.

    `export` and `archive-check` act on a file the MCP server has no path to, and both are written
    up in docs/mcp-server.md with the reason. A further command joining them means that question
    was not asked, so this fails until it is.
    """
    import argparse

    from reprolith.cli import build_parser

    parser = build_parser()
    subcommands = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    ).choices
    named = {
        "export", "archive-check", "claims-template", "claims-check", "claims-propose",
        "params-check", "figure-check", "figure-template",
    }
    file_based = {name for name in subcommands if name in named}
    assert file_based == named
    documented = (
        Path(__file__).parent.parent / "docs" / "mcp-server.md"
    ).read_text(encoding="utf-8")
    for name in file_based:
        assert f"reprolith {name}" in documented, f"{name} is not explained in docs/mcp-server.md"
    # Everything else must be reachable as an MCP tool name or be a pure formatting view of one.
    on_the_query_surface = set(subcommands) - file_based
    assert on_the_query_surface == {
        "backlog", "bundle", "catalog", "certificate", "certificates-for", "dossier", "gaps",
        "presubmission", "self-validation", "status", "verdict",
    }


def test_export_to_a_path_it_cannot_write_is_a_message(tmp_path, capsys):
    """A directory, a missing parent, a read-only location: ordinary mistakes for the only
    command here that writes, and a traceback is not an answer to any of them."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    repo, _ = _write_repo(tmp_path)
    model = _write_exportable_bundle(repo)
    target = tmp_path / "a-directory"
    target.mkdir()
    assert run(["--data-dir", str(repo), "export", "ACC1", "--model", str(model),
                "--out", str(target)]) == 1
    assert "cannot write the archive" in capsys.readouterr().err


def test_export_says_when_it_replaced_a_file(tmp_path, capsys):
    """It is the one command that destroys something, and the person running it finds out here
    rather than later."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    repo, _ = _write_repo(tmp_path)
    model = _write_exportable_bundle(repo)
    out = tmp_path / "archive.omex"

    assert run(["--data-dir", str(repo), "export", "ACC1", "--model", str(model),
                "--out", str(out)]) == 0
    assert "replacing" not in capsys.readouterr().out

    assert run(["--data-dir", str(repo), "export", "ACC1", "--model", str(model),
                "--out", str(out)]) == 0
    assert "replacing what was there" in capsys.readouterr().out


def test_claims_template_writes_a_file_with_the_blanks_left_to_fill(tmp_path, capsys):
    """The command that closes the loop: the check needs a claims file, this writes one."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml

    model = tmp_path / "m.xml"
    model.write_text(_EXPORT_MODEL, encoding="utf-8")
    document = tmp_path / "m.sedml"
    document.write_text(
        build_experiment_sedml(_EXPORT_MODEL, duration=24.0, steps=240), encoding="utf-8"
    )
    out = tmp_path / "claims.json"

    assert run(["claims-template", "--model", str(model), "--sedml", str(document),
                "--out", str(out)]) == 0
    assert "wrote" in capsys.readouterr().out
    written = json.loads(out.read_text(encoding="utf-8"))
    assert all(c["reported"] is None for c in written["claims"])
    assert written["readable_outputs"]


def test_claims_template_without_a_document_writes_no_claims(tmp_path, capsys):
    """A model says what can be read, never what the paper showed."""
    model = tmp_path / "m.xml"
    model.write_text(_EXPORT_MODEL, encoding="utf-8")
    assert run(["claims-template", "--model", str(model)]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["claims"] == []
    assert written["notes"]


def test_claims_template_needs_exactly_one_source(tmp_path, capsys):
    assert run(["claims-template"]) == 1
    assert "either an archive or --model" in capsys.readouterr().err


def test_claims_template_of_an_unreadable_model_is_a_message(tmp_path, capsys):
    model = tmp_path / "m.xml"
    model.write_text("not xml at all", encoding="utf-8")
    assert run(["claims-template", "--model", str(model)]) == 1
    assert "cannot read the model" in capsys.readouterr().err


def test_claims_check_reports_a_value_the_cited_table_does_not_print(tmp_path, capsys):
    """The command form of the check that would have caught the corpus's one wrong value."""
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [["Plasma", "500", "6.1"]]}}}),
                      encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": [{
        "claim_id": "Cmax", "quantity": "peak", "species": "p", "reported": 6.2,
        "source_location": "Table 6, plasma row",
    }]}), encoding="utf-8")

    assert run(["claims-check", "--claims", str(claims), "--tables", str(tables)]) == 1
    printed = capsys.readouterr().out
    assert "NOT FOUND" in printed and "6.2 is not printed in Table 6" in printed


def test_claims_check_passes_a_value_the_table_prints(tmp_path, capsys):
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [["Plasma", "500", "6.1"]]}}}),
                      encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": [{
        "claim_id": "Cmax", "quantity": "peak", "species": "p", "reported": 6.1,
        "source_location": "Table 6, plasma row",
    }]}), encoding="utf-8")
    assert run(["claims-check", "--claims", str(claims), "--tables", str(tables)]) == 0
    assert "ok:" in capsys.readouterr().out


def test_claims_check_does_not_fail_on_a_claim_it_cannot_check(tmp_path, capsys):
    """A value read from a figure is unchecked, not wrong, and must not fail a submission hook."""
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [["Plasma", "6.1"]]}}}),
                      encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": [{
        "claim_id": "Cmax", "quantity": "peak", "species": "p", "reported": 9.9,
        "source_location": "Figure 3B",
    }]}), encoding="utf-8")
    assert run(["claims-check", "--claims", str(claims), "--tables", str(tables)]) == 0
    assert "not checked" in capsys.readouterr().out


def test_claims_check_of_a_tables_file_with_no_tables_is_a_message(tmp_path, capsys):
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {}}), encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": []}), encoding="utf-8")
    assert run(["claims-check", "--claims", str(claims), "--tables", str(tables)]) == 1
    assert "holds no tables" in capsys.readouterr().err


def test_claims_propose_writes_candidates_from_a_papers_tables(tmp_path, capsys):
    """The paper half of a claims file: every number a table prints, none of them a claim yet."""
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [
        ["Tissue", "Dose, mg", "Cmax, nmol/mL"],
        ["Plasma", "500", "6.1"],
    ]}}}), encoding="utf-8")
    out = tmp_path / "candidates.json"
    assert run(["claims-propose", "--tables", str(tables), "--out", str(out)]) == 0
    assert "1 candidate(s)" in capsys.readouterr().out
    written = json.loads(out.read_text(encoding="utf-8"))
    (candidate,) = written["candidates"]
    assert candidate["reported"] == 6.1 and candidate["species"] == ""
    assert candidate["metric"] == "cmax"


def test_claims_propose_of_a_tables_file_with_no_tables_is_a_message(tmp_path, capsys):
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {}}), encoding="utf-8")
    assert run(["claims-propose", "--tables", str(tables)]) == 1
    assert "holds no tables" in capsys.readouterr().err


def test_claims_propose_output_is_checkable_against_the_same_tables(tmp_path, capsys):
    """The two halves compose: what it proposes, `claims-check` confirms is in the paper."""
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [
        ["Tissue", "Dose, mg", "Cmax, nmol/mL"],
        ["Plasma", "500", "6.1"],
    ]}}}), encoding="utf-8")
    proposed = tmp_path / "candidates.json"
    assert run(["claims-propose", "--tables", str(tables), "--out", str(proposed)]) == 0
    picked = json.loads(proposed.read_text(encoding="utf-8"))["candidates"]
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": picked}), encoding="utf-8")
    assert run(["claims-check", "--claims", str(claims), "--tables", str(tables)]) == 0
    assert "ok:" in capsys.readouterr().out


def test_a_candidates_file_is_read_by_the_checks_without_a_rename(tmp_path, capsys):
    """`claims-propose` writes `candidates` on purpose; the checks read both keys."""
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [
        ["Tissue", "Cmax, nmol/mL"], ["Plasma", "6.1"],
    ]}}}), encoding="utf-8")
    out = tmp_path / "candidates.json"
    assert run(["claims-propose", "--tables", str(tables), "--out", str(out)]) == 0
    capsys.readouterr()
    assert run(["claims-check", "--claims", str(out), "--tables", str(tables)]) == 0
    assert "ok:" in capsys.readouterr().out


def test_an_unedited_candidates_file_is_refused_for_the_reason_that_applies(tmp_path, capsys):
    """Not "no 'claims' key" — the model output nobody has named yet."""
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [
        ["Tissue", "Cmax, nmol/mL"], ["Plasma", "6.1"],
    ]}}}), encoding="utf-8")
    out = tmp_path / "candidates.json"
    assert run(["claims-propose", "--tables", str(tables), "--out", str(out)]) == 0
    capsys.readouterr()
    archive = tmp_path / "a.omex"
    archive.write_bytes(b"not a zip")
    assert run(["archive-check", str(archive), "--claims", str(out)]) == 1
    assert "'species' is blank" in capsys.readouterr().err


def test_a_file_with_no_claims_key_says_what_it_found(tmp_path, capsys):
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"stuff": []}), encoding="utf-8")
    archive = tmp_path / "a.omex"
    archive.write_bytes(b"not a zip")
    assert run(["archive-check", str(archive), "--claims", str(claims)]) == 1
    error = capsys.readouterr().err
    assert "holds no claims" in error and "stuff" in error


def test_params_check_reports_a_value_the_model_does_not_carry(tmp_path, capsys):
    """The model-side counterpart of claims-check: the paper's Table 3 says 0.7 and the deposit
    says 9.9, which every reproduction in the corpus would pass without noticing."""
    model = tmp_path / "model.xml"
    model.write_text(
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level2/version4" '
        'level="2" version="4"><model id="m"><listOfParameters>'
        '<parameter id="Ktp_Liver" value="9.9"/></listOfParameters></model></sbml>',
        encoding="utf-8",
    )
    parameters = tmp_path / "parameters.json"
    parameters.write_text(json.dumps({"parameters": [
        {"parameter": "Ktp_Liver", "reported": 0.7, "source_location": "Table 3, Liver row"},
    ]}), encoding="utf-8")

    assert run(["params-check", "--model", str(model), "--parameters", str(parameters)]) == 1
    printed = capsys.readouterr().out
    assert "MISMATCH" in printed and "not 0.7" in printed


def test_params_check_does_not_fail_on_a_value_it_could_not_compare(tmp_path, capsys):
    """An inert value was not compared, and a submission hook must not read that as wrong."""
    model = tmp_path / "model.xml"
    model.write_text(
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level2/version4" '
        'level="2" version="4"><model id="m"><listOfParameters>'
        '<parameter id="k" value="9.9"/></listOfParameters><listOfInitialAssignments>'
        '<initialAssignment symbol="k"><math '
        'xmlns="http://www.w3.org/1998/Math/MathML"><cn>1</cn></math></initialAssignment>'
        '</listOfInitialAssignments></model></sbml>',
        encoding="utf-8",
    )
    parameters = tmp_path / "parameters.json"
    parameters.write_text(json.dumps({"parameters": [
        {"parameter": "k", "reported": 0.7, "source_location": "Table 3"},
    ]}), encoding="utf-8")
    assert run(["params-check", "--model", str(model), "--parameters", str(parameters)]) == 0
    printed = capsys.readouterr().out
    assert "not compared" in printed and "MISMATCH" not in printed


def test_params_check_on_something_that_is_not_sbml_is_a_message(tmp_path, capsys):
    model = tmp_path / "model.xml"
    model.write_text("not xml at all", encoding="utf-8")
    parameters = tmp_path / "parameters.json"
    parameters.write_text(json.dumps({"parameters": []}), encoding="utf-8")
    assert run(["params-check", "--model", str(model), "--parameters", str(parameters)]) == 1
    assert "cannot read the model" in capsys.readouterr().err


def test_figure_check_reads_a_digitization_and_reports_what_it_rests_on(tmp_path, capsys):
    """The curator's file, before it is used as anybody's reference: what it says and how coarse
    it is. The widest gap is reported and not judged — between two readings the reference is the
    curator's straight line, and how much of a comparison rests on that is theirs to weigh."""
    series = tmp_path / "figure3a.json"
    series.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "fig3a-plasma", "curve": "plasma",
                    "points": [[0, 0.5], [2, 6.0], [24, 1.0]]}],
    }), encoding="utf-8")

    assert run(["figure-check", "--series", str(series)]) == 0
    printed = capsys.readouterr().out
    assert "fig3a-plasma" in printed and "3 point(s) over 0.0-24.0 h" in printed
    assert "92% of the span" in printed
    assert "no model was run" in printed


def test_figure_check_refuses_a_reading_off_its_own_axes(tmp_path, capsys):
    """A mis-calibrated digitization is smooth, ordered, and wrong; this is where it stops."""
    series = tmp_path / "figure3a.json"
    series.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "fig3a-plasma", "curve": "plasma",
                    "points": [[0, 0.5], [2, 60.0], [24, 10.0]]}],
    }), encoding="utf-8")

    assert run(["figure-check", "--series", str(series)]) == 1
    assert "outside its own axis" in capsys.readouterr().err


def test_figure_check_of_a_missing_file_is_a_message(tmp_path, capsys):
    assert run(["figure-check", "--series", str(tmp_path / "nope.json")]) == 1
    assert "cannot read the digitization" in capsys.readouterr().err


def test_figure_template_writes_the_pairing_nobody_could_guess(tmp_path, capsys):
    """A claim id off a SED-ML document is `plot_0__plot_0_0_0__plot_0_0_1` and has to match
    exactly, so the template writes the ids and the curve each plots — and nothing that is a
    reading: the figure, the tool, both axis ranges and every point stay blank."""
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    out = tmp_path / "figure.json"
    assert run(["figure-template", "--sedml", str(sedml), "--out", str(out)]) == 0
    assert "4 curve(s) to read off your figure" in capsys.readouterr().out

    written = json.loads(out.read_text(encoding="utf-8"))
    assert [s["claim"] for s in written["series"]] == [
        "plot_0__plot_0_0_0__plot_0_0_1", "plot_0__plot_0_0_0__plot_0_1_1",
        "plot_1__plot_1_0_0__plot_1_0_1", "plot_1__plot_1_0_0__plot_1_1_1",
    ]
    assert all(s["points"] == [] for s in written["series"])
    assert written["figure"] == "" and written["digitizer"] == ""
    assert written["x_axis"]["minimum"] is None and written["y_axis"]["unit"] == ""


def test_a_template_handed_straight_back_is_told_what_is_left_to_write(tmp_path, capsys):
    """Reading it would refuse on whichever blank it reached first, which says nothing about the
    other four. Every blank is named, and the command is the one that names them."""
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    out = tmp_path / "figure.json"
    run(["figure-template", "--sedml", str(sedml), "--out", str(out)])
    capsys.readouterr()

    assert run(["figure-check", "--series", str(out)]) == 1
    error = capsys.readouterr().err
    assert "has not been filled in yet" in error
    for blank in ("'figure' is blank", "'digitizer' is blank", "'x_axis.minimum' is blank",
                  "'y_axis.unit' is blank", "has no points"):
        assert blank in error


def test_figure_template_from_a_document_that_is_not_one_is_a_message(tmp_path, capsys):
    bad = tmp_path / "not.sedml"
    bad.write_text("<not-sedml", encoding="utf-8")
    assert run(["figure-template", "--sedml", str(bad)]) == 1
    assert "cannot read the document" in capsys.readouterr().err


_SPEC = "http://identifiers.org/combine.specifications/"


def test_figure_template_reads_the_document_out_of_an_archive_too(tmp_path, capsys):
    """A curator with a .omex should not have to unzip it to learn the ids they must pair to —
    the same affordance `claims-template` has, on the file beside it."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    kinetic = Path(__file__).parent.parent / "datasets" / "kinetic"
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{_SPEC}omex-manifest">
  <content location="." format="{_SPEC}omex"/>
  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>
  <content location="./BIOMD0000000010_url.xml" format="{_SPEC}sbml.level-2.version-4"/>
  <content location="./BIOMD0000000010.sedml" format="{_SPEC}sed-ml.level-1.version-4" master="true"/>
</omexManifest>
"""
    archive = tmp_path / "model.omex"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.xml", manifest)
        zf.writestr(
            "BIOMD0000000010_url.xml",
            (kinetic / "BIOMD0000000010.xml").read_text(encoding="utf-8"),
        )
        zf.writestr(
            "BIOMD0000000010.sedml",
            (kinetic / "BIOMD0000000010.sedml").read_text(encoding="utf-8"),
        )

    out = tmp_path / "figure.json"
    assert run(["figure-template", str(archive), "--out", str(out)]) == 0
    packaged = json.loads(out.read_text(encoding="utf-8"))

    loose = tmp_path / "loose.json"
    run(["figure-template", "--sedml", str(kinetic / "BIOMD0000000010.sedml"), "--out", str(loose)])
    # The two forms cannot reach different pairings: it is the same document either way.
    assert packaged == json.loads(loose.read_text(encoding="utf-8"))


def test_figure_template_needs_exactly_one_of_the_two_forms(capsys):
    assert run(["figure-template"]) == 1
    assert "either an archive or --sedml" in capsys.readouterr().err


def test_figure_template_from_an_archive_with_no_document_says_so(tmp_path, capsys):
    """Which curves a paper shows is the document's statement, and there is no document."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    kinetic = Path(__file__).parent.parent / "datasets" / "kinetic"
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{_SPEC}omex-manifest">
  <content location="." format="{_SPEC}omex"/>
  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>
  <content location="./model.xml" format="{_SPEC}sbml.level-2.version-4" master="true"/>
</omexManifest>
"""
    archive = tmp_path / "model-only.omex"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.xml", manifest)
        zf.writestr("model.xml", (kinetic / "BIOMD0000000010.xml").read_text(encoding="utf-8"))

    assert run(["figure-template", str(archive)]) == 1
    assert "ships no simulation document" in capsys.readouterr().err
