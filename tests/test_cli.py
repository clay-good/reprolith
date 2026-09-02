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
    assert run(["--data-dir", str(repo), "presubmission", digest, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    # a partial certificate is never reported ready to submit, and scope always travels
    assert report["ready_to_submit"] is False
    assert "clinical" in json.dumps(report).lower()


def test_presubmission_reads_as_a_report_and_not_as_a_machine_view(tmp_path, capsys):
    """The one report written for an author to read was the one served to them as JSON.

    It printed the machine view whatever was asked, so `--json` changed nothing — while its sibling
    `archive-check`, which answers the same question before any certificate exists, has had a
    plain-text rendering from the start, and the renderer for this one existed, exported and
    tested, with no surface calling it.
    """
    repo, digest = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "presubmission", digest]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("PRE-SUBMISSION REPRODUCIBILITY CHECK")
    assert "FIX BEFORE YOU SUBMIT" in printed and "NOT YET READY" in printed
    # The scope travels into the rendering, as it does into every other published surface.
    assert "clinical" in printed
    # And it is a rendering, not a JSON dump that happens to start with a word.
    with pytest.raises(json.JSONDecodeError):
        json.loads(printed)


def test_presubmission_unknown_digest_exits_nonzero(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "presubmission", "nope"]) == 1
    assert "unknown digest" in capsys.readouterr().err


