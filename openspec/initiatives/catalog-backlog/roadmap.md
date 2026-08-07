# Catalog Backlog — Top 10

Ranked by the rubric in [`README.md`](README.md): **(value × readiness) ÷ cost**, with
ground-truth-first and momentum as hard overrides. Everything here assumes the ODE PK/PD MVP
(`bootstrap-ode-pkpd-mvp`) has closed its self-validation loop.

Each item is a stub, not a spec. When picked up, it becomes a capability spec (or a delta) plus
a change under `openspec/changes/`.

---

## Tier 1 — Foundation and fast, ground-truth-backed breadth

### 1. Seed from curated model repositories (ground-truth-first)

- **Type:** source integration
- **Why (value):** Curated repositories ship models *with* reproduced figures and curation
  status — built-in ground truth. This is the source that keeps blind self-validation possible
  for every class and fills the first test sets. Nothing outranks it.
- **Oracle / approach:** No new oracle. Import curated entries, attach their curation status as
  ground-truth labels (withheld from the verdict path), route by model class.
- **Seed source:** Public curated model repositories (e.g. BioModels) and their reproduced-figure
  metadata.
- **Difficulty:** Low–medium (mostly ingestion plumbing and label mapping).
- **Depends on:** MVP catalog + `catalog-seeding`.
- **Done when:** Each supported class has a labelled, blind test set sourced here, and agreement
  reports run against it.

### 2. Generic kinetic (systems-biology ODE) model class

- **Type:** model class
- **Why (value):** The largest single body of curated dynamic models. It reuses the PK/PD curve
  oracle almost unchanged, so it buys enormous catalog breadth at low cost — the fastest way to
  make Reprolith visibly general and busy.
- **Oracle / approach:** Same time-course reproduction as PK/PD (curves and derived scalars),
  specialized to biochemical reaction-network structure and species/observable claims.
- **Seed source:** Curated kinetic models (item 1) first, then the un-curated tail (item 6).
- **Difficulty:** Low–medium (near-neighbor of the MVP oracle).
- **Depends on:** MVP oracle; item 1.
- **Done when:** The class passes its blind self-validation gate and certificates render for a
  seeded kinetic set.

### 3. Constraint-based / flux-balance (FBA) model class

- **Type:** model class *(spec drafted: `constraint-based-class`)*
- **Why (value):** The generalization proof. Its oracle shares nothing with curve-matching —
  optimization outcomes checked by linear programming and a standardized fingerprint. Passing it
  demonstrates the engine's abstractions are general, and it plugs into an existing community
  reproducibility standard.
- **Oracle / approach:** Objective value, flux distribution, flux-variability, and gene/reaction
  essentiality, compared via a standardized fingerprint; alternate-optima handled honestly.
- **Seed source:** Fingerprint-curated constraint-based models in public repositories.
- **Difficulty:** Medium (new optimization oracle, but well-standardized).
- **Depends on:** MVP shared contracts; item 1.
- **Done when:** Blind agreement with fingerprint-curated ground truth is reported and
  disagreements resolved.

---

## Tier 2 — Reproduction yield and robustness

### 4. SED-ML / OMEX adopt-and-verify fast-path

- **Type:** capability
- **Why (value):** When a paper ships an executable simulation recipe and archive, reproduction
  is mostly "run it and check" — the highest certificate yield per unit effort, across every
  class at once. Also the cleanest momentum builder.
- **Oracle / approach:** Detect a shipped recipe/archive, adopt-and-verify per the reconstruction
  contract, run under the pinned engine, compare to the paper's claims.
- **Seed source:** Repositories and supplements that already carry recipes/archives.
- **Difficulty:** Low–medium.
- **Depends on:** MVP reconstruction + oracle.
- **Done when:** A shipped-archive paper flows to a certificate with minimal reconstruction, and
  mismatches between archive and manuscript are surfaced.

### 5. Multi-engine matrix and cross-engine corroboration

- **Type:** capability
- **Why (value):** Lifts a deferred fence. Running a reconstruction on more than one registered
  engine separates a model's behavior from a single solver's quirks, turning "engine-sensitive"
  from a hidden risk into a reported verdict — a real credibility multiplier.
- **Oracle / approach:** Register multiple containerized engines; run compatible reconstructions
  on each; report verdict stability; flag flips as engine-sensitive.
- **Seed source:** N/A (applies to existing entries).
- **Difficulty:** Medium (engine integration and result normalization).
- **Depends on:** MVP oracle; the BioSimulators engine registry.
- **Done when:** Verdict stability is reported across ≥2 engines for supported classes.

### 6. Seed the un-curated literature (preprint / journal feeds)

