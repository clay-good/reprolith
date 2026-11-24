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
  of manuscript **prose** is built and on the terminal too (`claims-propose --prose`, merged into
  the same candidates file), though it moves this corpus's reach by nothing — see below. Measured
  on this set: reading tables reaches three
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

- **Type:** capability *(landed for all six classes: kinetic per model and PK/PD per
  claim at the dose it was certified at, COPASI vs libRoadRunner; constraint-based per model,
  Reprolith's own LP against COBRApy; and logical per network, CANA on the six enumerable
  attractor sets and sympy's SAT on the three 44-to-60-node models' fixed-point sets — the
  question those certificates rest on, and one no 2ⁿ enumeration can answer on either side. What
  is compared is chosen per class: the **objective value** for a linear program, because its
  optimum is unique where the flux vector attaining it is not, so comparing flux distributions
  would call two correct solvers engine-sensitive on any model with alternate optima; and the
  attractor or fixed-point set itself for the discrete class, published as an exact match rather
  than as a distance of zero, which on a page of curve distances reads as the best number on it.
  All reported beside the certificates rather than gating them. **And the stochastic class now has
  one too** (2026-09-05), which is a correction as much as an addition: this entry said its
  question — a Gillespie ensemble — was one no installed implementation but this one answers, and
  that was never checked. libRoadRunner ships a Gillespie integrator, it was already pinned here as
  the ODE classes' second engine, and it runs all three certified networks in four seconds. What it
  reports is different in kind from the other three classes and is published that way: two
  ensembles of the same model agree only up to Monte Carlo error, so the comparison is the
  difference of the two means over their **combined standard error**, against a criterion of three,
  and it would be a lie on the curve classes' scale (1.9 standard errors rounds to `2e+00`). Each
  agreement also carries the bias it could *not* have seen, because two small ensembles agree with
  almost anything: 6.5% of the mean on the Poisson-mean-10 network — wider than the 5% that class's
  own scalar verdict passes at — and 1.8% on the reversible isomerization. It is scoped to
  reactions at most first-order in each reactant and refuses the rest by name: Reprolith runs the
  stochastic mass action k·n(n−1)/2 where libRoadRunner's Gillespie takes the SBML rate law
  verbatim as k·n², a measured 24% gap on `2A → B` from four molecules that is a difference of
  convention and would have been published as engine sensitivity. Putting the same network in
  front of both needed a writer — `build_stochastic_sbml`, the exact inverse of the class's
  ingester, round-tripped in the tests — since until now the SSA's networks existed only as Python
  objects. **And the spatial class closed the matrix the same day**, by the same correction: scipy's
  LSODA — installed here since the constraint-based class needed a linear program — integrates the
  method-of-lines diffusion system this class steps explicitly, and the three certified profiles
  agree to 1e-03, the 1% of the curve budget the kinetic class spends. All six classes are
  corroborated. That number is scoped hard, because it invites being read as a distance from the
  truth: LSODA integrates the *semi-discrete* system essentially exactly, so what is measured is
  the explicit stepper's time-discretization cost, and against the continuum solution the explicit
  scheme does better — 2.0e-05 from the closed-form Gaussian, since central differencing and
  forward Euler have opposite-signed truncation errors that cancel at a diffusion number of 1/6.
  The pair does not separate the spatial discretization at all; both take second-order central
  differences with a mirrored boundary, and that is stated rather than glossed.)*
- **Why (value):** Lifts a deferred fence. Running a reconstruction on more than one registered
  engine separates a model's behavior from a single solver's quirks, turning "engine-sensitive"
  from a hidden risk into a reported verdict — a real credibility multiplier.
- **Oracle / approach:** Register multiple containerized engines; run compatible reconstructions
  on each; report verdict stability; flag flips as engine-sensitive.