def test_dossier_and_bundle(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "dossier", "ACC1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "dossiers"
    assert run(["--data-dir", str(repo), "bundle", "ACC1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "bundles"


def test_dossier_and_bundle_read_as_pages_and_not_as_dumps(tmp_path, capsys):
    """Both printed their JSON whatever was asked, so `--json` changed nothing on either.

    The metformin dossier is ninety-five equations and thirty-seven values deep — a shape for a
    program to read, put in front of a person, with the gaps they are looking for at the end of it.
    """
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "dossier", "ACC1"]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("DOSSIER — ") and "WHAT WAS EXTRACTED" in printed
    assert "GAPS" in printed
    with pytest.raises(json.JSONDecodeError):
        json.loads(printed)

    assert run(["--data-dir", str(repo), "bundle", "ACC1"]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("RECONSTRUCTION BUNDLE — ")
    assert "origin:" in printed and "ASSUMPTIONS" in printed
    with pytest.raises(json.JSONDecodeError):
        json.loads(printed)


def test_dossier_unknown_accession_exits_nonzero(tmp_path, capsys):
    repo, _ = _write_repo(tmp_path)
    assert run(["--data-dir", str(repo), "dossier", "MISSING"]) == 1
    assert "no dossier" in capsys.readouterr().err


def test_version_names_the_revision_a_verdict_would_be_judged_under(capsys):
    """A release number answers "which version"; a certificate turns on the judge revision.

    Someone holding a certificate and asking whether their copy would still produce it needs the
    digest over the code that judged it, and there was no way to ask this tool for it at all.
    """
    with pytest.raises(SystemExit) as exited:
        run(["--version"])
    assert exited.value.code == 0
    printed = capsys.readouterr().out
    assert printed.startswith("reprolith ")
    from reprolith.pins import class_revisions

    revisions = class_revisions()
    assert revisions, "no classes to report; this check would pass vacuously"
    for name, revision in revisions.items():
        assert f"{name} {revision}" in printed
    # Printed as written rather than rewrapped into a paragraph of three facts.
    assert len(printed.splitlines()) == 3


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
        "params-check", "params-template", "figure-check", "figure-template",
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


def test_params_check_pairs_a_published_volume_with_its_compartment(tmp_path, capsys):
    """A PBPK table's tissue volumes are compartments and its initial conditions are species.

    Reading only the parameter list, the command answered a correct pairing with a mismatch against
    a model carrying the published number — and its "what you did not report" list could not see
    either kind at all.
    """
    model = tmp_path / "model.xml"
    model.write_text(
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level2/version4" '
        'level="2" version="4"><model id="m">'
        '<listOfCompartments><compartment id="Liver" size="1.51"/>'
        '<compartment id="Lumen" size="0.6"/></listOfCompartments>'
        '<listOfSpecies><species id="mLiver" compartment="Liver" initialAmount="0"/>'
        '</listOfSpecies>'
        '<listOfParameters><parameter id="Ktp_Liver" value="5.5"/></listOfParameters>'
        '</model></sbml>',
        encoding="utf-8",
    )
    parameters = tmp_path / "parameters.json"
    parameters.write_text(json.dumps({"parameters": [
        {"parameter": "Liver", "reported": 1.5, "source_location": "Table 2, Liver volume"},
    ]}), encoding="utf-8")

    assert run(["params-check", "--model", str(model), "--parameters", str(parameters)]) == 0
    printed = capsys.readouterr().out
    assert "MISMATCH" not in printed
    assert "the compartment carries 1.51" in printed
    # And what it could not check is named by kind, not folded into one list of "parameters".
    assert "3 settable value(s) your paper does not report" in printed
    assert "compartment: Lumen" in printed
    assert "species: mLiver" in printed
    assert "parameter: Ktp_Liver" in printed


def test_claims_check_also_checks_the_unit_when_it_is_given_a_model(tmp_path, capsys):
    """A number is a number of something. Comparing a claim in one unit against a model output in
    another is a verdict about arithmetic, and no check downstream of it can see that."""
    model = tmp_path / "model.xml"
    model.write_text(
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" '
        'level="3" version="2"><model id="m" substanceUnits="substance" volumeUnits="volume">'
        '<listOfUnitDefinitions>'
        '<unitDefinition id="volume"><listOfUnits>'
        '<unit kind="litre" exponent="1" scale="-3" multiplier="1"/></listOfUnits></unitDefinition>'
        '<unitDefinition id="substance"><listOfUnits>'
        '<unit kind="mole" exponent="1" scale="-9" multiplier="1"/></listOfUnits></unitDefinition>'
        '</listOfUnitDefinitions>'
        '<listOfCompartments><compartment id="Plasma" size="2247" units="volume"/>'
        '</listOfCompartments>'
        '<listOfSpecies><species id="mPlasma" compartment="Plasma" initialAmount="0" '
        'substanceUnits="substance"/></listOfSpecies></model></sbml>',
        encoding="utf-8",
    )
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps({"claims": [
        {"claim_id": "ok", "species": "mPlasma", "reported": 6.1, "reported_units": "nmol/mL",
         "source_location": "Table 6"},
        {"claim_id": "off", "species": "mPlasma", "reported": 6.1, "reported_units": "µmol/mL",
         "source_location": "Table 6"},
    ]}), encoding="utf-8")
    tables = tmp_path / "tables.json"
    tables.write_text(json.dumps({"tables": {"Table 6": {"rows": [["6.1"]]}}}), encoding="utf-8")

    # Without a model the unit is not checked at all, and the command says nothing about it.
    assert run(["claims-check", "--claims", str(claims), "--tables", str(tables)]) == 0
    assert "UNITS CHECKED" not in capsys.readouterr().out

    assert run([
        "claims-check", "--claims", str(claims), "--tables", str(tables), "--model", str(model),
    ]) == 1
    printed = capsys.readouterr().out
    assert "[ok] ok: nmol/mL is the unit the model reads that output in" in printed
    # A micromole is a thousand nanomoles, so the model's unit is a thousandth of the claim's.
    assert "[off] ANOTHER UNIT" in printed and "0.001 times as large" in printed


def test_params_template_writes_the_file_params_check_reads(tmp_path, capsys):
    """The two commands compose: what the template writes is what the check reads, unfilled."""
    model = tmp_path / "model.xml"
    model.write_text(
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level2/version4" '
        'level="2" version="4"><model id="m">'
        '<listOfCompartments><compartment id="Liver" size="1.51"/></listOfCompartments>'
        '<listOfSpecies><species id="mLiver" compartment="Liver" initialAmount="0"/>'
        '</listOfSpecies>'
        '<listOfParameters><parameter id="Ktp_Liver" value="5.5"/>'
        '<parameter id="QLiver" value="1799"/></listOfParameters>'
        '<listOfInitialAssignments><initialAssignment symbol="QLiver"><math '
        'xmlns="http://www.w3.org/1998/Math/MathML"><cn>1</cn></math></initialAssignment>'
        '</listOfInitialAssignments></model></sbml>',
        encoding="utf-8",
    )
    out = tmp_path / "parameters.json"
    assert run(["params-template", "--model", str(model), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "3 row(s) to fill in: 1 compartments, 1 parameters, 1 species" in printed
    assert "1 value(s) your model's own math determines are listed apart" in printed

    written = json.loads(out.read_text(encoding="utf-8"))
    assert all(row["reported"] is None for row in written["parameters"])
    assert written["determined_by_the_model"] == {"parameter": ["QLiver"]}

    # Straight into the check, unedited: three unfilled rows, and not one of them a pass.
    assert run(["params-check", "--model", str(model), "--parameters", str(out)]) == 0
    checked = capsys.readouterr().out
    assert "3 parameter(s) were not compared" in checked and "ok:" not in checked


def test_the_params_commands_read_an_archive_as_well_as_a_loose_model(capsys):
    """Most papers ship the archive, and unzipping it to ask about your own model is the friction
    this surface exists to remove. `claims-template` has taken both since it was written; the
    parameter commands took only the loose file."""
    archive = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "metformin_reconstruction.omex"
    )
    assert run(["params-template", "--out", "/dev/null", str(archive)]) == 0
    assert "row(s) to fill in" in capsys.readouterr().out


def test_the_params_commands_refuse_two_models_and_none(capsys):
    """Naming both says nothing about which model the paper reports, and naming neither reads
    nothing — neither is a failure to read a file, so neither is worded as one."""
    assert run(["params-template"]) == 1
    assert capsys.readouterr().err.startswith("give either an archive or --model")
    assert run(["params-template", "--model", "a.xml", "b.omex"]) == 1
    assert capsys.readouterr().err.startswith("give either an archive or --model")


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


def test_figure_check_measures_what_a_reading_costs_from_the_reading_itself(tmp_path, capsys):
    """The gap said how *much* of the comparison is interpolated; this says how *wrong* it is.

    Rejoin each interior reading from its two neighbours and the residual is the curve's own
    curvature, in the units the verdict is in. A three-point reading straddling a peak spends more
    than the whole figure budget on its straight lines and is told so, with the place to add points.
    """
    coarse = tmp_path / "coarse.json"
    coarse.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "c", "curve": "plasma", "points": [[0, 0.5], [2, 6.0], [24, 1.0]]}],
    }), encoding="utf-8")
    assert run(["figure-check", "--series", str(coarse)]) == 0
    printed = capsys.readouterr().out
    assert "rejoining each reading from its neighbours misses it by at most" in printed
    assert "spend the whole figure tolerance before the model is consulted" in printed
    # The place to read more, not just the fact that more is needed.
    assert "add points near 2 h" in printed


