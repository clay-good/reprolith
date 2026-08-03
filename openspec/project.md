# Reprolith — Project Context

## What this is

Reprolith is an **auto-reproduction-and-certification engine for the computational
biomedical modeling literature**. Given a modeling paper and its artifacts, Reprolith
reconstructs the model into open standard formats, re-runs it, compares the result
against the paper's *own* published figures and tables, and issues a machine-readable
**reproduction certificate**: reproduced / partial / failed — per claim, with the
discrepancy quantified and the failure root-caused.

## The one idea it is built on

A published model's own figure is a **computational oracle**: it is exact and checkable
for free, within a declared numerical tolerance. Unlike wet biology, reproducing a
computational result requires no lab — only the model, the recipe, and a simulator.
Reprolith is *certify-don't-assert* applied to science papers.

## Why it matters

Over half of published computational models of physiological processes are irreproducible
from the information in their own manuscript. Curated repositories cannot keep up: only
about half of BioModels entries ship a runnable simulation recipe. Reprolith is the engine
that turns that backlog into certified, runnable, standard-format artifacts — and flags,
precisely, what each irreproducible paper left out.

## Non-negotiable scoping (state everywhere)

- **Reproducible ≠ correct ≠ clinically valid.** A certificate attests only that the
  described model regenerates the shown result. It makes no claim about biological truth,
  model appropriateness, or fitness for any clinical or therapeutic decision.
- Every certificate carries a machine-readable `scope` flag asserting the above.

## How we build

- **Narrow and deep first:** ODE PK/PD compartmental models end-to-end, then generalize.
- **Massive catalog:** a perpetual backlog seeded from public repositories and the
  literature so there is always well-scoped work to claim.
- **Two surfaces, one core:** a GitHub repository for humans and agents; an MCP server
  exposing the same engine as deterministic tools for agentic workflows.
- **Discipline loop:** test → note → iterate. Every model class is validated against
  known-reproducibility ground truth before its verdicts are trusted.
- **One goal, self-driving:** a human points a one-line goal at a coding agent; the
  autonomous build loop selects the next slice, proves it against deterministic gates,
  publishes it, and continues — recording a best estimate and escalating load-bearing
  low-confidence values to the verification queue rather than blocking or guessing. The
  queue is the collaboration surface where experts confirm, correct, and keep the dataset
  fresh.

## Ecosystem we stand on (do not reinvent)

- **Model formats:** SBML, CellML, SED-ML, OMEX (COMBINE archive), KiSAO, SBO.
- **Simulation:** the BioSimulators registry of containerized engines.
- **Ground truth for self-validation:** BioModels curation status and reproduced figures.

## Conventions

- Specs are behavior-first: requirements describe observable behavior and contracts;
  mechanism lives in `design.md` / `tasks.md`.
- Determinism is a product property: given the same inputs and pinned engine versions, a
  certificate is byte-reproducible. Any nondeterminism is declared, bounded, and recorded.
- Provenance is first-class: every extracted claim, parameter, and assumption cites its
  source location, and every gap Reprolith had to fill is recorded as an explicit field.
