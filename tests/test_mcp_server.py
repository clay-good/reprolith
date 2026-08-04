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
from reprolith.mcp_server import TOOL_DEFINITIONS


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


def test_unknown_method_returns_jsonrpc_error() -> None:
    query, _ = _fixture()
    resp = handle_request(query, {"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
    assert resp["error"]["code"] == -32601


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