def test_figure_check_does_not_warn_about_a_straight_line_read_coarsely(tmp_path, capsys):
    """The false alarm the gap heuristic could not avoid, and the reason the measurement is worth
    having: a line joined by a line is joined perfectly, at three points or at three hundred.

    The gap is still reported — 92% of this span is interpolated, which is a fact about the
    comparison — but nothing here claims it costs anything, because measured against the curator's
    own readings it costs exactly zero.
    """
    straight = tmp_path / "straight.json"
    straight.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "c", "curve": "plasma", "points": [[0, 1.0], [2, 1.5], [24, 7.0]]}],
    }), encoding="utf-8")
    assert run(["figure-check", "--series", str(straight)]) == 0
    printed = capsys.readouterr().out
    assert "92% of the span" in printed
    assert "spend the whole figure tolerance" not in printed
    assert "(0% of the pass budget)" in printed


def test_figure_check_publishes_the_measured_cost_as_json(tmp_path, capsys):
    """A script reads the number, not the sentence."""
    series = tmp_path / "figure3a.json"
    series.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "c", "curve": "plasma", "points": [[0, 0.5], [2, 6.0], [24, 1.0]]}],
    }), encoding="utf-8")
    assert run(["figure-check", "--series", str(series), "--json"]) == 0
    cost = json.loads(capsys.readouterr().out)["series"][0]["interpolation"]
    assert cost["measurable"] is True and cost["points"] == 3
    assert cost["worst_at"] == 2.0 and cost["worst_read"] == 6.0
    assert cost["budget_share"] > 1.0


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


