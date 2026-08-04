# Reprolith MCP server

Reprolith exposes its catalog, certificates, and reproducibility engine to AI agents over the
Model Context Protocol, so an agent can call it mid-workflow as a deterministic reproducibility
oracle. The server is read-only plus an inline linter: every tool returns data and changes no
state, and every verdict travels with its scope flag and qualifications.

## Run it

The server speaks JSON-RPC over stdio and needs no third-party MCP SDK. Install and run:

```bash
pip install -e .
reprolith-mcp
```

The `lint` tool additionally needs the optional engine extra (`pip install -e ".[engine]"`); the
other tools work without it. On start-up the server loads the labelled catalog and, if a
milestone run has been recorded, its certificates, dossiers, and bundles.

## Register it in an MCP client

Point any MCP client at the `reprolith-mcp` command over stdio. For a Claude Desktop-style
`mcpServers` config:

```json
{
  "mcpServers": {
    "reprolith": {
      "command": "reprolith-mcp"
    }
  }
}
```

## Tools

All read-only. A verdict is never a bare boolean — it carries the scope flag and per-claim
qualifications.

| Tool | Arguments | Returns |
|---|---|---|
| `list_catalog` | — | Catalog entries as blind views (no ground-truth label) |
| `status` | `title`/`doi`/`pubmed_id`/`accession` | A paper's lifecycle state and recorded history |
| `certificate` | `digest` | The full certificate: content, verdicts, scope, gaps |
| `verdict` | `digest` | The scope-qualified verdict (overall + per-claim + counts) |
| `gaps` | `digest` | The structured "what was missing" report |
| `certificates_for` | `title`/`doi`/… | Digests of every certificate for a paper, newest first |
| `dossier` | `accession` | The ingested dossier — extracted model structure |
| `bundle` | `accession` | The reconstruction bundle — model, recipe, assumptions |
| `lint` | `sbml`, `species`, `reference`, `duration`, `steps` | A deterministic per-claim verdict (needs the engine extra) |

## Example

Find the metformin certificate and read its verdict (JSON-RPC over stdio):

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"certificates_for","arguments":{"title":"Zake2021 - PBPK model of metformin in humans, single PO dose"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"verdict","arguments":{"digest":"<digest from id 1>"}}}
```

The verdict comes back `partially-reproduced` — the model reproduces its paper's reported Cmax,
but only under a load-bearing salt-form assumption, which the certificate flags. See
[`../datasets/worked_examples/`](../datasets/worked_examples/) for that certificate in full.

## Parity

The server computes no verdict of its own: every tool delegates to the same query surface and
oracle the repository uses, so it can never disagree with the repository. Effectful work handoff
(submitting a paper, claiming work, leasing) is deliberately not part of this surface in the
MVP — the repository is the work surface for that.