- **Type:** source integration
- **Why (value):** The mission's core. Un-curated papers are where reproducibility is unknown and
  the "what was missing" reports are most valuable to the field. Lower reproduction rate, highest
  impact — this is where Reprolith moves the needle.
- **Oracle / approach:** No new oracle. Feed-based seeding with quality-gate screening; route by
  class; these entries carry no ground-truth labels, so they follow, not precede, self-validation.
- **Seed source:** Preprint servers and journal feeds carrying modeling papers.
- **Difficulty:** Medium (screening precision, licensing discipline).
- **Depends on:** `catalog-seeding` licensing/quality gates; ≥1 class past its gate.
- **Done when:** Un-curated papers flow into certificates and structured gap reports at a
  sustained cadence.

---

## Tier 3 — Lift the deferred method fences

### 7. Population / inter-individual variability reproduction

- **Type:** capability *(oracle landed: distributional band judge in `simulation-oracle`)*
- **Why (value):** Many PK/PD and QSP figures are distributions, percentiles, or virtual
  populations, not single trajectories. Reproducing them unlocks a large, high-value slice of the
  literature the MVP explicitly deferred.
- **Oracle / approach:** Extend the oracle to compare distributional claims (bands, percentiles,
  variability metrics) under a declared, honest tolerance for simulated populations.
- **Seed source:** PK/PD and QSP papers reporting population figures.
- **Difficulty:** Medium–high (distributional comparison, reproducible sampling).
- **Depends on:** MVP oracle; ideally item 5 for robustness.
- **Done when:** A population figure is reproduced with a declared distributional tolerance and a
  qualified verdict.

### 8. Estimation reproduction (re-fit from raw data)

- **Type:** capability *(estimation judge landed in `simulation-oracle`; re-fitting engine deferred)*
- **Why (value):** The level-2 oracle deferred from the MVP: when raw data ships, re-fit the
  model and check the *reported parameter estimates*, not just the shown curve. The strongest form
  of reproducibility, and the most convincing when it holds.
- **Oracle / approach:** When reference raw data exists, run the paper's stated estimation and
  compare recovered estimates within tolerance; report separately from simulation reproduction.
- **Seed source:** Papers shipping raw datasets alongside the model.
- **Difficulty:** High (estimation is sensitive to method and starting points; determinism is
  harder).
- **Depends on:** MVP; strong tolerance/provenance discipline.
- **Done when:** A data-shipping paper's estimates are re-derived and certified as a distinct
  estimation verdict.

---

## Tier 4 — Generalize further, then distribute

### 9. Logical / Boolean and rule-based network model class

- **Type:** model class *(oracle + SBML-qual ingestion landed: `logical-class` spec, exact sync/async attractor judge, `ingest_qual_sbml`; blind self-validation set still to come)*
- **Why (value):** A third distinct oracle — discrete-state attractors and qualitative dynamics
  rather than continuous trajectories or optimization. Common in signaling models, and further
  hardens the claim that the engine is oracle-agnostic.
- **Oracle / approach:** Reproduce steady states / attractors and qualitative behavior claims
  with the appropriate discrete analysis, compared under class-specific tolerances.
- **Seed source:** Curated logical/rule-based models (item 1), then un-curated (item 6).
- **Difficulty:** Medium (new discrete oracle, reuses shared contracts).
- **Depends on:** MVP shared contracts; item 1.
- **Done when:** Blind self-validation passes for a seeded logical-model set.

### 10. Author / journal reproducibility gap report and pre-submission check

- **Type:** capability / distribution *(landed: `presubmission-check` spec + MCP `presubmission` tool)*
- **Why (value):** The adoption flywheel. Package the "what was missing" report as something an
  author or journal runs *before* publication — turning Reprolith from an after-the-fact auditor
  into a tool people want, and converting the un-curated tail into fewer irreproducible papers at
  the source.
- **Oracle / approach:** No new oracle. Re-present the certificate's gap report and per-claim
  verdicts as an author-facing pre-submission artifact, runnable over the MCP surface.
- **Seed source:** N/A (consumes existing engine output).
- **Difficulty:** Low–medium (presentation and workflow, not new science).
- **Depends on:** Certificate + MCP surface; a class past its self-validation gate.
- **Done when:** An author can submit a model pre-publication and receive a precise, actionable
  gap report and per-claim verdicts.

---

## Not in the top 10 (parked, with reasons)

- **Spatial / PDE and stochastic simulation classes** — different simulation machinery and a
  weaker free oracle; revisit after the deterministic classes are broad.
- **Whole-cell and very large QSP networks** — in-kind but often intractable under a single
  pinned engine; wait for item 5 and better resource handling.
- **A hosted web dashboard** — valuable for outreach, but the certificate and MCP surface come
  first; presentation follows substance.