_KINETIC_SEDML = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"


def _digitization(
    path: Path, claim: str, *, span: tuple[float, float] = (0, 9000), figure: str = "Figure 2A",
) -> Path:
    """A filled digitization of one panel, paired with ``claim`` and read over ``span``."""
    low, high = span
    path.write_text(json.dumps({
        "figure": figure, "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 9000, "unit": "s"},
        "y_axis": {"minimum": 0, "maximum": 300, "unit": "nM"},
        "series": [{"claim": claim, "curve": "MAPK_PP",
                    "points": [[low, 10.0], [(low + high) / 2, 280.0], [high, 40.0]]}],
    }), encoding="utf-8")
    return path


def test_figure_check_checks_the_pairing_against_the_document_it_was_read_off(tmp_path, capsys):
    """The pairing is the one part of the file nobody can guess, and the part a typo breaks
    silently. Given the document, the ids are checked against the curves it actually plots — and
    the curves this panel does not read are named, because "clean" over one of four reads as four.
    """
    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML)]) == 0
    printed = capsys.readouterr().out
    assert "every series is paired with a curve your document plots" in printed
    assert "covers a window your document runs" in printed
    assert "3 curve(s) your document plots are not read here" in printed
    assert "plot_1__plot_1_0_0__plot_1_1_1" in printed


def test_figure_check_costs_the_reading_over_the_run_it_will_be_judged_on(tmp_path, capsys):
    """A reading is required to *cover* the run, so it is permitted to exceed it — and the range a
    bend outside the run adds to the scale is range the verdict never uses. The Kholodenko document
    runs 0-9000 s; a reading that bends before 9000 s and then climbs steeply past it had that bend
    divided by the climb, and the number a curator acts on came out 2.2x too small (0.93 against
    the 2.0 the judged window carries).
    """
    series = tmp_path / "fig2a.json"
    series.write_text(json.dumps({
        "figure": "Figure 2A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 12000, "unit": "s"},
        "y_axis": {"minimum": 0, "maximum": 300, "unit": "nM"},
        # One bend inside the run; a straight climb after it, which adds range and no curvature.
        "series": [{"claim": "plot_0__plot_0_0_0__plot_0_0_1", "curve": "MAPK_PP",
                    "points": [[0, 10.0], [2250, 60.0], [4500, 30.0], [6750, 35.0],
                               [9000, 40.0], [12000, 280.0]]}],
    }), encoding="utf-8")
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML)]) == 0
    assert "measured over the 0-9000 s your document runs" in capsys.readouterr().out

    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML),
                "--json"]) == 0
    (judged,) = json.loads(capsys.readouterr().out)["series"]
    assert judged["interpolation"]["window"] == [0.0, 9000.0]
    # The same file read with no document beside it is measured over the whole reading — the number
    # that was always reported, and the one the climb past the run divides down.
    assert run(["figure-check", "--series", str(series), "--json"]) == 0
    (whole,) = json.loads(capsys.readouterr().out)["series"]
    assert whole["interpolation"]["window"] == [0.0, 12000.0]
    assert judged["interpolation"]["budget_share"] > 2 * whole["interpolation"]["budget_share"]


def test_figure_check_refuses_a_reading_paired_with_a_curve_the_document_does_not_plot(
    tmp_path, capsys,
):
    """A claim id is `plot_0__plot_0_0_0__plot_0_0_1`; one character wrong is a reading of nothing,
    and until now nothing told the curator so at the terminal."""
    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_2")
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML)]) == 1
    printed = capsys.readouterr().out
    assert "PAIRED WITH THE WRONG CLAIM" in printed
    assert "which your document does not carry" in printed


def test_figure_check_refuses_a_reading_paired_with_a_claim_that_is_not_a_target(tmp_path, capsys):
    """A report's data set is retained non-targetable on purpose: giving it values promotes it
    into a result the paper never staked, which is a tracked revision and not a side effect."""
    series = _digitization(tmp_path / "fig2a.json", "autogen_task_fig2a_MKKK")
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML)]) == 1
    assert "never staked" in capsys.readouterr().out


