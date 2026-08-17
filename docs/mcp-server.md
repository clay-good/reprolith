# Reprolith MCP server

Reprolith exposes its catalog, certificates, and reproducibility engine to AI agents over the
Model Context Protocol, so an agent can call it mid-workflow as a deterministic reproducibility
oracle. Most of the surface is read-only plus an inline linter — those tools return data and change
no state — and a smaller set of effectful tools closes an agent's work loop by claiming, recording,
and requeueing entries (see "Effectful tools" below). Every verdict travels with its scope flag and
qualifications, whichever surface it leaves by.

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
| `self_validation` | — | The blind track record per class: matched / abstained / other, aggregate only |
| `dossier` | `accession` | The ingested dossier — extracted model structure |
| `bundle` | `accession` | The reconstruction bundle — model, recipe, assumptions |
| `lint` | `sbml`, `species`, `reference`, `duration`, `steps` | A deterministic per-claim verdict for an ODE model curve (needs the engine extra) |
| `lint_objective` | `sbml`, `reported`, `medium` (optional) | A deterministic verdict for an SBML-fbc model's optimal objective under an optional medium (needs the engine and fba extras) |
| `lint_steady_state` | `rules`, `reported` | A deterministic verdict on whether a reported steady state is a fixed point of a supplied Boolean network (pure, no extra) |
| `lint_estimation` | `reported`, `recovered` | A deterministic verdict on a re-derived parameter estimate vs a reported one, at the estimation tolerance (pure, no extra) |
| `lint_distribution` | `reported`, `predicted` | A deterministic verdict on a simulated percentile envelope vs a reported one, worst-band governed (pure, no extra) |
| `lint_stochastic` | `sbml`, `species`, `reported_mean`, `duration`, `trajectories`, `seed` | A deterministic verdict on an SBML reaction network's mean species count via a pinned Gillespie SSA (needs the engine extra) |
| `lint_diffusion` | `initial`, `reference`, `diffusivity`, `dx`, `dt`, `steps`, `decay` (optional) | A deterministic verdict on a 1-D diffusion profile vs a reported one, by curve distance (pure, no extra) |

## Effectful tools

Kept separate from the read-only tools, and offered only when the server runs with a mutable
catalog (as `reprolith-mcp` does):

| Tool | Arguments | Effect |
|---|---|---|
| `submit_paper` | `title` (required), `doi`/`pubmed_id`/`accession`/`model_class` | Adds a candidate paper as a queued entry (unassigned class unless `model_class` is given) and reports what changed. Submitting the same paper again resolves to the existing entry — never a duplicate — and the change is persisted. A submission never edits an existing entry's identity; `identifiers_not_recorded` says which of yours were not added. |
| `claim_work` | `requester` (required), `model_class`, `lease_seconds` (default 3600) | Claims the next best claimable entry and leases it to the requester, so agents sharing one server don't collide. Readier (lower-difficulty) work is offered first; ground truth is deliberately not a ranking key, and an expired lease returns the entry to the pool. Returns the leased entry or that there is no eligible work. |
| `release_work` | `accession`, `requester` | Releases a claimed entry back to the queue. Only the lease holder may release it. |
| `record_result` | `accession`, `requester`, `digest` (all required), `at` | Records that the entry's reproduction is done. Walks it to `certified`, `failed`, or `blocked` — the state comes from the named certificate's verdict, never from the caller — records each move with the recording agent and the certificate digest, and drops the lease. The entry stops being offered as work. A certificate that does not name an identifier the entry carries, or that has been superseded, is refused. |
| `requeue_entry` | `accession`, `requester`, `reason` (all required), `at` | Returns a `blocked` entry to the queue because the input it was waiting on is now available. The reason is recorded in the entry's history. Only a `blocked` entry: re-opening a `failed` one is a re-verification decision, and a quarantine is released after review. |

### The work loop

An agent's cycle closes with `record_result`:

1. `claim_work` — leased the next entry.
2. Do the reproduction and publish a certificate (the digest is its identity).
3. `record_result` with that digest — the entry advances to `certified`, `failed`, or
   `blocked`, and leaves the claimable pool for good.

Skipping step 3 is what makes an agent loop spin: the entry stays `queued`, and the same unit is
handed out again the moment the lease expires. Two things are not the agent's to assert. The
outcome state is read from the certificate's own verdict, so a certificate that says
`not-reproduced` records a `failed` entry however the caller describes it; and the certificate
must positively name an identifier the entry carries — a DOI, a PubMed ID, or the paper's title —
so one paper's result can never be filed under another's accession. A blocked entry gets its
missing input recorded from the certificate's gap report, and `requeue_entry` is how it comes
back once that input arrives.

### What the lease is and is not

The lease is a coordination hint inside one server process, not a lock and not an authorization
check. `requester` is a name the caller supplies, so any agent can release another's lease by
naming it, and an expired lease is re-offered without telling the original holder. Two agents
running their own `reprolith-mcp` processes over the same `catalog.json` will each load it at
startup and rewrite it whole on every mutation, so both can be handed the same entry and the later
write wins. Run one server per catalog, or coordinate outside Reprolith.

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