- **Seed source:** N/A (applies to existing entries).
- **Difficulty:** Medium (engine integration and result normalization).
- **Depends on:** MVP oracle; the BioSimulators engine registry.
- **Done when:** ~~Verdict stability is reported across ≥2 engines for supported classes.~~ Done
  for every class that has a second implementation to register: 80 PK/PD claims, 6 kinetic models,
  8 constraint-based models, 9 logical networks, 3 stochastic networks and 3 spatial profiles, all
  engine-independent — every class this repository publishes
  (`tests/test_corroboration.py`, `tests/test_fba_corroboration.py`,
  `tests/test_logical_corroboration.py`, `tests/test_stochastic_corroboration.py`,
  `tests/test_spatial_corroboration.py`).

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
  corpus's reach by nothing — which is why it is not a seeding lift, and why it is still shipped
  (2026-09-09): the author whose peak is stated only in a sentence has no other reader, and leaving
  a measured, tested reader importable-but-unrunnable made a fact about *this corpus* read as a
  verdict on the reader. **And the figure captions were inside that sweep all along**
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
  Figure digitization is the only lift left. **And the ceiling is not this set's doing**
  (2026-09-02): the same question put to the curated models the seeded set does *not* contain —
  every one the repository's own search returns for pharmacokinetic and pharmacodynamic terms —
  finds six, five of them behind papers that are not open access, and the sixth printing
  ninety-five numbers across two tables with no column heading naming a quantity a reproduction
  targets. Nothing reachable outside the seeded thirty-one either
  (`datasets/manuscripts/candidate_survey.json`). **Its intake half landed 2026-08-30**
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
  the reading is a human act. **The first curator's reading of a real figure landed 2026-11-16**
  (`datasets/figures/Zake2021_figure5/`, taken with `scripts/digitize_figure_panels.py`): thirty
  curves of the metformin paper's Figure 5, whose peaks agree with its Table 6 to within 2.2%, all
  reproduced by the deposited model at normalized distances of 0.006 to 0.027, and all failing at the
  wrong dose or under the deposit's declared clock; all thirty are claims on that entry's published
  certificate (`figure_claims` in `datasets/pkpd_claims.json`). It is on a paper whose tables already reach the
  corpus, so it widens what that entry checks — whole curves, not one number per curve. **The first
  figure-only paper followed the same day**: Sluka et al. 2016's Figure 4, read in the digitizer's
  dark-line mode (a black line among black data markers), reproduced by BIOMD0000000619 at a
  normalized distance of 0.0065 with no assumption — the corpus's first clean pass, and the first
  entry off the blocked list since the metformin paper (27 blocked → 26; blind agreement 0/31 →
  1/31). **And the second deposit of that same paper followed** (2026-11-23): Figure 6, the
  standalone run of its sub-cellular metabolism module, is three black lines crossing twice with no
  markers at all, which needed the digitizer to follow lines *together* — traced one at a time, two
  of the three leave a crossing on the acetaminophen curve and read its values under their own
  names. It also needed the x axis converted: the figure is in minutes and the deposit's clock is
  seconds, so a claim may now state a `time_scale` as it already states a `value_scale`, and all
  three curves reproduce with it (0.0015 to 0.0022) and fail without it. BIOMD0000000624 is the
  corpus's second clean pass; blocked 26 → 25, blind agreement 1/31 → 2/31. The other 25 need the
  same act on their own papers' figures. **One of them was opened and measured rather than
  attempted** (2026-11-24, MODEL2301090001, Koeller et al. 2021's ICG liver-function PBPK). Three
  facts, in the order they matter. Its deposit **runs and responds to its paper's own stated
  doses**: 0.5 mg/kg into the model's 75 kg default peaks at 16.4 µmol/l where that paper's Figure
  2G shows about 18, so this entry is blocked for want of a *claim* and not for want of a runnable
  model — a distinction the blocked list could not previously make. Its figure, however, **cannot
  be read at the resolution the publisher serves**: Figure 2 is twelve panels in one 1084-px image,
  so panel G's plotting area is 234 px wide for seventy minutes, and the 2 mg/kg curve's entire
  rise — nought to 73.5 µmol/l, a hundred and ninety pixels of the y axis — happens inside **one
  pixel** of x. The peak is the quantity a pharmacokinetic claim is usually about, and at that
  scale a reading can say nothing about it; the decay is coarse but readable, eleven pixels from
  the peak to half of it. And the third fact is where a usable reference would come from instead:
  that paper's model *and the code that draws its figures* are published under CC-BY 4.0
  (github.com/matthiaskoenig/icg-model), and its data is in PK-DB — so the obstacle here is not a
  curator's time but a resolution the journal does not serve, with a published alternative that is
  a dataset rather than a picture. The other blocked papers are not all like this; three of the
  remaining ones are CC BY-NC-ND, which is a licensing question about redistributing a figure image
  rather than a technical one. **One of those three was then read** (2026-11-24, BIOMD0000000512, Benson et al. 2014's FAAH-inhibitor model): the licensing question answered itself, since this repository already redistributes content under terms more restrictive than its own — the BiGG models are academic and non-profit use only — and carries each source's terms in its notices rather than relicensing anything. An unmodified figure image in the publisher's own bytes is what CC BY-NC-ND permits, and what it decides is technical: the file stays JPEG, because re-encoding it would be the derivative that licence forbids. Figure 5 plots brain CB1 receptor occupancy at seven doses in seven colours with no data on the panel; six are claimed and four reproduce, the two partials missing only at the worst point of a steep descent. The seventh is read but not claimed, being near-black and inseparable from the dark edges of the saturated six. Blocked 25 → 24. The model also runs **without being rebuildable** — its concentrations are stated in a 1.45 L compartment and the reconstruction is amount-based — which is the first entry here certified purely by adopt-and-verify, with that limit stated on the certificate as this engine's rather than as the paper's. **And then the remaining papers' figures were measured rather than guessed at** (2026-11-24, `scripts/survey_published_figures.py` → `datasets/manuscripts/figure_survey.json`): 59 figures over seven of the papers behind the blocked entries — the seven whose open-access images can be fetched, accounting for 10 of the 24 blocked entries — each with the three properties that actually decide a reading — whether the image holds a closed plotting box the colour trace can locate, how many saturated hues it holds (a ceiling on how many series can be told apart), and the pixels per panel. **32 hold a closed box and 25 of those are drawn in two or more separable colours.** The belief the survey exists to refute is that the obstacle is *size*: it is not, and the numbers say so — the ten panels already read off Zake et al. 2021 are 280x257 pixels, which is 72,000 of them, and the *smallest whole image* still blocked is 151,800. Whether that beats Zake panel-for-panel the survey cannot say, because nobody has counted these papers' panels and `pixels_per_panel` is therefore an upper bound on 59 of 59 figures; what it can say is that the obstacle is not a publisher serving small files, which is the belief that was standing in for a measurement. What no property of an image shows is the third obstacle, whether the *curve* is resolvable in the panel it occupies, and the file says that of itself. The licence is recorded per paper for the same reason, and it decides *how* rather than *whether*: three papers are CC BY-NC-ND, whose figures are committed in the publisher's own bytes. The survey also records what it could not reach — the supplementary endpoint rate-limits and answers 500 under it, so a paper that errors keeps the figures an earlier run measured and says so in `carried_from`, and a run that measured fewer figures than the committed file refuses to overwrite it.

  **The first paper the survey sent us to turned out to be blocked by neither its figure nor its engine** (2026-11-24, BIOMD0000000608, Palsson et al. 2013's fully-integrated immune response model). Its figures are the most readable in the set — 600-pixel BMC images, four with closed boxes, up to nine separable hues, CC BY — and its deposit **runs under this repository's own pin in under a second**. What blocks it is that **140 of its 163 outputs are identified only by position** — all 52 of its species among them, named `x_1` through `x_52` — with no `name` that differs from the id, no SBO term and no annotation anywhere in the document: there is no output to point a claim at. No engine says so, because nothing is wrong with the mathematics — both import the file, integrate it to completion, and hand back one finite trajectory per output, none of which can be matched to anything the paper plots. That is now a check (`outputs_without_stated_meanings`), reported to the author by `archive-check` and, because that is where an author writing claims by hand actually starts, in `claims-template`'s notes beside the outputs it lists.

  **What counts as an output, and what the rule must not report, were both settled by measurement rather than taste.** An output is a species, or a parameter a rate rule or assignment rule drives. Scoring *every* parameter reports `k1`, `k3`, `V1`, `K1`, `r2` and `R5` across six of the models committed here — a rate constant named `k1` is an input the author chose and has said everything it needs to — so a constant is not scored. Scoring only *species* reports nothing at all for BIOMD0000000238, whose whole state is three rule-driven parameters called `X1`, `X2` and `X3`; that one is now a finding, and a proportionate one at three of its twenty-seven outputs, because the rest of that model names its quantities properly. The identifier rule is narrow in the same way: one letter and a number, so `IL6` is never reported. Its first version allowed two, and the test sweep caught it reporting exactly that — an interleukin is a quantity an immune-response model names `IL6`, and the check was being written on an immune-response paper. Swept over every model committed here, four outputs in two files are reported and both are right. The same sweep over the other twenty-three blocked entries found no third case, which is itself the answer to the obvious next question: this is Palsson's deposit, not a pattern in the backlog. Blocked for want of a *figure* and blocked for want of a *nameable output* are different facts about an entry, and until this the backlog could not tell them apart.

  **And with both measurements in hand, every one of the ten entries the survey covers now has a named obstacle** — which is the first time this list has been anything other than "needs figure digitization" repeated ten times:

  | Entries | Paper | What is actually in the way |
  | --- | --- | --- |
  | BIOMD0000000534-537 | Dwivedi et al. 2014 (IL-6 QSP) | **Nothing measured yet.** 5 of 8 figures hold a closed box and 3 of those carry 2+ separable colours. The strongest remaining candidate, and the largest single block in the backlog. |
  | BIOMD0000000608 | Palsson et al. 2013 (FIRM) | 140 of 163 outputs are identified only by position, so there is nothing for a claim to name. The figures are the most readable in the set; that is not the problem. |
  | BIOMD0000000490 | Demin et al. 2013 (5-LO PK/PD) | **0 of 6** figures hold a closed plotting box, so the colour trace has no panel to locate. |
  | MODEL1711210003 | Sier et al. 2017 (estradiol) | 118 reactions, a rate law for none of them: reaction topology, not a runnable model (`reactions_without_rate_laws`). |
  | MODEL2301090001 | Koeller et al. 2021 (ICG) | Readable by every property of the image, and still unreadable: the 2 mg/kg bolus puts 190 px of y range inside one pixel of x. Its figure-drawing code is published CC-BY. |
  | MODEL2301090002 | Grzegorzewski et al. 2022 (DXM) | Its results figure is box plots, not curves — not a target for a curve claim. |
  | MODEL2412270001 | Abbiati et al. 2021 (avadomide) | Ships an R script rather than SBML; 5 framed, coloured figures waiting behind that. |

  Dwivedi is the one line in that table with no named obstacle, and that is the measurement's doing: the script's own docstring had recorded it as the frameless pair alongside Demin, from memory and before anything was measured. Demin's six figures do measure as frameless. Dwivedi's five framed ones do not, so a sentence written from memory had written off the backlog's biggest block — which is now a test (`test_the_prose_about_which_papers_are_frameless_is_held_to_the_measurement`) rather than a sentence.

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
  Poisson/binomial results. **And its five certificates are clean passes since 2026-11-24**, which
  is the thing this class had never managed: every one of them read `partially-reproduced` for the
  ensemble Reprolith drew, and all five were the "not waiting on anyone" half of the verification
  queue. A draw stops being a choice the verdict rests on once its own error bar is within a tenth
  of the band the claim is judged in — the tenth the spatial class holds a finite grid to, keyed on
  the tolerance and never on the residual — and four of the five ensembles were simply bought up to
  it (to 4,000, 11,000, 12,000, and 85,000 for the Fano factor, whose error bar is `sqrt(2/n)` of
  its value). The fifth was already inside it and had been qualified for a choice that could not
  have moved it. The cross-engine corroboration got *stronger* as the samples grew — 1.9 combined
  standard errors to 1.0, resolving a bias above 2.1% where it could not have seen 6.5% — which is
  the check that had to pass first: a real disagreement between the two implementations would have
  grown instead. Now complete across the full class pattern: `stochastic_dossier` /
  `validate_stochastic` (unstated sampling protocol as a load-bearing gap), `certify_stochastic`,
  `ingest_stochastic_sbml`, the `lint_stochastic` inline linter, and a walkable 3/3 milestone.
- **Spatial / PDE simulation class** — *DONE*: landed as `spatial-class`, a pure-Python 1-D/2-D
  finite-difference reaction-diffusion solver reusing the curve oracle — and, since 2026-09-06, the
  scalar comparison too: `GradientClaim` certifies a reported **decay length** and
  `FrontSpeedClaim` a reported **invasion front speed**, which unlike a whole profile are numbers a
  paper prints in its text, so they are reachable by the table and prose extraction that already
  works rather than waiting on figure digitization. The front claim also measures its own
  convergence — a KPP speed approaches `2√(rD)` only logarithmically, so it reports how much the
  measurement is still moving and a reader can tell a still-converging run from a converged one.
  The third scalar, a Turing **pattern wavelength**, landed later the same day as `PatternClaim`.
  This entry said it could not be a claim type, and the obstacle it named was real: this class
  records every input a number turns on, and a two-species reaction has no canonical
  parameterization — Schnakenberg, Brusselator and Gierer-Meinhardt are different functions, and a
  claim taking a callable could not be re-derived from its own certificate. **Naming the family is
  the resolution**: `TURING_KINETICS` holds all three with their rate laws, steady states and
  Jacobians, a claim states one plus its two parameters, and a family this class does not implement
  is refused by name rather than approximated by a neighbour. Two measurements shaped the rest of
  it. The selected mode *moves while the pattern grows* (22 at t=3, 21 at t=6, 20 from t=9 on), so
  a claim states a confirming window and abstains when the mode changes across it. And the
  wavelength is *quantized* to 2L/m, so the claim reports the finest distinction its own domain can
  make and abstains where that is coarser than the width it would be judged at — resolving to 5%
  takes a domain holding twenty wavelengths. The certificate judges what the nonlinear run selects
  and reports the linear-stability prediction beside it, those being 16.0 and 15.24 on the
  self-validation configuration. Self-validated against
  closed-form results (Gaussian diffusion, Fisher-KPP and Nagumo front speeds, morphogen decay
  length, the Turing dispersion relation and wavelength selection). Has `spatial_dossier` /
  `validate_spatial` (unstated domain/boundary as a load-bearing gap), `certify_spatial`, the
  `lint_diffusion` inline linter, and a walkable 3/3 milestone. **Correction (2026-08-28):** this
  entry said ingestion was blocked because "there is no standard single-file interchange format for
  a reaction-diffusion model to ingest". There is one — the SBML Level 3 `spatial` package — and
  the pinned libSBML reads it, which was never checked before the claim was written down.
  `ingest_spatial_sbml` now reads the intersection that this solver runs (Cartesian geometry in one
  or two components with a stated extent, one isotropic diffusion coefficient per spatial species,
  a uniform initial concentration) and refuses the rest by name. It refused a stated **Dirichlet**
  wall too, for a reason that went stale twice — first that this solver had no other wall, then that
  a claim had no field to carry one — and neither is true now: the file's wall reaches the run
  (2026-09-06), and a claim that states its boundary is not qualified for a choice Reprolith did not
  make, so it can reach a clean pass. A prescribed non-zero flux is still refused, being a term this
  scheme does not have, as is a file asking for two different walls at once. What *is* blocked is narrower and still true: no published spatial model is in
  this corpus and none can be fetched here, so the reader is validated against files libSBML's own
  spatial API wrote, not against one from the field. **The single boundary condition is gone
  (2026-09-06):** `diffuse_1d` runs zero-flux, Dirichlet (absorbing or held at a value) and
  periodic walls, each validated against the exact eigenmode decay for that boundary and against
  what it does to mass — reflect, absorb, wrap. The default is unchanged, so every published
  certificate still means what it meant. What the second wall *buys* is the measurement: the
  boundary assumption used to say the distance "moves with a choice the paper did not make" and
  could only assert it, and each spatial certificate now carries what the choice costs that claim
  — on the three committed profiles the judged distance moves by 2e-10 to 2e-06 against a pass
  threshold of 1e-01. On a claim that states no wall the assumption stays load-bearing and stays
  this engine's limit — the wall is then Reprolith's — and what changed is that its cost is a
  number. **This entry said a claim carries no field naming a boundary, which stopped being true
  the same day it was written:** `SpatialClaim.boundary` carries the source's wall through to the
  run, so a claim that states one is neither assumed for nor qualified, and `ingest_spatial_sbml`
  stopped refusing a file that states a Dirichlet wall. The sentence is corrected here rather than
  deleted, because the limitation was real until it was not.
  Measuring it also turned up an accuracy fact written down nowhere: the mirrored-ghost-point
  zero-flux wall is **first-order** (error ratio 1.95 as the grid halves) while Dirichlet and the
  interior stencil are second-order (4.00), so wherever a wall influences the answer this solver's
  order is set by its boundary and not by its stencil.
- **Whole-cell and very large QSP networks** — in-kind but often intractable under a single
  pinned engine; wait for item 5 and better resource handling.
- **A hosted web dashboard** — valuable for outreach, but the certificate and MCP surface come
  first; presentation follows substance.