def test_figure_check_refuses_a_reading_that_does_not_cover_the_window_the_document_runs(
    tmp_path, capsys,
):
    """Nothing is extrapolated, so a reading that starts after the run does is a file that is
    internally perfect and cannot be used. That refusal exists — at the join, in Python, after the
    curator has gone home — and both numbers that say so are on disk while they are still here."""
    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1",
                           span=(300, 9000))
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML)]) == 1
    printed = capsys.readouterr().out
    assert "READ OVER TOO SHORT A WINDOW" in printed
    assert "was read over 300-9000 s, and your document runs 0-9000" in printed
    assert "nothing here is extrapolated" in printed


def test_figure_check_reads_every_panel_a_paper_has(tmp_path, capsys):
    """One file is one panel, and a paper is several. Checked one at a time, each of them reads
    as "the other three curves are unread" — which is true of the file and false of the paper."""
    first = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    second = _digitization(tmp_path / "fig2b.json", "plot_1__plot_1_0_0__plot_1_0_1",
                           figure="Figure 2B")
    assert run(["figure-check", "--series", str(first), "--series", str(second),
                "--sedml", str(_KINETIC_SEDML)]) == 0
    printed = capsys.readouterr().out
    assert "2 SERIES READ FROM Figure 2A, Figure 2B" in printed
    # Which picture a claim was read off is the fact a curator checking two panels needs.
    assert "Figure 2A [plot_0__plot_0_0_0__plot_0_0_1]" in printed
    # The curator's label for the curve and the document's quantity, side by side and never
    # compared: a reading of the wrong curve of the right figure passes every other check here.
    assert "your document plots MAPK_PP there" in printed
    # How much of the comparison is the curator's straight line, stated and not judged: a curve
    # read at three points is judged on the run's own thousand samples.
    assert ("your document samples 0-9000 s 1001 times, and this curve was read at 3: the other "
            "998 are the straight line between readings") in printed
    assert "2 curve(s) your document plots are not read here" in printed


def test_figure_check_refuses_one_claim_read_off_two_panels(tmp_path, capsys):
    """A file cannot pair two curves with one claim — the reader refuses that. Two files could,
    and nothing saw it: the join keys readings by claim id, so the second panel's curve silently
    replaced the first's and one of the two readings was never used."""
    first = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    second = _digitization(tmp_path / "fig2b.json", "plot_0__plot_0_0_0__plot_0_0_1",
                           figure="Figure 2B")
    assert run(["figure-check", "--series", str(first), "--series", str(second),
                "--sedml", str(_KINETIC_SEDML)]) == 1
    printed = capsys.readouterr().out
    assert "paired with more than one panel (Figure 2A, Figure 2B)" in printed


def test_figure_check_refuses_one_file_holding_two_of_the_documents_panels(tmp_path, capsys):
    """`figure-template` will not write this file any more, and a hand-written one still can.

    Once the axis ranges are filled in there is nothing left to notice: the second plot's curves
    are calibrated against the first plot's axes, and what comes out is ordered, smooth, plausible
    and wrong by a constant factor.
    """
    mixed = tmp_path / "both.json"
    mixed.write_text(json.dumps({
        "figure": "Figure 2", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 9000, "unit": "s"},
        "y_axis": {"minimum": 0, "maximum": 300, "unit": "nM"},
        "series": [
            {"claim": "plot_0__plot_0_0_0__plot_0_0_1", "curve": "MAPK_PP",
             "points": [[0, 10.0], [4500, 280.0], [9000, 40.0]]},
            {"claim": "plot_1__plot_1_0_0__plot_1_0_1", "curve": "MAPK_PP",
             "points": [[0, 12.0], [4500, 260.0], [9000, 44.0]]},
        ],
    }), encoding="utf-8")
    assert run(["figure-check", "--series", str(mixed), "--sedml", str(_KINETIC_SEDML)]) == 1
    printed = capsys.readouterr().out
    assert "the readings in Figure 2 come from 2 of your document's plots" in printed
    assert "'plot_0' (Figure 2A), 'plot_1' (Figure 2B)" in printed


