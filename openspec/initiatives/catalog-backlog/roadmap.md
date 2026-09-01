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

- **Type:** capability *(DONE: intake — recipes, claims, and archive reading in `paper-ingestion`;
  emitting an archive in `certificate-publication` — model, SED-ML, and manifest, written
  deterministically; and now archive-vs-*manuscript* mismatches — `manuscript_mismatches` compares
  the shipped experiment against the paper's extracted claims and reports an output the model does
  not declare, one the experiment never records, and a value the run never holds. On the shipped
  metformin archive that is one true line and no noise: the document scans the dose over
  389.2/778.4/1167.6 mg and the paper's 1000 mg claim is 779.9 mg free base. It is reachable from
  the CLI now — `archive-check --claims` — and the file that check needs is generated rather than
  hand-written: `claims-template` turns the author's model and document into one stub per plotted
  curve, with the two fields only the author has left blank and refused if left that way. What
  remains is *extraction*, and half of it is now built: `claims-propose` reads candidate claims out
  of a paper's own **tables** (`claims-check` then confirms each value is printed where it says it
  is), which took the corpus from one certified-against-a-paper entry to four — every model that
  paper deposited, with the engine's pass, failure and abstention paths all exercised on real
  published numbers for the first time. Reading results out
  of manuscript **prose** is still not built. Measured on this set: reading tables reaches three
  papers in ten of the open-access subset, and the rest state their results in figures —
  `datasets/manuscripts/table_survey.json`.)*
- **Why (value):** When a paper ships an executable simulation recipe and archive, reproduction
  is mostly "run it and check" — the highest certificate yield per unit effort, across every
  class at once. Also the cleanest momentum builder.
- **Oracle / approach:** Detect a shipped recipe/archive, adopt-and-verify per the reconstruction
  contract, run under the pinned engine, compare to the paper's claims.
- **Seed source:** Repositories and supplements that already carry recipes/archives.
- **Difficulty:** Low–medium.
- **Depends on:** MVP reconstruction + oracle.
- **Done when:** ~~A shipped-archive paper flows to a certificate with minimal reconstruction, and
  mismatches between archive and manuscript are surfaced.~~ Both halves done: the end-to-end walk
  is `tests/test_archive_end_to_end.py`, the manuscript comparison
  `tests/test_manuscript_mismatch.py`.

### 5. Multi-engine matrix and cross-engine corroboration

