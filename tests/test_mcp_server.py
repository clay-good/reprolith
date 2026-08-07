"""The read-only MCP server over the query surface (spec: mcp-server). Pure stdlib, no engine."""

from __future__ import annotations

import io
import json

from reprolith import (
    Catalog,
    CertificateLedger,
    ClaimAssessment,
    EnginePin,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    ReprolithQuery,
    Verdict,
    build_certificate,
    handle_request,
    serve_stdio,
)
from reprolith.mcp_server import TOOL_DEFINITIONS, load_certificates, load_dossiers
from reprolith.seed import seed_catalog


def _fixture() -> tuple[ReprolithQuery, str]:
    catalog = Catalog()
    catalog.add(
        Identifiers(title="Two-compartment PK model", doi="10.1/x"), ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="curation"),
    )
    ledger = CertificateLedger()
    digest = ledger.issue(build_certificate(
        paper=PaperIdentity(title="Two-compartment PK model", doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
    ))
    return ReprolithQuery(catalog, ledger), digest


def _call(query, name, arguments):
    resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": name, "arguments": arguments}})
    result = resp["result"]
    is_error = result.get("isError", False)
    text = result["content"][0]["text"]
    return (text if is_error else json.loads(text)), is_error


def test_initialize_and_tools_list() -> None:
    query, _ = _fixture()
    init = handle_request(query, {"jsonrpc": "2.0", "id": 0, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "reprolith"
    tools = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"list_catalog", "status", "certificate", "verdict", "gaps"} <= names
    assert names == {t["name"] for t in TOOL_DEFINITIONS}


def test_initialized_notification_has_no_response() -> None:
    query, _ = _fixture()
    assert handle_request(query, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_verdict_tool_carries_scope_and_qualifications() -> None:
    query, digest = _fixture()
    verdict, is_error = _call(query, "verdict", {"digest": digest})
    assert not is_error
    assert verdict["overall"] == OverallVerdict.REPRODUCED.value
    # The inescapable scope flag travels over MCP too (spec).
    assert verdict["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_catalog_and_status_tools_are_blind() -> None:
    query, _ = _fixture()
    entries, _ = _call(query, "list_catalog", {})
    assert entries and all("ground_truth" not in e for e in entries)
    status, _ = _call(query, "status", {"doi": "10.1/x"})
    assert status is not None and "ground_truth" not in status


def test_unknown_tool_is_a_tool_error_not_a_crash() -> None:
    query, _ = _fixture()
    _, is_error = _call(query, "does_not_exist", {})
    assert is_error


def test_lint_tool_is_registered() -> None:
    assert "lint" in {t["name"] for t in TOOL_DEFINITIONS}


def test_lint_objective_tool_is_registered() -> None:
    assert "lint_objective" in {t["name"] for t in TOOL_DEFINITIONS}


def test_lint_objective_tool_returns_a_scope_qualified_verdict() -> None:
    from pathlib import Path

    import pytest

    pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
    pytest.importorskip("scipy", reason="the fba extra (scipy) is not installed")
    query, _ = _fixture()
    sbml = (Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml").read_text(
        encoding="utf-8"
    )
    result, is_error = _call(query, "lint_objective", {"sbml": sbml, "reported": 0.873922})
    assert not is_error
    assert result["verdict"] == "reproduced"
    assert result["method"] == "scalar-relative-error"
    assert result["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_lint_steady_state_tool_is_registered() -> None:
    assert "lint_steady_state" in {t["name"] for t in TOOL_DEFINITIONS}


def test_lint_steady_state_tool_returns_a_scope_qualified_verdict() -> None:
    # The logical linter is pure Python — no engine extra — so it runs unconditionally over MCP.
    query, _ = _fixture()
    result, is_error = _call(query, "lint_steady_state", {
        "rules": {"A": "!B", "B": "!A"}, "reported": {"A": 1, "B": 0},
    })
    assert not is_error
    assert result["verdict"] == "reproduced"
    assert result["method"] == "attractor-set-match"
    assert result["scope"]["machine"] == "reproducible-not-correct-not-clinical"

    bad, is_error = _call(query, "lint_steady_state", {
        "rules": {"A": "!B", "B": "!A"}, "reported": {"A": 1, "B": 1},
    })
    assert not is_error and bad["verdict"] == "failed"


def test_dossier_tool_serves_the_stored_ingested_dossier() -> None:
    # The metformin dossier the milestone run ingested and stored is served for inspection.
    from pathlib import Path

    dossier_dir = Path(__file__).parent.parent / "datasets" / "milestone" / "dossiers"
    dossiers = load_dossiers(dossier_dir)
    query = ReprolithQuery(Catalog(), CertificateLedger(), dossiers)
    dossier, is_error = _call(query, "dossier", {"accession": "BIOMD0000001028"})
    assert not is_error
    assert len(dossier["state_variables"]) == 21  # the real PBPK model structure
    assert dossier["parameters"]
    # An unknown accession is served as null, not an error.
    missing, is_error = _call(query, "dossier", {"accession": "NOPE"})
    assert not is_error and missing is None


def test_bundle_tool_serves_the_stored_reconstruction_bundle() -> None:
    from pathlib import Path

    bundle_dir = Path(__file__).parent.parent / "datasets" / "milestone" / "bundles"
    bundles = load_dossiers(bundle_dir)  # same loader (one JSON per accession)
    query = ReprolithQuery(Catalog(), CertificateLedger(), bundles=bundles)
    bundle, is_error = _call(query, "bundle", {"accession": "BIOMD0000001028"})
    assert not is_error
    assert bundle["origin"] == "author-supplied"  # the metformin model was adopted
    assert len(bundle["recipe"]) == 2  # a recipe step per claim
    assert bundle["assumptions"]  # the salt-form assumption travels


def test_status_reflects_persisted_run_progress() -> None:
    # The persisted milestone catalog records the run's lifecycle; status shows the metformin
    # entry as certified, loaded from disk with no re-run.
    import json
    from pathlib import Path

    catalog_file = Path(__file__).parent.parent / "datasets" / "milestone" / "catalog.json"
    catalog = Catalog.from_dict(json.loads(catalog_file.read_text(encoding="utf-8")))
    query = ReprolithQuery(catalog, CertificateLedger())
    status, _ = _call(query, "status", {"accession": "BIOMD0000001028"})
    assert status["state"] == "certified"
    assert status["history"]  # the lifecycle path was recorded


def test_server_serves_the_stored_milestone_certificate() -> None:
    # End to end, no engine: the metformin certificate the milestone run stored as JSON is
    # loaded into the ledger and served through the MCP tools.
    from pathlib import Path

    catalog = Catalog()
    seed_catalog(catalog)
    ledger = CertificateLedger()
    cert_dir = Path(__file__).parent.parent / "datasets" / "milestone" / "certificates"
    assert load_certificates(ledger, cert_dir) >= 1
    query = ReprolithQuery(catalog, ledger)

    # The certificate's paper carries the title (shared with the catalog entry), so it is
    # discoverable by title.
    digests, _ = _call(query, "certificates_for",
                       {"title": "Zake2021 - PBPK model of metformin in humans, single PO dose"})
    assert digests
    verdict, is_error = _call(query, "verdict", {"digest": digests[0]})
    assert not is_error
    assert verdict["overall"] == OverallVerdict.PARTIALLY_REPRODUCED.value
    assert verdict["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_lint_tool_reports_missing_engine_as_a_tool_error() -> None:
    import pytest

    if _copasi_installed():
        pytest.skip("engine installed; the missing-engine path is not exercised")
    query, _ = _fixture()
    text, is_error = _call(query, "lint", {
        "sbml": "<sbml/>", "species": "A", "reference": [1.0], "duration": 1.0, "steps": 0,
    })
    # Without the engine extra the tool errors cleanly rather than crashing the server.
    assert is_error and "engine" in text.lower()


def _copasi_installed() -> bool:
    import importlib.util

    return importlib.util.find_spec("COPASI") is not None


def test_lint_tool_returns_a_scope_qualified_verdict_with_the_engine() -> None:
    import math

    import pytest

    pytest.importorskip("COPASI", reason="the engine extra is not installed")
    query, _ = _fixture()
    sbml = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="onecomp">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies><species id="A" compartment="c" initialAmount="100"
      hasOnlySubstanceUnits="true" boundaryCondition="false" constant="false"/></listOfSpecies>
    <listOfParameters><parameter id="k" value="0.5" constant="true"/></listOfParameters>
    <listOfRules><rateRule variable="A"><math xmlns="http://www.w3.org/1998/Math/MathML">
      <apply><minus/><apply><times/><ci>k</ci><ci>A</ci></apply></apply></math></rateRule></listOfRules>
  </model>
</sbml>"""
    reference = [100.0 * math.exp(-0.5 * t) for t in range(11)]
    result, is_error = _call(query, "lint", {
        "sbml": sbml, "species": "A", "reference": reference, "duration": 10.0, "steps": 10,
    })
    assert not is_error
    assert result["verdict"] == "reproduced"
    assert result["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_unknown_method_returns_jsonrpc_error() -> None:
    query, _ = _fixture()
    resp = handle_request(query, {"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
    assert resp["error"]["code"] == -32601


# --- effectful tools: separated from read-only, offered only with a mutable catalog ---


def test_read_only_server_hides_and_refuses_submit_paper() -> None:
    query, _ = _fixture()  # no catalog passed -> read-only
    tools = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert "submit_paper" not in {t["name"] for t in tools["result"]["tools"]}
    resp = handle_request(query, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "submit_paper", "arguments": {"title": "x"}}})
    assert resp["result"]["isError"]


def test_submit_paper_adds_an_entry_persists_and_dedups() -> None:
    catalog = Catalog()
    query = ReprolithQuery(catalog, CertificateLedger())
    saved: list[int] = []

    def call_submit(args):
        return handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "submit_paper", "arguments": args}},
                              catalog=catalog, on_change=lambda: saved.append(len(catalog)))

    # Effectful tools are listed when a mutable catalog is provided.
    tools = handle_request(query, {"jsonrpc": "2.0", "id": 0, "method": "tools/list"}, catalog=catalog)
    assert "submit_paper" in {t["name"] for t in tools["result"]["tools"]}

    first = call_submit({"title": "New PK model", "doi": "10.1/new"})
    report = json.loads(first["result"]["content"][0]["text"])
    assert report["created"] and not report["resolved_to_existing"]
    assert len(catalog) == 1 and saved == [1]  # persisted after the change
    # The read query reflects the new entry (shared catalog).
    assert any(e["identifiers"]["doi"] == "10.1/new" for e in query.list_catalog())

    # Submitting the same paper again resolves to the existing entry, no duplicate.
    again = call_submit({"title": "New PK model (v2)", "doi": "10.1/new"})
    report2 = json.loads(again["result"]["content"][0]["text"])
    assert report2["resolved_to_existing"] and not report2["created"]
    assert len(catalog) == 1


def test_claim_work_tool_leases_the_next_item() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD)
    catalog.add(Identifiers(title="B", accession="B2"), ModelClass.ODE_PKPD)
    query = ReprolithQuery(catalog, CertificateLedger())
    clock = [1000.0]  # an injected wall clock

    def claim(requester):
        resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "claim_work",
                                                 "arguments": {"requester": requester, "lease_seconds": 60}}},
                              catalog=catalog, now=lambda: clock[0])
        return json.loads(resp["result"]["content"][0]["text"])

    first = claim("agent-1")
    assert first["claimed"] and first["lease_expires"] == 1060.0
    second = claim("agent-2")  # different item, no collision
    assert second["claimed"] and second["entry"]["identifiers"]["accession"] != first["entry"]["identifiers"]["accession"]
    # No eligible work left while both are leased.
    assert claim("agent-3") == {"claimed": False, "reason": "no eligible work"}


def test_claim_work_refused_on_read_only_server() -> None:
    query, _ = _fixture()
    resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "claim_work", "arguments": {"requester": "a"}}})
    assert resp["result"]["isError"]


def test_release_work_returns_the_item_to_the_queue() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD)
    query = ReprolithQuery(catalog, CertificateLedger())

    def call(name, args):
        resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": name, "arguments": args}},
                              catalog=catalog, now=lambda: 0.0)
        return json.loads(resp["result"]["content"][0]["text"])

    call("claim_work", {"requester": "agent-1", "lease_seconds": 1000})
    # A non-holder cannot release it.
    assert call("release_work", {"accession": "A1", "requester": "agent-2"})["released"] is False
    # The holder releases it back to the queue.
    assert call("release_work", {"accession": "A1", "requester": "agent-1"})["released"] is True
    # It is claimable again immediately.
    assert call("claim_work", {"requester": "agent-2", "lease_seconds": 10})["claimed"] is True


def test_stdio_round_trip() -> None:
    query, digest = _fixture()
    requests = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "certificate", "arguments": {"digest": digest}}}),
    ]) + "\n"
    out = io.StringIO()
    serve_stdio(query, reader=io.StringIO(requests), writer=out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    # initialize + tools/call -> 2 responses (the notification produced none).
    assert len(responses) == 2
    assert responses[0]["id"] == 1
    cert = json.loads(responses[1]["result"]["content"][0]["text"])
    assert cert["overall"] == OverallVerdict.REPRODUCED.value


def test_backlog_health_tool_reports_the_backlog() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="A1"), ModelClass.ODE_PKPD,
                ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source="c"))
    catalog.add(Identifiers(title="B", accession="B2"), ModelClass.KINETIC)
    query = ReprolithQuery(catalog, CertificateLedger())
    health, _ = _call(query, "backlog_health", {})
    assert health["total"] == 2
    assert health["by_state"]["queued"] == 2
    assert health["labelled"] == 1 and health["unlabelled"] == 1
    assert health["by_class"] == {"ode-pkpd": 1, "kinetic": 1}
