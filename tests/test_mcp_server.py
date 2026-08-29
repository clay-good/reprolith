"""The read-only MCP server over the query surface (spec: mcp-server). Pure stdlib, no engine."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
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
    certificate_digest,
    handle_request,
    serve_stdio,
)
from reprolith.mcp_server import (
    EFFECTFUL_TOOLS,
    TOOL_DEFINITIONS,
    load_certificates,
    load_dossiers,
)
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


def test_a_non_object_request_is_refused_not_a_crash() -> None:
    # A well-formed JSON value that is not an object (a bare number, string, list, or null) must
    # not reach `request.get(...)` and blow up the loop; it is an invalid JSON-RPC request.
    query, _ = _fixture()
    for payload in (42, "hello", [1, 2], None):
        resp = handle_request(query, payload)  # type: ignore[arg-type]
        assert resp is not None
        assert resp["error"]["code"] == -32600


def test_serve_stdio_survives_a_malformed_line_and_keeps_serving() -> None:
    # One garbage line from an untrusted peer must not kill the single-threaded stdio loop for
    # every later caller: it gets a parse error (-32700), and the next valid request is answered.
    query, _ = _fixture()
    valid = '{"jsonrpc": "2.0", "id": 9, "method": "tools/list"}'
    for first in ("not json at all", "42", "null", "[]"):
        reader = io.StringIO(first + "\n" + valid + "\n")
        writer = io.StringIO()
        serve_stdio(query, reader=reader, writer=writer)
        lines = [json.loads(line) for line in writer.getvalue().splitlines() if line]
        assert lines[0]["error"]["code"] in (-32700, -32600)
        # The following valid request is still answered — the loop did not die.
        assert lines[-1]["id"] == 9 and "result" in lines[-1]


def test_lint_diffusion_rejects_an_oversized_step_count_instead_of_wedging() -> None:
    # lint_diffusion runs a pure-Python `for _ in range(steps)` loop; on the single-threaded stdio
    # server an absurd step count from an untrusted caller would wedge the whole request loop. The
    # boundary caps it, so a pathological request returns a clean tool error in O(1), not a hang.
    query, _ = _fixture()
    text, is_error = _call(query, "lint_diffusion", {
        "initial": [0.0, 1.0], "reference": [0.0, 1.0],
        "diffusivity": 0.0, "dx": 1.0, "dt": 1.0, "steps": 10**12,
    })
    assert is_error
    assert "steps" in text


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
    # One recipe step per claim, counted from the claims dataset rather than written here: this
    # entry has grown from two claims to thirty-three, and a literal makes that a chore.
    _entry = json.loads(
        (Path(__file__).parent.parent / "datasets" / "pkpd_claims.json").read_text(
            encoding="utf-8"
        )
    )["entries"]["BIOMD0000001028"]
    assert len(bundle["recipe"]) == len(_entry["claims"])
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
        "sbml": "<sbml/>", "species": "A", "reference": [1.0, 1.0], "duration": 1.0, "steps": 1,
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
    assert claim("agent-3") == {"claimed": False, "reason": "no eligible work", "skipped_without_accession": 0}


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


def test_inline_linters_for_estimation_and_population_over_mcp() -> None:
    query, _ = _fixture()
    est, is_error = _call(query, "lint_estimation", {"reported": 3.2, "recovered": 3.3})
    assert not is_error and est["verdict"] == "reproduced"
    assert est["scope"]["machine"] == "reproducible-not-correct-not-clinical"

    def bands(f):
        return [{"percentile": p, "curve": [1.0 * f, 2.0 * f, 3.0 * f]} for p in (5.0, 50.0, 95.0)]

    pop, is_error = _call(query, "lint_distribution", {"reported": bands(1.0), "predicted": bands(1.02)})
    assert not is_error and pop["verdict"] == "reproduced"
    assert pop["method"] == "distribution-band-distance"


def test_aggregated_view_reaches_every_class_certificate() -> None:
    """The default read surface aggregates all six classes' published certificates, not just PK/PD.

    Without aggregation the ledger holds only the PK/PD milestone certificate; with it, every
    class's committed certificates are queryable — so an agent can fetch and cite any of them.
    """
    from reprolith.mcp_server import (
        default_data_dir,
        load_repository,
        milestone_certificate_dirs,
    )

    dirs = milestone_certificate_dirs()
    assert set(dirs) == {
        "ode-pkpd", "constraint-based", "kinetic", "logical", "stochastic", "spatial",
    }
    committed = sum(len(list(d.glob("*.json"))) for d in dirs.values())
    assert committed >= 30  # the six classes' walkable milestones

    plain, _ = load_repository(default_data_dir())
    aggregated, _ = load_repository(default_data_dir(), aggregate=True)
    assert len(plain._ledger) < len(aggregated._ledger)
    assert len(aggregated._ledger) == committed

    # A constraint-based (FBA) verdict is reachable only through the aggregated surface, and it
    # still travels with its scope flag — the honesty invariant holds across the aggregation.
    fba_digest = next(
        d for d, c in aggregated._ledger.items() if "iAF1260" in c.paper.title
    )
    assert plain.verdict(fba_digest) is None
    view = aggregated.verdict(fba_digest)
    assert view is not None
    assert view["scope"]["machine"] == "reproducible-not-correct-not-clinical"


def test_self_validation_tool_is_honest_over_mcp() -> None:
    """The self_validation tool reports abstentions apart from wrong verdicts, and lists every class."""
    from reprolith.mcp_server import default_data_dir, load_repository

    aggregated, _ = load_repository(default_data_dir(), aggregate=True)
    report, is_error = _call(aggregated, "self_validation", {})
    assert not is_error
    assert set(report["by_class"]) == {
        "ode-pkpd", "constraint-based", "kinetic", "logical", "stochastic", "spatial",
    }
    overall = report["overall"]
    # honest partition: matched + abstained + other == labelled, and no blended rate to mislead
    assert (overall["agreements"] + overall["abstentions"] + overall["other_disagreements"]
            == overall["labelled_entries"])
    assert "agreement_rate" not in overall
    # the read-only surface refuses the tool when no reports are loaded (empty by_class)
    plain, _ = load_repository(default_data_dir())
    plain_report, _ = _call(plain, "self_validation", {})
    assert plain_report["by_class"] == {}


def test_a_failed_catalog_write_leaves_the_previous_catalog_intact(tmp_path: Path) -> None:
    """A write that dies partway must not destroy the file both surfaces read at startup.

    The catalog is rewritten in full on every mutation. Writing in place meant an interrupted or
    out-of-space write truncated it, and the next start of the server and the CLI both died on the
    unparseable remains — a total wedge from one ordinary effectful call.
    """
    import json as _json

    import pytest
    from reprolith.mcp_server import write_json_atomically

    catalog_file = tmp_path / "catalog.json"
    write_json_atomically(catalog_file, {"entries": ["first"]})
    original = catalog_file.read_text(encoding="utf-8")

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        write_json_atomically(catalog_file, {"entries": [Unserializable()]})

    assert catalog_file.read_text(encoding="utf-8") == original
    assert _json.loads(original) == {"entries": ["first"]}
    assert list(tmp_path.iterdir()) == [catalog_file]  # no temporary debris left behind


def test_a_missing_repository_state_names_the_cause(tmp_path: Path, monkeypatch) -> None:
    """An installed copy of the package carries no datasets, so say that instead of failing later.

    The default state is resolved relative to the source tree. Outside a checkout that path lands
    inside site-packages, and every surface used to die on a bare FileNotFoundError naming a file
    the user never heard of, several frames away from the real cause.
    """
    import pytest
    from reprolith import mcp_server

    monkeypatch.setattr(mcp_server, "repository_data_root", lambda: tmp_path / "datasets")
    with pytest.raises(FileNotFoundError, match="--data-dir"):
        mcp_server.default_data_dir()


def test_lint_steady_state_refuses_an_oversized_network_instead_of_wedging() -> None:
    # Every other lint_* tool caps the caller-supplied size that drives its loop. This one took a
    # rules dict of any size, and a Boolean network's analysis is exponential in its node count, so
    # a single request could occupy the single-threaded stdio server for minutes or longer.
    query, _ = _fixture()
    rules = {f"n{i}": f"!n{(i + 1) % 40}" for i in range(40)}
    text, is_error = _call(query, "lint_steady_state", {
        "rules": rules, "reported": {name: 0 for name in rules},
    })
    assert is_error
    assert "node limit" in text
    # A network inside the ceiling is still served.
    ok, is_error = _call(query, "lint_steady_state", {
        "rules": {"A": "!B", "B": "!A"}, "reported": {"A": 1, "B": 0},
    })
    assert not is_error and ok["verdict"] == "reproduced"


def test_a_submitted_paper_without_a_class_is_unassigned_not_ode_pkpd() -> None:
    # Defaulting put every unclassified paper on the ODE pathway and made it the answer to a
    # claim_work(model_class="ode-pkpd") request.
    from reprolith.catalog import Catalog
    from reprolith.mcp_server import submit_paper

    catalog = Catalog()
    result = submit_paper(catalog, {"title": "A Boolean model of the yeast cell cycle"})
    assert result["entry"]["model_class"] == "unassigned"


def test_a_lease_must_be_a_real_span_of_time() -> None:
    import pytest
    from reprolith.catalog import Catalog, Identifiers
    from reprolith.mcp_server import claim_work

    catalog = Catalog()
    catalog.add(Identifiers(title="Paper A", accession="ACC-A"))
    for bad in (-1, 0, float("nan"), 1e18):
        with pytest.raises(ValueError, match="lease_seconds"):
            claim_work(catalog, {"requester": "agent-1", "lease_seconds": bad}, at=1000.0)
    # A sound lease still holds the entry against a second requester.
    assert claim_work(catalog, {"requester": "agent-1", "lease_seconds": 60}, at=1000.0)["claimed"]
    assert claim_work(catalog, {"requester": "agent-2"}, at=1010.0)["claimed"] is False


# --- recording completed work (spec: mcp-server, "Work that has been done is recorded") -------


def _recording_fixture() -> tuple[Catalog, ReprolithQuery, str]:
    """A queued entry plus a published certificate for that same paper."""
    catalog = Catalog()
    catalog.add(Identifiers(title="Paper A", doi="10.1/a", accession="ACC-A"), ModelClass.ODE_PKPD)
    ledger = CertificateLedger()
    digest = ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper A", doi="10.1/a"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
    ))
    return catalog, ReprolithQuery(catalog, ledger), digest


def _claim(query, catalog, requester, *, at=0.0):
    """Take the lease before recording: a result is a claim that *this* requester did the work."""
    claimed, _ = _effectful(query, catalog, "claim_work",
                            {"requester": requester, "lease_seconds": 3600}, at=at)
    assert claimed["claimed"], claimed
    return claimed


def _effectful(query, catalog, name, arguments, *, at=0.0):
    resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": name, "arguments": arguments}},
                          catalog=catalog, now=lambda: at)
    result = resp["result"]
    is_error = result.get("isError", False)
    text = result["content"][0]["text"]
    return (text if is_error else json.loads(text)), is_error


def test_recording_a_result_takes_the_entry_out_of_the_queue() -> None:
    # Without this the loop never closed: an agent claimed an entry, published a certificate,
    # and the entry stayed queued — handed out again at lease expiry.
    catalog, query, digest = _recording_fixture()
    claimed, _ = _effectful(query, catalog, "claim_work",
                            {"requester": "agent-1", "lease_seconds": 60})
    assert claimed["claimed"]

    done, is_error = _effectful(query, catalog, "record_result",
                                {"accession": "ACC-A", "requester": "agent-1", "digest": digest})
    assert not is_error
    assert done["recorded"] and done["state"] == "certified" and done["overall"] == "reproduced"
    # No longer claimable, by anyone, even once the lease would have expired.
    again, _ = _effectful(query, catalog, "claim_work", {"requester": "agent-2"}, at=1e9)
    assert again == {"claimed": False, "reason": "no eligible work", "skipped_without_accession": 0}
    # The pathway is recorded, not inferred, and names who recorded it.
    history = query.status(accession="ACC-A")["history"]
    assert [t["to_state"] for t in history][-1] == "certified"
    assert history[-1]["actor"] == "agent-1" and digest in history[-1]["reason"]
    # The reply is the blind view: recording work never reveals a ground-truth label.
    assert "ground_truth" not in json.dumps(done)


def test_a_recorded_result_cannot_claim_more_than_its_certificate() -> None:
    catalog, query, digest = _recording_fixture()
    ledger = query._ledger
    failed = ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper A", doi="10.1/a"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC",
                                     verdict=Verdict.FAILED, source_location="Table 1",
                                     root_cause="parameter mismatch")],
    ))
    _claim(query, catalog, "a")
    done, _ = _effectful(query, catalog, "record_result",
                         {"accession": "ACC-A", "requester": "a", "digest": failed})
    # The state comes from the certificate's verdict, never from the caller.
    assert done["recorded"] and done["state"] == "failed"
    assert digest != failed


def test_recording_refuses_another_papers_certificate() -> None:
    catalog, query, _ = _recording_fixture()
    other = query._ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper B", doi="10.2/b"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
    ))
    _claim(query, catalog, "a")
    text, is_error = _effectful(query, catalog, "record_result",
                                {"accession": "ACC-A", "requester": "a", "digest": other})
    assert is_error and "different paper" in text
    assert catalog.find(Identifiers(title="", accession="ACC-A")).state.value == "queued"


def test_recording_refuses_an_unknown_certificate_a_non_holder_and_a_repeat() -> None:
    catalog, query, digest = _recording_fixture()
    unclaimed, _ = _effectful(query, catalog, "record_result",
                              {"accession": "ACC-A", "requester": "a", "digest": digest})
    # Recording asserts that this requester did the work, so an unclaimed entry is refused:
    # otherwise any caller could file a result against a unit they never took.
    assert unclaimed == {"recorded": False, "reason": "not the lease holder"}
    _claim(query, catalog, "a")
    unknown, _ = _effectful(query, catalog, "record_result",
                            {"accession": "ACC-A", "requester": "a", "digest": "deadbeef"})
    assert unknown == {"recorded": False, "reason": "unknown certificate"}
    missing, _ = _effectful(query, catalog, "record_result",
                            {"accession": "NOPE", "requester": "a", "digest": digest})
    assert missing == {"recorded": False, "reason": "unknown entry"}

    _effectful(query, catalog, "claim_work", {"requester": "agent-1", "lease_seconds": 60})
    held, _ = _effectful(query, catalog, "record_result",
                         {"accession": "ACC-A", "requester": "agent-2", "digest": digest})
    assert held == {"recorded": False, "reason": "not the lease holder"}
    # An expired lease is not a hold — the entry is back in the pool — but recording is the claim
    # that this requester did the work, so the agent that finished it takes the lease and records
    # under it rather than filing against a unit nobody holds.
    stale, _ = _effectful(query, catalog, "record_result",
                          {"accession": "ACC-A", "requester": "agent-2", "digest": digest}, at=1e9)
    assert stale == {"recorded": False, "reason": "not the lease holder"}
    _claim(query, catalog, "agent-2", at=1e9)
    done, _ = _effectful(query, catalog, "record_result",
                         {"accession": "ACC-A", "requester": "agent-2", "digest": digest}, at=1e9)
    assert done["recorded"]
    # Recording it twice does not double-record: it refuses rather than silently no-op.
    twice, _ = _effectful(query, catalog, "record_result",
                          {"accession": "ACC-A", "requester": "agent-2", "digest": digest}, at=1e9)
    assert twice == {"recorded": False, "reason": "entry is already certified"}


def test_a_blocked_entry_can_be_returned_to_the_queue() -> None:
    # The lifecycle always permitted blocked -> queued; no surface performed it, so an entry
    # blocked on a missing supplement stayed out of the backlog even once it arrived.
    catalog, query, _ = _recording_fixture()
    blocked = query._ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper A", doi="10.1/a"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=(), gap_report=("the supplement with the dosing schedule is paywalled",),
    ))
    _claim(query, catalog, "a")
    done, _ = _effectful(query, catalog, "record_result",
                         {"accession": "ACC-A", "requester": "a", "digest": blocked})
    assert done["recorded"] and done["state"] == "blocked"
    entry = catalog.find(Identifiers(title="", accession="ACC-A"))
    assert entry.history[-1].missing_inputs == ("the supplement with the dosing schedule is paywalled",)

    back, is_error = _effectful(query, catalog, "requeue_entry",
                                {"accession": "ACC-A", "requester": "curator",
                                 "reason": "the author sent the dosing schedule"})
    assert not is_error and back["requeued"] and back["state"] == "queued"
    assert entry.history[-1].reason == "the author sent the dosing schedule"
    claim, _ = _effectful(query, catalog, "claim_work", {"requester": "agent-9"})
    assert claim["claimed"]


def test_requeue_refuses_every_state_except_blocked() -> None:
    # Leaning on the state machine alone was not enough: it permits failed -> queued and
    # quarantined -> queued, so a caller could requeue a recorded failure and record a success
    # over the top (laundering a verdict), or undo a curator's quarantine.
    from reprolith.enums import LifecycleState

    for state in LifecycleState:
        catalog, query, _ = _recording_fixture()
        entry = catalog.find(Identifiers(title="", accession="ACC-A"))
        entry._state = state
        result, _ = _effectful(query, catalog, "requeue_entry",
                               {"accession": "ACC-A", "requester": "c", "reason": "why"})
        assert result["requeued"] is (state is LifecycleState.BLOCKED), state


def test_a_recorded_failure_cannot_be_laundered_into_a_certification() -> None:
    catalog, query, _ = _recording_fixture()
    failed = query._ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper A", doi="10.1/a"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.FAILED,
                                     source_location="Table 1", root_cause="parameter mismatch")],
    ))
    _claim(query, catalog, "a")
    done, _ = _effectful(query, catalog, "record_result",
                         {"accession": "ACC-A", "requester": "a", "digest": failed})
    assert done["state"] == "failed"
    back, _ = _effectful(query, catalog, "requeue_entry",
                         {"accession": "ACC-A", "requester": "a", "reason": "try again"})
    assert back == {"requeued": False, "reason": "entry is failed, not blocked"}


def test_recording_tools_are_refused_on_a_read_only_server() -> None:
    query, digest = _fixture()
    for name, args in (("record_result", {"accession": "A", "requester": "r", "digest": digest}),
                       ("requeue_entry", {"accession": "A", "requester": "r", "reason": "x"})):
        resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": name, "arguments": args}})
        assert resp["result"]["isError"]


def test_a_certificate_must_positively_identify_the_entrys_paper() -> None:
    # Refusing only a *contradiction* on doi/pubmed is vacuous here: no entry in the shipped
    # catalog carries either, so every certificate ever issued passed the check and any caller
    # could file the metformin reproduction under any accession they liked.
    catalog = Catalog()
    catalog.add(Identifiers(title="A Paper Nobody Reproduced", accession="ATTACK-1"))
    ledger = CertificateLedger()
    digest = ledger.issue(build_certificate(
        paper=PaperIdentity(title="Zake2021 - PBPK model of metformin", doi="10.1371/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="Cmax", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
    ))
    query = ReprolithQuery(catalog, ledger)
    _claim(query, catalog, "a")
    text, is_error = _effectful(query, catalog, "record_result",
                                {"accession": "ATTACK-1", "requester": "a", "digest": digest})
    # Two rules now refuse this, and the general one speaks first: `require_same_paper` no longer
    # goes quiet when only one side states a DOI, so an unrelated title is refused before the
    # MCP-specific positive-identity rule is reached. Either message is an honest refusal of the
    # same attack; what matters is that it is refused and the entry does not move.
    assert is_error and "is for a different paper" in text
    assert "A Paper Nobody Reproduced" in text and "Zake2021" in text
    assert catalog.find(Identifiers(title="", accession="ATTACK-1")).state.value == "queued"
    # A title is a sufficient witness when nothing stronger exists on either side — it is the
    # one identifier every record carries — and normalization makes it robust to case/spacing.
    catalog.add(Identifiers(title="  zake2021 - PBPK MODEL of  metformin ", accession="OK-1"))
    _claim(query, catalog, "a")  # the new entry is the only unleased one left
    done, is_error = _effectful(query, catalog, "record_result",
                                {"accession": "OK-1", "requester": "a", "digest": digest})
    assert not is_error and done["recorded"]


def test_a_superseded_certificate_is_not_recordable() -> None:
    catalog, query, digest = _recording_fixture()
    correction = query._ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper A", doi="10.1/a"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.FAILED,
                                     source_location="Table 1", root_cause="parameter mismatch")],
        supersedes=query.certificate_object(digest),
    ))
    _claim(query, catalog, "a")
    stale, _ = _effectful(query, catalog, "record_result",
                          {"accession": "ACC-A", "requester": "a", "digest": digest})
    assert stale == {"recorded": False,
                     "reason": "that certificate has been superseded; record the correction instead"}
    current, _ = _effectful(query, catalog, "record_result",
                            {"accession": "ACC-A", "requester": "a", "digest": correction})
    assert current["recorded"] and current["state"] == "failed"


def test_submitting_a_paper_reveals_nothing_about_the_graded_set() -> None:
    # The frozen-identity refusal fired only for a labelled entry, which made submit_paper a
    # membership oracle for the blind test set: probe each accession with a junk identifier and
    # read the partition off which ones refuse.
    def transcript(labelled: bool) -> list:
        catalog = Catalog()
        catalog.add(
            Identifiers(title="Paper A", accession="ACC-A"), ModelClass.ODE_PKPD,
            ground_truth=(GroundTruth(expected=OverallVerdict.REPRODUCED, source="curation")
                          if labelled else None),
        )
        query = ReprolithQuery(catalog, CertificateLedger())
        return [_effectful(query, catalog, "submit_paper",
                           {"title": "Paper A", "pubmed_id": "probe-1"}),
                _effectful(query, catalog, "list_catalog", {}),
                _effectful(query, catalog, "status", {"accession": "ACC-A"})]

    # Nothing an entry-level read or write returns distinguishes the two catalogs. (The aggregate
    # labelled/unlabelled counts in backlog_health are published on purpose: they say how much of
    # the backlog is graded, never which entries.)
    assert transcript(labelled=True) == transcript(labelled=False)
    # The submission still resolves to the one entry, and says what it did not record.
    reply = transcript(labelled=True)[0][0]
    assert reply["resolved_to_existing"] and reply["identifiers_not_recorded"] == ["pubmed_id"]


def test_a_change_that_cannot_be_persisted_is_rolled_back() -> None:
    # on_change() runs after the in-memory mutation; an OSError there left memory permanently
    # ahead of disk, and every later save persisted a state that was never durable.
    catalog, query, digest = _recording_fixture()

    def refuse_to_save() -> None:
        raise OSError(28, "No space left on device")

    resp = handle_request(query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "record_result",
                                             "arguments": {"accession": "ACC-A",
                                                           "requester": "a", "digest": digest}}},
                          catalog=catalog, on_change=refuse_to_save, now=lambda: 0.0)
    assert resp["result"]["isError"]
    assert "rolled back" in resp["result"]["content"][0]["text"]
    entry = catalog.find(Identifiers(title="", accession="ACC-A"))
    assert entry.state.value == "queued" and entry.history == ()


def test_a_saved_catalog_that_contradicts_itself_is_refused() -> None:
    import pytest
    from reprolith.catalog import Catalog as C

    catalog = Catalog()
    catalog.add(Identifiers(title="Paper A", accession="ACC-A"))
    sound = catalog.to_dict()
    C.from_dict(sound)  # the honest file still loads

    state_without_history = json.loads(json.dumps(sound))
    state_without_history["entries"][0]["state"] = "certified"
    blocked_without_inputs = json.loads(json.dumps(sound))
    blocked_without_inputs["entries"][0]["state"] = "blocked"
    unusable_lease = json.loads(json.dumps(sound))
    unusable_lease["entries"][0]["lease_expires"] = "soon"
    for corrupt in (state_without_history, blocked_without_inputs, unusable_lease):
        with pytest.raises(ValueError):
            C.from_dict(corrupt)


def test_a_recorded_history_is_stamped_by_the_server_not_the_caller() -> None:
    """The record of when a paper was certified was free text the recorder supplied.

    `at` was taken verbatim, unparsed, so a caller could date the entire pathway to any year it
    liked — and a reader has no way to tell a recorded timestamp from an asserted one.
    """
    catalog, query, digest = _recording_fixture()
    _claim(query, catalog, "a", at=1_000_000.0)
    done, _ = _effectful(
        query, catalog, "record_result",
        {"accession": "ACC-A", "requester": "a", "digest": digest, "at": "1999-01-01T00:00:00+00:00"},
        at=1_000_000.0,
    )
    assert done["recorded"]
    entry = catalog.find(Identifiers(title="", accession="ACC-A"))
    stamps = {t.at for t in entry.history}
    assert "1999-01-01T00:00:00+00:00" not in stamps
    assert all(t.at.startswith("1970-01-12") for t in entry.history[-6:])  # the server clock

    # And the parameter is gone from the advertised schema, so nothing invites the attempt.
    tools = {t["name"]: t for t in EFFECTFUL_TOOLS}
    assert "at" not in tools["record_result"]["inputSchema"]["properties"]
    assert "at" not in tools["requeue_entry"]["inputSchema"]["properties"]



def test_an_entry_cannot_cycle_through_the_queue_forever() -> None:
    """blocked -> queued -> blocked is a free cycle, and every lap grows a history nothing prunes.

    Fifty laps grew one entry's record to 150 transitions and the catalog file both surfaces read
    at startup to 37 KiB. An entry requeued this many times is not waiting on a missing input any
    more.
    """
    catalog, query, _ = _recording_fixture()
    blocked = query._ledger.issue(build_certificate(
        paper=PaperIdentity(title="Paper A", doi="10.1/a"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=(), gap_report=("the supplement is paywalled",),
    ))
    outcomes = []
    for _ in range(7):
        _claim(query, catalog, "a")
        _effectful(query, catalog, "record_result",
                   {"accession": "ACC-A", "requester": "a", "digest": blocked})
        back, _ = _effectful(query, catalog, "requeue_entry",
                             {"accession": "ACC-A", "requester": "a", "reason": "it arrived"})
        outcomes.append(back["requeued"])
        if not back["requeued"]:
            assert "needs review" in back["reason"]
            break
    assert outcomes[0] is True and outcomes[-1] is False
    entry = catalog.find(Identifiers(title="", accession="ACC-A"))
    assert len(entry.history) < 40  # bounded, not one-fifty-per-fifty-laps


def test_an_entry_with_no_accession_is_not_handed_out_as_work() -> None:
    """A leased entry the surface cannot address again is a strand, not a work unit.

    `submit_paper` needs only a title, and both `release_work` and `record_result` resolve an
    entry by accession — so such an entry could be claimed and then neither finished nor handed
    back, stranding until the lease expired and it was offered again, indefinitely.
    """
    from reprolith.catalog import Catalog, Identifiers, ModelClass
    from reprolith.mcp_server import claim_work, release_work

    catalog = Catalog()
    catalog.add(Identifiers(title="a paper with no accession"), model_class=ModelClass.ODE_PKPD)
    claimed = claim_work(catalog, {"requester": "agentA"}, at=1000.0)
    assert claimed["claimed"] is False
    assert "no accession" in claimed["reason"]
    # And it is genuinely back in the pool rather than silently leased.
    assert catalog.claimable(1000.0)
    assert release_work(catalog, {"accession": "", "requester": "agentA"})["released"] is False


def test_record_result_returns_the_verdict_with_its_scope_not_a_bare_string() -> None:
    """The one effectful reply that carried a verdict used to carry it stripped of everything else.

    Every read tool returns a verdict through `ReprolithQuery`, where the "never a bare verdict"
    invariant lives. `record_result` built its own reply, so the moment an agent finished a unit it
    was handed `"overall": "partially-reproduced"` with no scope flag and no note that the result
    rested on an assumption Reprolith supplied.
    """
    catalog, query, digest = _recording_fixture()
    _effectful(query, catalog, "claim_work", {"requester": "agent-1", "lease_seconds": 60})

    done, is_error = _effectful(query, catalog, "record_result",
                                {"accession": "ACC-A", "requester": "agent-1", "digest": digest})
    assert not is_error and done["recorded"]
    assert done["verdict"] == query.verdict(digest)
    assert done["verdict"]["scope"]["machine"]
    assert done["verdict"]["overall"] == done["overall"]


def test_an_explicit_data_dir_is_read_exactly_as_given_on_both_surfaces() -> None:
    """`--data-dir X` must mean the same thing to an agent as it does to a human at a terminal.

    The server aggregated every class's committed milestone certificates regardless of the flag, so
    pointing it at an empty directory still reported six classes and 60 labelled entries — and
    since the aggregate ledger is what `record_result` validates a digest against, an agent could
    certify an entry against a certificate the operator's directory has never held.
    """
    import tempfile
    from unittest.mock import patch

    from reprolith.mcp_server import main

    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        (sandbox / "catalog.json").write_text(json.dumps(Catalog().to_dict()), encoding="utf-8")
        (sandbox / "certificates").mkdir()
        seen: dict[str, object] = {}

        def capture(query, *, catalog, on_change, now, guard=None):  # noqa: ANN001
            seen["digests"] = tuple(query._ledger.items())

        with patch("reprolith.mcp_server.serve_stdio", capture):
            main(["--data-dir", str(sandbox)])
        assert seen["digests"] == (), "an empty data dir must serve an empty ledger"


def test_an_effectful_call_applies_to_the_current_catalog_not_a_startup_snapshot() -> None:
    """stdio MCP is one server process per client, so "concurrent requesters" means processes.

    Each server mutated a catalog it loaded once at startup and rewrote the whole file, so two
    agents were handed the same unit and one agent's unrelated `submit_paper` erased another's
    recorded certification along with all six of its transitions — the two live surfaces and the
    CLI then gave three different answers for one entry's state. The guard is held across the whole
    read-modify-write and re-reads the catalog under it, so a mutation applies to what is on disk.
    """
    from contextlib import contextmanager

    catalog, query, _ = _recording_fixture()
    # What another server process wrote while this one was idle: the entry is already leased.
    elsewhere = Catalog.from_dict(catalog.to_dict())
    elsewhere.find(Identifiers(title="", accession="ACC-A")).lease(
        "agent-elsewhere", at=0.0, seconds=3600
    )
    other_process_state = elsewhere.to_dict()

    @contextmanager
    def guard():
        catalog.restore(other_process_state)  # what re-reading the file under the lock does
        yield

    resp = handle_request(
        query,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "claim_work", "arguments": {"requester": "agent-late"}}},
        catalog=catalog, now=lambda: 0.0, guard=guard,
    )
    claimed = json.loads(resp["result"]["content"][0]["text"])
    assert claimed == {"claimed": False, "reason": "no eligible work", "skipped_without_accession": 0}
    assert catalog.find(Identifiers(title="", accession="ACC-A")).leased_to == "agent-elsewhere"


def test_an_accession_less_entry_is_stepped_over_not_left_blocking_the_queue() -> None:
    """Refusing the head of the queue and returning let one entry withhold every entry behind it.

    `release_work` and `record_result` both address an entry by accession, so an entry without one
    cannot be finished or handed back and must not be leased. It was refused — and the refusal
    stopped there. `seed_candidates` gives every un-curated candidate no accession and nothing in
    this surface can add one (`submit_paper` does not merge identifiers into an existing entry), so
    a single such entry jammed the whole queue permanently while `backlog_health` went on
    publishing it as claimable.
    """
    from reprolith.enums import ModelClass as _ModelClass
    from reprolith.mcp_server import claim_work

    catalog = Catalog()
    # Un-curated first: `claimable` ranks by readiness, and these carry no difficulty, so they sort
    # ahead of the workable entry — which is exactly the ordering that used to be fatal.
    catalog.add(Identifiers(title="Un-curated one"), _ModelClass.ODE_PKPD)
    catalog.add(Identifiers(title="Un-curated two"), _ModelClass.ODE_PKPD)
    catalog.add(Identifiers(title="Workable", accession="BIOMD0000000012"),
                _ModelClass.ODE_PKPD, difficulty="high")

    claimed = claim_work(catalog, {"requester": "agent-1"}, at=0.0)
    assert claimed["claimed"] is True
    assert claimed["entry"]["identifiers"]["accession"] == "BIOMD0000000012"
    # The claimant is told why the two ahead of it were passed over.
    assert claimed["skipped_without_accession"] == 2

    exhausted = claim_work(catalog, {"requester": "agent-2"}, at=0.0)
    assert exhausted["claimed"] is False
    assert exhausted["skipped_without_accession"] == 2
    assert "no accession" in exhausted["reason"]


def test_a_blank_catalog_is_refused_not_overwritten_with_a_startup_snapshot(tmp_path) -> None:
    """Blank is not the same as absent, and skipping the re-read lost every write since start-up.

    The guard re-reads the catalog under its lock so a mutation applies to current state. For an
    empty file it skipped the re-read, mutated this process's start-up snapshot and wrote *that*
    back whole — destroying every entry and transition another process had written, while replying
    as if the call had succeeded. Reachable: the milestone scripts rewrite this file, and a crash
    mid-write leaves it at zero length. Start-up already refuses a blank catalog, and this function
    already refuses a corrupt-but-non-empty one; it was the third reader of one condition.
    """
    from reprolith.enums import ModelClass as _ModelClass
    from reprolith.mcp_server import refresh_catalog_from_disk

    catalog_file = tmp_path / "catalog.json"
    loaded = Catalog()
    loaded.add(Identifiers(title="A", accession="A1"), _ModelClass.ODE_PKPD)

    # A genuine first run has no file at all, and is left alone.
    refresh_catalog_from_disk(loaded, catalog_file)
    assert len(loaded) == 1

    # A blank file beside a non-empty catalog is refused rather than silently reverted.
    catalog_file.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="exists but is empty"):
        refresh_catalog_from_disk(loaded, catalog_file)

    # A real file is read, and is what the mutation then applies to.
    other = Catalog()
    other.add(Identifiers(title="B", accession="B2"), _ModelClass.ODE_PKPD)
    other.add(Identifiers(title="C", accession="C3"), _ModelClass.ODE_PKPD)
    catalog_file.write_text(json.dumps(other.to_dict()), encoding="utf-8")
    refresh_catalog_from_disk(loaded, catalog_file)
    assert {e.identifiers.accession for e in loaded.entries} == {"B2", "C3"}


def test_a_correction_published_after_startup_is_seen_by_the_write_path(tmp_path) -> None:
    """The ledger was a start-up snapshot, and supersession is expressed by *adding* a file.

    So `record_result`'s refusal to record a superseded certificate was decided against the set as
    it stood when the process started: a correction published into the same data directory
    afterwards was invisible, and the retracted verdict went into the entry's permanent lifecycle
    history while the CLI reading that same directory reported it superseded.
    """
    from reprolith.mcp_server import refresh_certificates

    directory = tmp_path / "certificates"
    directory.mkdir()
    ledger = CertificateLedger()
    seen: dict[Path, tuple[tuple[str, int, int], ...]] = {}

    original = build_certificate(
        paper=PaperIdentity(title="A paper", doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
    )
    (directory / "original.json").write_text(json.dumps(original.content()), encoding="utf-8")
    refresh_certificates(ledger, [directory], seen)
    first = certificate_digest(original)
    assert ledger.get(first) is not None
    assert not [c for _, c in ledger.items() if c.supersedes == first]

    # A correction lands after that first load; the mtime moves, so the next pass picks it up.
    correction = build_certificate(
        paper=PaperIdentity(title="A paper", doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="Table 1")],
        supersedes=original,
    )
    (directory / "correction.json").write_text(json.dumps(correction.content()), encoding="utf-8")
    refresh_certificates(ledger, [directory], seen)
    assert [c.supersedes for _, c in ledger.items() if c.supersedes] == [first]

    # …and a correction republished *in place*, which is how every milestone script writes a
    # certificate. A directory's mtime does not move for an in-place rewrite, so keying on it left
    # exactly this case invisible for the life of the process.
    ledger_two = CertificateLedger()
    seen_two: dict[Path, tuple[tuple[str, int, int], ...]] = {}
    single = tmp_path / "single"
    single.mkdir()
    target = single / "BIOMD0000000001.json"
    target.write_text(json.dumps(original.content()), encoding="utf-8")
    refresh_certificates(ledger_two, [single], seen_two)
    assert len(ledger_two) == 1
    target.write_text(json.dumps(correction.content()), encoding="utf-8")
    refresh_certificates(ledger_two, [single], seen_two)
    assert [c.supersedes for _, c in ledger_two.items() if c.supersedes] == [first]

    # An unreadable certificate raises — and does not mark the directory seen, or every valid file
    # beside it would go unread for the rest of the run.
    (single / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not a readable certificate"):
        refresh_certificates(ledger_two, [single], seen_two)
    with pytest.raises(ValueError, match="not a readable certificate"):
        refresh_certificates(ledger_two, [single], seen_two)


def test_a_missing_agreement_report_is_refused_rather_than_skipped(tmp_path, monkeypatch) -> None:
    """Skipped, a whole class simply vanished from the published track record.

    `self_validation_summary` publishes `classes` and `labelled_entries` as sums over whatever it
    found, so removing one report turned 60 labelled entries into 57 and six classes into five —
    asserted as the whole truth, on a page still rendering that class's three certificates. The
    raise was added for that, and nothing pinned it: reverting it to `continue` left the whole
    suite green.
    """
    from reprolith import mcp_server

    real = mcp_server.milestone_certificate_dirs()
    absent = tmp_path / "nowhere" / "certificates"
    monkeypatch.setattr(
        mcp_server, "milestone_certificate_dirs", lambda: {**real, "invented": absent}
    )
    with pytest.raises(FileNotFoundError, match="no agreement report for the 'invented' class"):
        mcp_server.milestone_agreement_reports()

    # Unpatched, every declared class must have one — the count is the point, not just the loop.
    monkeypatch.undo()
    assert len(mcp_server.milestone_agreement_reports()) == len(real) == 6


def test_positional_params_are_an_invalid_params_error_not_a_crash() -> None:
    """JSON-RPC allows an array of params; every method here takes named ones. Reaching `.get` on
    a list raised out of the handler, which is a server dying on a request it should refuse."""
    query, _ = _fixture()
    response = handle_request(
        query, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1, 2]}
    )
    assert response is not None
    assert response["error"]["code"] == -32602
    assert "expected an object" in response["error"]["message"]


def test_arguments_that_are_not_an_object_are_refused_in_words() -> None:
    """It came back as "string indices must be integers" — a Python message published to an agent
    by the surface whose whole job is saying what went wrong."""
    query, _ = _fixture()
    payload, is_error = _call(query, "certificate", "notadict")
    assert is_error
    assert "'arguments' must be an object, not str" in payload


def test_an_argument_of_the_wrong_type_is_refused_rather_than_looked_up() -> None:
    """A digest passed as a number reached the ledger, matched nothing, and came back `null` —
    filed under "no such certificate" instead of "that is not a digest". The schema every agent
    is handed by tools/list is now the check it looks like."""
    query, _ = _fixture()
    payload, is_error = _call(query, "certificate", {"digest": 123})
    assert is_error
    assert "'digest' must be string, not int" in payload

    payload, is_error = _call(query, "lint", {
        "sbml": "x", "species": "y", "reference": 1, "duration": 1.0, "steps": 1,
    })
    assert is_error and "'reference' must be array, not int" in payload

    # A bool is an int in Python and is not a number anywhere a caller means it.
    payload, is_error = _call(query, "lint_estimation", {"reported": True, "recovered": 1.0})
    assert is_error and "'reported' must be number, not bool" in payload


def test_a_lookup_naming_no_paper_says_so_instead_of_answering_none() -> None:
    """A misspelled field — `pmid` for `pubmed_id` — was ignored, leaving a lookup with no
    identifier at all, which answers `[]`: this paper has no certificates. A confident wrong
    answer to a question nobody managed to ask."""
    query, _ = _fixture()
    payload, is_error = _call(query, "certificates_for", {"pmid": "12345"})
    assert is_error
    assert "name the paper by one of" in payload and "passed pmid" in payload

    payload, is_error = _call(query, "status", {})
    assert is_error and "name the paper by one of" in payload


def test_a_well_formed_lookup_is_untouched() -> None:
    """The refusals above are about malformed calls; a real one still answers."""
    query, digest = _fixture()
    payload, is_error = _call(query, "certificates_for", {"doi": "10.1/x"})
    assert not is_error and payload == [digest]
