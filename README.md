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

> Status: pre-alpha. Six model classes (PK/PD, constraint-based, kinetic, logical, stochastic,
> spatial) are built and self-validated in the open. See [`openspec/`](openspec/) for the full spec.

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
solver). It reports the full FROG fingerprint the constraint-based-class spec names — objective
value, flux variability, and both reaction- and gene-deletion outcomes — each preserving the
"abstain when unsure" rule under alternate optima, plus the LP dual (`shadow_prices`: metabolite
shadow prices and reaction reduced costs, validated against the primal by strong duality) and
parsimonious FBA (`parsimonious_fluxes`: the minimal-total-flux tie-break among alternate optima);
see [docs/fba-oracle.md](docs/fba-oracle.md). The same shared pathway carries it end to end: a
constraint-based dossier adopts the paper's SBML-fbc model and records its load-bearing medium,
then certifies to a scope-flagged verdict, reproduced or honestly not. It self-validates against a
real published model: [datasets/constraint_based/](datasets/constraint_based/) ships the *E. coli*
core model, and the `ingest_fbc_sbml` → `solve_objective` pathway reproduces its independently-known
maximal growth rate (0.873922) to every published digit — with a
[worked example](datasets/constraint_based/worked_example/) walking the whole dossier → certificate.

```bash
pip install -e ".[dev,engine,fba]"   # fba brings the LP solver; engine (libsbml) reads the .xml model
```

Generic **systems-biology kinetic models** (signaling, metabolic, gene-regulatory networks) are the
third class. They reuse the PK/PD curve oracle unchanged — the reproducible result is a species
time-course — so adding them is mostly demonstrating the contract generalizes. The class is
self-validated non-circularly against an independent simulator (libRoadRunner): curated BioModels
networks spanning six dynamic regimes (signaling, gene-regulatory, metabolic, cell-cycle, circadian,
calcium) reproduce, and the [milestone blind run](datasets/kinetic/milestone/) scores 6/6 through the
same catalog and agreement machinery as the other classes. See
[docs/kinetic-class.md](docs/kinetic-class.md).

**Logical / Boolean network models** are the fourth class, and the sharpest generalization proof: a
discrete oracle with no continuous trajectory and no optimization, where the reproducible result is
the network's steady states and attractors. It reuses the shared contracts and adds only exact,
dependency-free attractor analysis (synchronous and asynchronous), reads standard SBML-qual, and is
self-validated non-circularly against CANA (Correia et al. 2018), an independent Boolean-network
library: Reprolith's own attractor oracle reproduces CANA's results on four real
published models — the Arabidopsis flower, Drosophila segment-polarity, and budding-yeast cell-cycle
networks, and a schemata example — with the [milestone blind run](datasets/logical/milestone/)
scoring 4/4 through the same catalog and agreement machinery. See
[docs/logical-class.md](docs/logical-class.md).

**Stochastic (SSA) models** are the fifth class: discrete-molecule reaction networks where a single
run is a random sample, so the reproducible result is a distribution. An exact, pure-Python
Gillespie simulator (deterministic under a pinned seed) feeds the same distributional oracle the
population figures use, and the class is self-validated non-circularly against closed-form results —
the immigration-death process's Poisson stationary mean and variance and a reversible reaction's
binomial equilibrium — with a 3/3 [milestone blind run](datasets/stochastic/milestone/).

**Spatial reaction-diffusion (PDE) models** are the sixth class: the reproducible result is a
concentration profile over space, so a pure-Python finite-difference solver feeds the same curve
oracle, self-validated non-circularly against the exact analytical diffusion solution (a Gaussian
whose variance grows by 2·D·t) with a 3/3 [milestone blind run](datasets/spatial/milestone/).

All six classes are measured blind against independently-established ground truth on the same
machinery — [docs/self-validation.md](docs/self-validation.md) is the one-look evidence summary.

Reprolith gets better when people who know the science validate its judgment. When it isn't sure
about a load-bearing value, it opens a **verification issue** with its best estimate — confirming
or correcting one is the most valuable thing you can do here. See
[CONTRIBUTING.md](CONTRIBUTING.md).
