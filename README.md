# Reprolith

**Point it at a modeling paper. Get back proof of whether the model reproduces its own results.**

More than half of published biomedical models can't be reproduced from the information in
their own paper. Reprolith rebuilds the model from the paper, re-runs it, and checks the
output against the paper's own figures and tables — then hands you a **certificate**:
reproduced, partially, or not — for each result, with the reason.

---

## Why this works when biology usually doesn't

You normally can't check a biology claim without a lab. But a paper's own figure is different:
it's a **computational result**, and re-running the model either matches it or it doesn't —
checkable, for free, to a stated tolerance. Reprolith lives entirely in that gap. No lab, no
guessing — just: *does the described model produce the shown result?*

## What you get

- **A per-result verdict, not a vibe.** Every figure and reported number is checked on its own.
- **Honest by construction.** If a result only reproduced because Reprolith had to assume a
  missing value, the certificate says so. It never takes credit for its own guesses.
- **A "what was missing" list.** When a paper can't be reproduced, you get the exact
  parameter, unit, or condition it left out — the thing the field actually needs to fix.
- **Standard, runnable artifacts.** The rebuilt model ships in open formats anyone can re-run.

## What it is *not*

Reproducible is not the same as correct, and neither is the same as safe to use on a patient.
A certificate attests to one thing only: that the model regenerates its own published results.
It makes **no** claim about biological truth or clinical use. Every certificate says this in
plain text.

## For agents, too

Reprolith runs as an **MCP server**, so an AI agent can call it mid-workflow as a deterministic
reproducibility check — submit a model, get a verdict it can trust and cite. Same engine,
same answers as the human-facing repository.

The server is dependency-free (JSON-RPC over stdio, no third-party SDK) and exposes read-only
tools — browse the catalog, get a paper's status, fetch a certificate, read its gaps, inspect a
dossier or bundle — each delegating to the same query surface the repository uses, so a verdict
always travels with its scope flag and qualifications. Run it with `reprolith-mcp` (after
`pip install -e .`); see [docs/mcp-server.md](docs/mcp-server.md) to register it in a client and
for the tool reference.

## Where it starts

Narrow and deep first: **ODE pharmacokinetic/pharmacodynamic models** — dose-in,
concentration-and-effect-out — end to end, validated against models whose reproducibility is
already independently known. Then it widens, one model class at a time, over a backlog that
never runs dry.

---

*Reprolith · reproduce + monolith · the bedrock layer under a literature that should be
runnable.*

> Status: pre-alpha. Building the first model class in the open. See
> [`openspec/`](openspec/) for the full specification.

## Build and contribute

The core engine is dependency-free (standard library only): the catalog, ingestion dossier,
reconstruction, oracle, certificate, agreement report, and read-only query surface all run
without third-party packages, so the required-checks gate stays fast and trivially
reproducible. The honesty invariants — determinism, the inescapable scope statement, and
assumption-qualification — are enforced in code and checked in CI.

```bash
pip install -e ".[dev]"
ruff check . && mypy && pytest -q
```

Actually running a model needs the optional **`engine`** extra, which pins COPASI (a
BioSimulators-registered engine) and the SBML tooling. It stays out of the core so the fast
gate does not depend on it; the engine-backed tests skip when it is absent.

```bash
pip install -e ".[dev,engine]"   # then pytest -q runs the simulation-backed tests too
```

With the extra installed the full loop runs end to end: a dossier compiles to SBML
([`reprolith.build_model_sbml`](python/reprolith/sbml.py)), runs under the pin
([`reprolith.simulate`](python/reprolith/engine.py)), is judged by the oracle, and produces a
scope-flagged certificate. The blind PK/PD self-validation set lives in
[`datasets/pkpd_test_set.json`](datasets/pkpd_test_set.json), labelled from BioModels'
curation status.

Constraint-based (FBA) models reproduce a different kind of claim — an optimization outcome, not
a time course — so they get their own oracle behind the optional **`fba`** extra (scipy's linear
solver). It reports the fingerprints the constraint-based-class spec names, each preserving the
"abstain when unsure" rule under alternate optima; see
[docs/fba-oracle.md](docs/fba-oracle.md). It self-validates against a real published model:
[datasets/constraint_based/](datasets/constraint_based/) ships the *E. coli* core model, and the
`ingest_fbc_sbml` → `solve_objective` pathway reproduces its independently-known maximal growth
rate (0.873922) to every published digit.

```bash
pip install -e ".[dev,fba]"   # then pytest -q runs the FBA oracle tests too
```

Reprolith gets better when people who know the science validate its judgment. When it isn't sure
about a load-bearing value, it opens a **verification issue** with its best estimate — confirming
or correcting one is the most valuable thing you can do here. See
[CONTRIBUTING.md](CONTRIBUTING.md).
