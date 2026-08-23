# Design — bootstrap-ode-pkpd-mvp

This document holds mechanism and decisions. The behavioral contracts live in the specs; this
is how we intend to satisfy them for the MVP, and what we deliberately leave open.

## Design goals, in priority order

1. **Close the loop before widening it.** One class, end to end, measured against ground
   truth, beats five half-built pathways.
2. **The oracle must be trustworthy before the reconstructor is clever.** A confidently wrong
   verdict is worse than an honest `blocked`. When unsure, the system abstains.
3. **Everything is an inspectable file.** A human or agent can open any entry, dossier,
   bundle, and certificate and see exactly what happened and why.
4. **Determinism is engineered, not hoped for.** Engines and versions are pinned; tolerances
   absorb declared nondeterminism; the same inputs yield the same certificate.

## Stand on the standards ecosystem

We do not build a simulator or a new model format. We target the existing standards and
containerized engines so our outputs are portable and independently checkable:

- Model: SBML (primary for PK/PD kinetics), CellML tolerated on intake.
- Simulation recipe: SED-ML **on intake only** — Reprolith reads a shipped recipe
  (`parse_sedml_recipes`) and does not emit one. See below.
- Engines: the BioSimulators containerized registry, pinned by version, so anyone can re-run
  a bundle and get our numbers.
- Self-validation labels: public curation status and reproduced figures (e.g. BioModels).

Concrete library choices (interchangeable, kept out of the specs) are an implementation
detail to settle at build time; the contract is only that outputs validate against these
standards and run under a pinned registered engine.

**What a bundle actually is today, stated plainly.** This section used to say "bundle: OMEX /
COMBINE archive", and nothing emits one: there is no SED-ML writer and no archive writer in the
package. A published bundle is a Reprolith JSON record that *references* a model file by path and
carries a recipe in Reprolith's own shape. The model it points at is standard SBML and the engine
pin is real, so the run is reproducible — but the container is not a COMBINE archive and the recipe
is not SED-ML. Emitting both belongs in the not-yet list below, not in the delivered contract.

## Key decisions

### D1 — Simulation reproduction is the primary target; estimation reproduction is secondary

We check "does the described model, run as described, reproduce the shown output," not "can we
re-fit the parameters from raw data." Simulation reproduction is what curation does, needs no
raw dataset, and is deterministic. Estimation reproduction is recorded as a separate, deferred
capability, attempted only when raw data is present.

### D2 — The oracle abstains rather than guesses

`not-evaluable` is a first-class verdict. If a claim has no numeric data and no digitizable
figure, or the reconstruction rests on an assumption too load-bearing to defend, we do not
manufacture a pass or a fail. Abstention keeps the agreement metric meaningful.

### D3 — Assumptions gate the verdict vocabulary

A claim reproduced only because of a load-bearing assumption can never be reported as
unqualified `reproduced`. This is enforced at the certificate layer so no pathway can bypass
it. It is the mechanism that keeps Reprolith from taking credit for its own guesses.

### D4 — Blind self-validation is the acceptance gate

Ground-truth labels are stored on the catalog entry but are structurally withheld from
ingestion, reconstruction, and the oracle. Agreement is computed only after a verdict exists.
The milestone's definition of done is the agreement report plus a resolution for every
disagreement.

### D5 — Tolerances are documented defaults with principled overrides

Each PK/PD claim type gets a documented default tolerance. Overrides require a stated
rationale (paper-stated precision or reviewer judgment). No unexplained thresholds.

### D6 — Fence on method, not topology

The MVP takes the whole ODE PK/PD family — multi-compartment, nonlinear/saturable kinetics,
transit/lag absorption, effect-compartment and indirect-response PD, target-mediated
disposition, and PBPK — because a paper's model topology is not what makes reproduction hard
or easy; the *method* of reproduction is. We fence on method (single-subject, deterministic,
simulation-level, one pinned engine) and let structural complexity through. A large or stiff
in-kind model that will not converge degrades to `blocked`, never `failed`. This keeps
Reprolith ambitious from day one without weakening the honesty of a verdict: what we defer,
we defer for a principled reason a reviewer can see.

## Comparison methods (MVP)

- **Curves:** simulate under the claim's protocol; compare the predicted profile to reference
  points via a normalized distance over the stated span; verdict by threshold.
- **Scalar PK/PD metrics:** derive the metric from the simulation using its standard
  definition; compare to the reported value by relative error.
- **Figure-only references:** compare against digitized or paper-reported summary values; the
  tolerance is widened to reflect digitization uncertainty, and this is recorded.

## The discipline loop (how we actually work)

```
pick a labelled entry
  -> ingest (dossier + gaps)
  -> reconstruct (bundle + assumptions)
  -> run oracle blind (per-claim verdicts)
  -> issue certificate
  -> compare to ground-truth label
  -> AGREE:   note what made it work; move on
     DISAGREE: write the defect note; fix ingestion/reconstruction/oracle/tolerance; re-run
repeat until the labelled set is exhausted and every disagreement is fixed or explained
```

Notes are kept per entry so the failure-mode catalogue and the tolerance defaults are
evidence-driven, not guessed up front.

## What we are explicitly NOT building yet

- Population / inter-individual variability simulation.
- Estimation reproduction (re-fitting from raw data).
- Multi-engine corroboration (single pinned engine for the MVP; cross-engine is deferred).
- Lease-based work handoff over MCP (repository is the work surface for now; MCP is read-only
  plus the inline linter).
- Any model class other than `ode-pkpd`; unassigned candidates accumulate as backlog.
- **Emitting SED-ML or an OMEX/COMBINE archive.** SED-ML is read on intake and never written; a
  bundle is a Reprolith JSON record referencing an SBML file. The "Stand on the standards
  ecosystem" section above used to list archive emission as part of the delivered contract.

Several of the entries above have since been built — population and estimation reproduction,
cross-engine corroboration, five further model classes, and lease-based handoff over MCP all exist
now. They are left listed rather than silently deleted, because this document is the record of what
the change proposed, and the note under each is the honest way to show the difference.

## Risks and how the design answers them

- **Reconstruction is too hard / too many blocks.** Acceptable: a well-characterized `blocked`
  with a precise missing-inputs list is a valid, useful outcome and itself evidence for the
  field. The oracle abstaining is a feature, not a failure.
- **Prior art overlap (Talk2Biomodels, LLM→SBML).** We differentiate by verdict + certificate
  on the un-curated/irreproducible tail, not chat over already-curated models.
- **Tolerance disputes.** Every tolerance is documented and overridable with rationale, so a
  disagreement is a conversation about a recorded number, not a black box.
- **Ground-truth leakage into verdicts.** Labels are withheld by construction (D4); any
  pathway that reads them is a defect.
