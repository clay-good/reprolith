"""A read-only MCP server over the query surface (spec: ``mcp-server``).

Reprolith's agent-facing surface: an MCP server exposing the same catalog, status, certificate,
and gap queries a human reads through the repository, so an agent can call Reprolith mid-workflow
as a deterministic reproducibility oracle. Every tool here is read-only and side-effect-free
(spec: "Read-only and effectful tools are separated"), and every verdict returned carries its
scope flag and qualifications because the tools delegate to :class:`~reprolith.query.ReprolithQuery`
— the server computes no verdict of its own, so it cannot diverge from the repository ("Parity
with the human surface").

MCP is JSON-RPC 2.0 over stdio, so this needs no third-party SDK: :func:`handle_request` is a pure
function from a request object to a response object (testable without any I/O), and
:func:`serve_stdio` is the newline-delimited stdio loop around it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import IO, Any

from .query import ReprolithQuery
from .supersession import CertificateLedger

PROTOCOL_VERSION = "2024-11-05"

_ONE_DIGEST = {
    "type": "object",
    "properties": {"digest": {"type": "string", "description": "the certificate's content digest"}},
    "required": ["digest"],
}
_IDENTIFIER = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "doi": {"type": "string"},
        "pubmed_id": {"type": "string"},
        "accession": {"type": "string"},
    },
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_catalog",
        "description": "Browse catalog entries as blind public views (no ground-truth label).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "status",
        "description": "A paper's lifecycle status and recorded history, by identifier.",
        "inputSchema": _IDENTIFIER,
    },
    {
        "name": "certificate",
        "description": "The full certificate for a digest: content, verdicts, scope, and gaps.",
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "verdict",
        "description": "The scope-qualified verdict for a digest (never a bare boolean).",
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "gaps",
        "description": "The structured 'what was missing' report for a digest.",
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "certificates_for",
        "description": "Digests of every certificate issued for a paper, newest first.",
        "inputSchema": _IDENTIFIER,
    },
    {
        "name": "lint",
        "description": (
            "Deterministic linter: run a supplied SBML model under the pinned engine and judge "
            "a species curve against a claim's reference points. Needs the engine extra."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sbml": {"type": "string", "description": "the SBML model to run"},
                "species": {"type": "string", "description": "the output species to read"},
                "reference": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "reference values at the same steps+1 sample points",
                },
                "duration": {"type": "number"},
                "steps": {"type": "integer"},
            },
            "required": ["sbml", "species", "reference", "duration", "steps"],
        },
    },
]


def dispatch_tool(query: ReprolithQuery, name: str, arguments: dict[str, Any]) -> Any:
    """Call the named read-only query tool with the given arguments."""
    if name == "list_catalog":
        return query.list_catalog()
    if name == "status":
        return query.status(**_identifier_kwargs(arguments))
    if name == "certificate":
        return query.certificate(arguments["digest"])
    if name == "verdict":
        return query.verdict(arguments["digest"])
    if name == "gaps":
        return query.gaps(arguments["digest"])
    if name == "certificates_for":
        return query.certificates_for(**_identifier_kwargs(arguments))
    if name == "lint":
        from .linter import lint_curve

        result = lint_curve(
            arguments["sbml"],
            arguments["species"],
            reference=tuple(arguments["reference"]),
            duration=arguments["duration"],
            steps=arguments["steps"],
        )
        return result.to_dict()
    raise KeyError(f"unknown tool: {name}")


def _identifier_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    return {k: arguments[k] for k in ("title", "doi", "pubmed_id", "accession") if k in arguments}


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(query: ReprolithQuery, request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC request; return the response, or ``None`` for a notification.

    Implements the MCP methods a read-only server needs: ``initialize``, ``tools/list``, and
    ``tools/call`` (plus the ``notifications/initialized`` notification, which has no response).
    """
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "reprolith", "version": _version()},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _result(request_id, {"tools": TOOL_DEFINITIONS})
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            data = dispatch_tool(query, name, arguments)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            # Unknown tool / bad args, a length mismatch, or the engine being absent or diverging
            # (EngineUnavailable and NonFiniteSimulation are RuntimeErrors) are tool-level errors:
            # report them to the caller rather than crash the server.
            return _result(
                request_id,
                {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True},
            )
        return _result(
            request_id,
            {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}]},
        )

    if request_id is None:
        return None  # an unknown notification
    return _error(request_id, -32601, f"method not found: {method}")


def serve_stdio(
    query: ReprolithQuery,
    *,
    reader: IO[str] | None = None,
    writer: IO[str] | None = None,
) -> None:
    """Serve the read-only surface over newline-delimited JSON-RPC on stdio."""
    reader = reader or sys.stdin
    writer = writer or sys.stdout
    for line in reader:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        response = handle_request(query, request)
        if response is not None:
            writer.write(json.dumps(response) + "\n")
            writer.flush()


def _version() -> str:
    from . import __version__

    return __version__


def load_certificates(ledger: CertificateLedger, directory: Path | str) -> int:
    """Load every stored certificate JSON in ``directory`` into ``ledger``; return the count.

    Each file is a certificate's ``content`` dict; reloading is dependency-free (no engine),
    so the server can serve real certificates produced earlier by the milestone run.
    """
    from .persistence import certificate_from_content

    path = Path(directory)
    loaded = 0
    if path.is_dir():
        for file in sorted(path.glob("*.json")):
            ledger.issue(certificate_from_content(json.loads(file.read_text(encoding="utf-8"))))
            loaded += 1
    return loaded


def main() -> None:  # pragma: no cover - stdio entry point
    """Run the server over stdio, loading the persisted catalog and certificates if present."""
    import json

    from .catalog import Catalog
    from .seed import seed_catalog

    milestone = Path(__file__).resolve().parents[2] / "datasets" / "milestone"
    catalog_file = milestone / "catalog.json"
    if catalog_file.is_file():
        catalog = Catalog.from_dict(json.loads(catalog_file.read_text(encoding="utf-8")))  # the run's real progress
    else:
        catalog = Catalog()
        seed_catalog(catalog)
    ledger = CertificateLedger()
    load_certificates(ledger, milestone / "certificates")
    serve_stdio(ReprolithQuery(catalog, ledger))


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "PROTOCOL_VERSION",
    "TOOL_DEFINITIONS",
    "dispatch_tool",
    "handle_request",
    "load_certificates",
    "serve_stdio",
]
