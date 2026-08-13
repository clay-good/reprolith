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
| `presubmission` | `digest` | Author-facing pre-submission check: readiness + prioritized fix list |
| `certificates_for` | `title`/`doi`/… | Digests of every certificate for a paper, newest first |
| `backlog_health` | — | Backlog depth by state, class, and difficulty, and the labelled mix |
| `dossier` | `accession` | The ingested dossier — extracted model structure |
| `bundle` | `accession` | The reconstruction bundle — model, recipe, assumptions |
| `lint` | `sbml`, `species`, `reference`, `duration`, `steps` | A deterministic per-claim verdict for an ODE model curve (needs the engine extra) |
| `lint_objective` | `sbml`, `reported`, `medium` (optional) | A deterministic verdict for an SBML-fbc model's optimal objective under an optional medium (needs the engine and fba extras) |
| `lint_steady_state` | `rules`, `reported` | A deterministic verdict on whether a reported steady state is a fixed point of a supplied Boolean network (pure, no extra) |
| `lint_estimation` | `reported`, `recovered` | A deterministic verdict on a re-derived parameter estimate vs a reported one, at the estimation tolerance (pure, no extra) |
| `lint_distribution` | `reported`, `predicted` | A deterministic verdict on a simulated percentile envelope vs a reported one, worst-band governed (pure, no extra) |
| `lint_stochastic` | `sbml`, `species`, `reported_mean`, `duration`, `trajectories`, `seed` | A deterministic verdict on an SBML reaction network's mean species count via a pinned Gillespie SSA (needs the engine extra) |
| `lint_diffusion` | `initial`, `reference`, `diffusivity`, `dx`, `dt`, `steps` | A deterministic verdict on a 1-D diffusion profile vs a reported one, by curve distance (pure, no extra) |

## Effectful tool

Kept separate from the read-only tools, and offered only when the server runs with a mutable
catalog (as `reprolith-mcp` does):

| Tool | Arguments | Effect |
|---|---|---|
| `submit_paper` | `title` (required), `doi`/`pubmed_id`/`accession`/`model_class` | Adds a candidate paper as a queued `ode-pkpd` entry and reports what changed. Submitting the same paper again resolves to the existing entry — never a duplicate — and the change is persisted. |
| `claim_work` | `requester` (required), `model_class`, `lease_seconds` (default 3600) | Claims the next best claimable entry and leases it to the requester, so concurrent agents don't collide. Ground-truth-labelled work is offered first; an expired lease returns the entry to the pool. Returns the leased entry or that there is no eligible work. |
| `release_work` | `accession`, `requester` | Releases a claimed entry back to the queue. Only the lease holder may release it. |

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
oracle the repository uses, so it can never disagree with the repository. Read-only and
effectful tools are separated: the effectful `submit_paper` and `claim_work` appear only when the
server runs with a mutable catalog, and a read-only server hides and refuses them.

The human-facing `reprolith` CLI is the same surface for people at a terminal: it loads the same
persisted state through the same `load_repository` and reads it through the same `ReprolithQuery`,
so the terminal view and the agent view are guaranteed identical. Any read command takes `--json`
to emit the exact object the corresponding MCP tool returns.