- **Type:** capability *(landed for both ODE classes: kinetic per model, PK/PD per claim at the
  dose it was certified at, COPASI vs libRoadRunner, reported beside the certificates rather than
  gating them. The other four classes have no second registered engine, so nothing is reported for
  them — an absence, not a pass.)*
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
- **Measured (2026-08-29):** on the seeded set, 21 of 31 entries ship a curated SBML model, 9 ship
  SBML that is not curated, and 1 ships an R script. A paper stating reproducible results is only
  half of what a certificate needs, and the entries clearing both conditions are exactly the four
  variants of the one paper already certified (`datasets/manuscripts/table_survey.json`) — **all
  four of which are now certified**, carrying 80 claims (72 reproduce, 7 fail with stated causes,
  1 abstains). No further entry in this test set is reachable from what is built: the remaining
  papers either publish their results in figures or ship no runnable model. Lifting it needs
  figure digitization or entries whose models run. **Prose extraction is measured out**: a prose
  candidate reader (`propose_claims_from_prose`) reaches two of the ten open-access papers and
  both already state their results in a table — the seven figure-only papers state none in their
  text either. It broadens what can be read from a paper already reachable and moves the
  corpus's reach by nothing. **And the figure captions were inside that sweep all along**
  (2026-08-30): 87 of 87 caption paragraphs across the ten papers, now counted rather than
  assumed, and none of the ten candidates they carry is attributed to a model while naming a
  metric — so "the results are in the figures" is a statement about the pictures, not about
  unread text beside them. **The one non-curated entry whose paper prints a table was opened**
  (MODEL1711210003, an estradiol PBPK/genome-scale model): it deposits 118 reactions and a rate law
  for none of them — 114 with an empty `<kineticLaw><math/>` and 4 with no `kineticLaw` at all — so
  it is reaction topology, not a runnable model, and no extraction capability would reach it. That
  is now a check (`reactions_without_rate_laws`, leading `archive-check`'s fix list) rather than
  only a note, because no engine says what is wrong: libRoadRunner runs an absent law with its flux
  silently at zero, and COPASI imports the file and abandons the run partway with every sample it
  did return finite. **And "entries whose models run" is measured out too**
  (`datasets/non_curated_survey.json`): probed over a ladder of durations, **5 of the 9 non-curated
  SBML models run**, and joining the two surveys they are disjoint — the one entry whose paper
  prints a results table is the estradiol model that does not run, and of the five that do, four
  name no reachable paper and the fifth's prints no table. Nothing is waiting on a better engine.
  Figure digitization is the only lift left. **Its intake half landed 2026-08-30**
  (`reprolith.digitization`, `reprolith figure-check`, [`docs/figure-values.md`](../../../docs/figure-values.md)):
  a curator's plot-digitizer output becomes a claim's reference data on the run's own sample grid,
  interpolated in the axis's own scale and never extrapolated, with a mis-calibrated reading — a
  point outside its own axes — refused by name, and the reference kind pinned to `digitized-figure`
  so the wider band is not escapable. The pairing a curator cannot verify by eye — the claim ids the
  template filled in — is checked against the document those ids came from when `figure-check` is
  given it (2026-08-31), which is where a typo, a renamed output, or a file filled in against an
  older document stops — as is a reading that does not cover the window the document runs, which
  nothing extrapolates over and which the join therefore refuses long after the curator has gone.
  Without a document the report says the ids were not checked rather than reading clean over a
  check nobody made. What a reading *costs* is now measured from the reading itself rather than
  proxied by its widest gap (2026-08-31): each interior point is rejoined from its neighbours and
  the residual is the curve's own curvature, reported as a share of the pass budget and as the x
  where it bends most. The gap was shape-blind in both directions — it warned about a straight line
  read at three points and said nothing about a PK curve read at ten, whose 11% gaps hide straight
  lines spending one and a half times the whole budget.
  Reprolith reads no pixels and this does not pretend to:
  the reading is a human act. What it needs next is a curator's digitization of a figure from a paper
  already in this corpus; none exists, so it is validated against series generated from known
  functions, the same fence items 7 and 8 carry.

---

## Tier 3 — Lift the deferred method fences

### 7. Population / inter-individual variability reproduction

- **Type:** capability *(landed: the distributional band judge in `simulation-oracle`, and now the
  half that was deferred — `simulate_population` draws a log-normal between-subject variability
  model under a stated seed and runs the ensemble, validated against the closed-form percentiles of
  a one-compartment model whose volume varies. The two halves are now joined end to end
  (`tests/test_population_end_to_end.py`, 2026-09-01) — model, ensemble, envelope, certificate,
  nothing hand-written between them — and the grid mismatch a paper's printed times can produce
  against a run's own samples is now refused where the envelopes are aligned, naming the percentile
  and both counts, rather than as a bare length assertion two frames down. What is still missing is a *paper's*
  population figure to point it at; the demonstration is against mathematics, not a published
  envelope.)*
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

- **Type:** capability *(landed: the estimation judge in `simulation-oracle`, and now the re-fitting
  engine — `refit_parameters` minimizes least squares with an owned, deterministic Nelder-Mead on
  the log scale, validated by recovering a rate constant a closed-form regression gives exactly.
  What is still missing is a *paper's* shipped dataset to point it at; the demonstration is against
  mathematics, not a published estimate.)*
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

- **Type:** model class *(DONE: `logical-class` spec, exact sync/async attractor judge, `ingest_qual_sbml`, and 4/4 blind cross-validation vs CANA on real published models)*
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

- **Stochastic (SSA) simulation class** — *DONE*: landed as `stochastic-class`, a pure-Python
  Gillespie SSA reusing the distributional oracle, self-validated against closed-form
  Poisson/binomial results. Now complete across the full class pattern: `stochastic_dossier` /
  `validate_stochastic` (unstated sampling protocol as a load-bearing gap), `certify_stochastic`,
  `ingest_stochastic_sbml`, the `lint_stochastic` inline linter, and a walkable 3/3 milestone.
- **Spatial / PDE simulation class** — *DONE*: landed as `spatial-class`, a pure-Python 1-D/2-D
  finite-difference reaction-diffusion solver reusing the curve oracle, self-validated against
  closed-form results (Gaussian diffusion, Fisher-KPP and Nagumo front speeds, morphogen decay
  length, the Turing dispersion relation and wavelength selection). Has `spatial_dossier` /
  `validate_spatial` (unstated domain/boundary as a load-bearing gap), `certify_spatial`, the
  `lint_diffusion` inline linter, and a walkable 3/3 milestone. **Correction (2026-08-28):** this
  entry said ingestion was blocked because "there is no standard single-file interchange format for
  a reaction-diffusion model to ingest". There is one — the SBML Level 3 `spatial` package — and
  the pinned libSBML reads it, which was never checked before the claim was written down.
  `ingest_spatial_sbml` now reads the intersection that this solver runs (Cartesian geometry in one
  or two components with a stated extent, one isotropic diffusion coefficient per spatial species,
  a uniform initial concentration) and refuses the rest by name, zero-flux Neumann boundaries
  included, since running a Dirichlet model under Neumann walls is a different model with no sign
  that it happened. What *is* blocked is narrower and still true: no published spatial model is in
  this corpus and none can be fetched here, so the reader is validated against files libSBML's own
  spatial API wrote, not against one from the field.
- **Whole-cell and very large QSP networks** — in-kind but often intractable under a single
  pinned engine; wait for item 5 and better resource handling.
- **A hosted web dashboard** — valuable for outreach, but the certificate and MCP surface come
  first; presentation follows substance.