def test_figure_check_names_the_same_panel_passed_twice_as_what_it_is(tmp_path, capsys):
    """One file under two names is the ordinary slip, and "more than one panel" would send a
    curator looking for a second picture that does not exist."""
    only = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    assert run(["figure-check", "--series", str(only), "--series", str(only),
                "--sedml", str(_KINETIC_SEDML)]) == 1
    assert "2 readings, all of them in Figure 2A" in capsys.readouterr().out


def test_figure_check_without_a_document_says_the_pairing_was_not_checked(tmp_path, capsys):
    """A clean report over a check nobody made is the shape this repository keeps being caught by."""
    series = _digitization(tmp_path / "fig2a.json", "not-a-claim-in-any-document")
    assert run(["figure-check", "--series", str(series)]) == 0
    assert "were not checked: no document was given" in capsys.readouterr().out


def test_figure_check_reads_the_pairing_out_of_an_archive_too(tmp_path, capsys):
    """The two input forms cannot reach different conclusions: it is the same document either way."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    kinetic = _KINETIC_SEDML.parent
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
        zf.writestr("BIOMD0000000010.sedml", _KINETIC_SEDML.read_text(encoding="utf-8"))

    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    assert run(["figure-check", "--series", str(series), str(archive), "--json"]) == 0
    packaged = json.loads(capsys.readouterr().out)
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML),
                "--json"]) == 0
    loose = json.loads(capsys.readouterr().out)
    assert packaged["pairing"]["curves_not_read"] == loose["pairing"]["curves_not_read"]
    assert packaged["pairing"]["faults"] == [] == loose["pairing"]["faults"]


def test_figure_check_compares_the_reading_s_clock_against_the_model_s(tmp_path, capsys):
    """The window check cannot see this, and it is the error that ruins a reading silently.

    A figure read in minutes over 0-120 covers a run of 0-24 hours *as numbers*, so nothing was
    refused and every value landed in the wrong place. Both files state a unit; only a model can be
    asked which one the run is on.
    """
    model = tmp_path / "model.xml"
    model.write_text(
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" '
        'level="3" version="2"><model id="m" timeUnits="time"><listOfUnitDefinitions>'
        '<unitDefinition id="time"><listOfUnits>'
        '<unit kind="second" exponent="1" scale="0" multiplier="3600"/></listOfUnits>'
        '</unitDefinition></listOfUnitDefinitions></model></sbml>',
        encoding="utf-8",
    )
    # The fixture reads its x axis in seconds; this model's clock is in hours.
    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML),
                "--model", str(model)]) == 0
    printed = capsys.readouterr().out
    assert "UNITS DISAGREE" in printed
    assert "read against an x axis in s" in printed and "3600 times as large" in printed
    # Reported, never a fault: which of the two files is wrong is not this command's to decide, and
    # a deposit that declares its own time wrongly must not make a correct reading unusable.
    assert "every series is paired with a curve your document plots" in printed

    # Without a model there is nothing to compare against, and nothing is said.
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML)]) == 0
    assert "UNITS DISAGREE" not in capsys.readouterr().out


def test_figure_check_compares_the_reading_s_y_axis_against_the_output_it_reads(tmp_path, capsys):
    """The document says which output a curve reads, and the model says what that is measured in.

    This paper plots each tissue twice, in mg on one panel and nmol on another, so the wrong panel
    paired with the right claim is a file nothing else here can fault.
    """
    worked = Path(__file__).parent.parent / "datasets" / "worked_examples"
    path = tmp_path / "fig.json"
    path.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 30, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 30, "unit": "mg/mL"},
        "series": [{"claim": "p2_curve_17_task2", "curve": "venous plasma",
                    "points": [[0, 0.0], [1, 20.0], [30, 2.0]]}],
    }), encoding="utf-8")

    assert run([
        "figure-check", "--series", str(path),
        "--sedml", str(worked / "Zake2021_metformin_human_single_PO.sedml"),
        "--model", str(worked / "Zake2021_metformin_human_single_PO.xml"),
    ]) == 0
    printed = capsys.readouterr().out
    assert "y axis in mg/mL" in printed and "mPlasmaVenous" in printed


def test_figure_check_json_shape_is_pinned(tmp_path, capsys):
    """This command has no MCP tool, so nothing else pins what a script reading it receives.

    Every other read command's `--json` is held to the object its MCP tool returns; the two figure
    commands work on a file the server has no path to, so the equivalent guard is here or nowhere.
    """
    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    assert run(["figure-check", "--series", str(series), "--sedml", str(_KINETIC_SEDML),
                "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"series", "pairing", "unit_notes"}
    (reading,) = payload["series"]
    assert set(reading) == {"claim", "curve", "figure", "digitizer", "points", "x_axis", "y_axis",
                            "resolution", "interpolation"}
    assert set(reading["resolution"]) == {"points", "span", "widest_gap", "widest_gap_fraction"}
    assert set(reading["interpolation"]) == {"points", "window", "measurable", "worst_at",
                                             "worst_read", "worst_interpolated", "worst_residual",
                                             "normalized", "budget_share"}
    assert set(payload["pairing"]) == {"checked_against", "faults", "curves_not_read", "runs",
                                       "window_faults"}
    assert payload["pairing"]["runs"] == [[0.0, 9000.0, 1000]]

    # Without a document the pairing is absent rather than empty: nothing was checked.
    assert run(["figure-check", "--series", str(series), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pairing"] is None


def test_figure_check_takes_one_document_or_the_other_and_not_both(tmp_path, capsys):
    series = _digitization(tmp_path / "fig2a.json", "plot_0__plot_0_0_0__plot_0_0_1")
    assert run(["figure-check", "--series", str(series), "some.omex",
                "--sedml", str(_KINETIC_SEDML)]) == 1
    assert "either an archive or --sedml, not both" in capsys.readouterr().err


def test_figure_check_of_a_missing_file_is_a_message(tmp_path, capsys):
    assert run(["figure-check", "--series", str(tmp_path / "nope.json")]) == 1
    assert "cannot read the digitization" in capsys.readouterr().err


def test_figure_template_writes_the_pairing_nobody_could_guess(tmp_path, capsys):
    """A claim id off a SED-ML document is `plot_0__plot_0_0_0__plot_0_0_1` and has to match
    exactly, so the template writes the ids and the curve each plots — and nothing that is a
    reading: the figure, the tool, both axis ranges and every point stay blank."""
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    out = tmp_path / "figure.json"
    assert run(["figure-template", "--sedml", str(sedml), "--plot", "plot_0",
                "--out", str(out)]) == 0
    assert "2 curve(s) to read off your figure" in capsys.readouterr().out

    written = json.loads(out.read_text(encoding="utf-8"))
    # This document plots two panels, and one file is one of them.
    assert [s["claim"] for s in written["series"]] == [
        "plot_0__plot_0_0_0__plot_0_0_1", "plot_0__plot_0_0_0__plot_0_1_1",
    ]
    assert all(s["points"] == [] for s in written["series"])
    assert written["figure"] == "" and written["digitizer"] == ""
    # The one piece of guidance that has to arrive before the reading, not after it: a reading
    # already taken cannot be made finer without taking it again.
    assert any("read about twenty points per curve" in note for note in written["notes"])
    assert written["x_axis"]["minimum"] is None and written["y_axis"]["unit"] == ""


def test_a_template_handed_straight_back_is_told_what_is_left_to_write(tmp_path, capsys):
    """Reading it would refuse on whichever blank it reached first, which says nothing about the
    other four. Every blank is named, and the command is the one that names them."""
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    out = tmp_path / "figure.json"
    run(["figure-template", "--sedml", str(sedml), "--plot", "plot_0", "--out", str(out)])
    capsys.readouterr()

    assert run(["figure-check", "--series", str(out)]) == 1
    error = capsys.readouterr().err
    assert "has not been filled in yet" in error
    for blank in ("'figure' is blank", "'digitizer' is blank", "'x_axis.minimum' is blank",
                  "'y_axis.unit' is blank", "has no points"):
        assert blank in error


def test_figure_template_will_not_write_two_panels_into_one_file(tmp_path, capsys):
    """A file states its axes once, because one file is one panel. Two plots' curves under one
    pair of axis ranges is the second panel read against the first panel's calibration — ordered,
    smooth, plausible and wrong by a constant factor, which is exactly what the axis-range refusal
    catches and cannot see once it is baked into the file."""
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    assert run(["figure-template", "--sedml", str(sedml)]) == 1
    error = capsys.readouterr().err
    assert "this document plots 2: 'plot_0' (Figure 2A), 'plot_1' (Figure 2B)" in error
    # Not a defect in the author's document, and it does not say it is.
    assert "cannot read the document" not in error


def test_figure_template_names_the_plots_it_has_when_asked_for_one_it_does_not(tmp_path, capsys):
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    assert run(["figure-template", "--sedml", str(sedml), "--plot", "plot_9"]) == 1
    assert "no plot 'plot_9'" in capsys.readouterr().err


def test_figure_template_writes_one_file_per_panel_in_one_command(tmp_path, capsys):
    """A four-figure paper should not be four invocations and four plot ids looked up by hand.

    Still one file per panel: the boundary is the point, not the number of commands.
    """
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    out = tmp_path / "panels"
    assert run(["figure-template", "--sedml", str(sedml), "--out-dir", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "'plot_0' (Figure 2A): 2 curve(s)" in printed
    assert "'plot_1' (Figure 2B): 2 curve(s)" in printed

    written = json.loads((out / "plot_1.json").read_text(encoding="utf-8"))
    assert [s["claim"] for s in written["series"]] == [
        "plot_1__plot_1_0_0__plot_1_0_1", "plot_1__plot_1_0_0__plot_1_1_1",
    ]
    # It is the same file the single-panel form writes, so the two cannot drift apart.
    one = tmp_path / "one.json"
    run(["figure-template", "--sedml", str(sedml), "--plot", "plot_1", "--out", str(one)])
    assert json.loads(one.read_text(encoding="utf-8")) == written


def test_figure_template_says_when_it_replaced_a_filled_in_file(tmp_path, capsys):
    """A curator who has already read a curve into one of these should not lose it silently."""
    sedml = Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.sedml"
    out = tmp_path / "panels"
    run(["figure-template", "--sedml", str(sedml), "--out-dir", str(out)])
    capsys.readouterr()
    assert run(["figure-template", "--sedml", str(sedml), "--out-dir", str(out)]) == 0
    assert "(replaced)" in capsys.readouterr().out


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
    assert run(["figure-template", str(archive), "--plot", "plot_1", "--out", str(out)]) == 0
    packaged = json.loads(out.read_text(encoding="utf-8"))

    loose = tmp_path / "loose.json"
    run(["figure-template", "--sedml", str(kinetic / "BIOMD0000000010.sedml"), "--plot", "plot_1",
         "--out", str(loose)])
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


def test_figure_check_says_a_two_point_reading_cannot_be_measured_at_all(tmp_path, capsys):
    """The only unmeasurable case a series can reach, and the branch that used to guard it wrong.

    Two points is one straight line over the whole span with no interior reading to check it
    against. It was guarded by the widest-gap threshold, which cannot discriminate here — a
    two-point reading's one gap *is* the span, so the condition was true whenever it was reached
    and read as a test that could fail.
    """
    two = tmp_path / "two.json"
    two.write_text(json.dumps({
        "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 10, "unit": "nmol/mL"},
        "series": [{"claim": "c", "curve": "plasma", "points": [[0, 0.5], [24, 6.0]]}],
    }), encoding="utf-8")
    assert run(["figure-check", "--series", str(two)]) == 0
    printed = capsys.readouterr().out
    assert "2 readings leave no interior point between 0 and 24 h" in printed
    assert "check the straight lines over it against" in printed
    # And no measured number is printed for it, rather than a zero that would read as "free".
    assert "of the pass budget" not in printed

    assert run(["figure-check", "--series", str(two), "--json"]) == 0
    cost = json.loads(capsys.readouterr().out)["series"][0]["interpolation"]
    assert cost["measurable"] is False and cost["budget_share"] is None
