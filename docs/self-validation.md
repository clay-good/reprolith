# Self-validation across all model classes

Reprolith's central discipline is that its verdicts are measured blind against reproducibility
whose truth is independently established, on the *same* shared machinery for every model class. This
page is the one-look summary of that evidence; each row links to a walkable milestone a stranger can
follow end to end, all regenerable from the repository alone.

| Class | Blind agreement | Independent ground truth | Milestone |
|---|---|---|---|
| **PK/PD (ODE)** | 1 reproduced matching its label + 27 honest abstentions + **3 verdicts stricter than the label**, over 31 BioModels entries; no false pass | BioModels manual-curation status; the metformin claim read from the paper | [`datasets/milestone/`](../datasets/milestone/) |
| **Constraint-based (FBA)** | **8/8** blind agreement across bacteria, a pathogen, and a eukaryote | E. coli core's documented growth rate; COBRApy references for the genome-scale set | [`datasets/constraint_based/milestone/`](../datasets/constraint_based/milestone/) |
| **Generic-kinetic (ODE)** | **6/6** blind agreement across six network types | libRoadRunner (independent CVODE) reference trajectories | [`datasets/kinetic/milestone/`](../datasets/kinetic/milestone/) |
| **Logical (Boolean)** | **9/9** blind agreement (incl. three 44–60-node models at scale) | CANA attractor signatures — how many attractors and the period of each, which is what the reference records; not the attractor states themselves (small models) + the SHA-256 of the fixed-point **set** an independent SAT solver found (the large signalling networks). Every certificate states the update scheme its numbers were computed under | [`datasets/logical/milestone/`](../datasets/logical/milestone/) |
| **Stochastic (SSA)** | **3/3** blind agreement, every one `partially-reproduced` | Closed-form Poisson / binomial means (analytical) | [`datasets/stochastic/milestone/`](../datasets/stochastic/milestone/) |
| **Spatial (reaction-diffusion)** | **3/3** blind agreement, every one `partially-reproduced` | Closed-form Gaussian diffusion (analytical) | [`datasets/spatial/milestone/`](../datasets/spatial/milestone/) |

Two rows read `partially-reproduced` where the profile or the mean matches its analytical target
exactly, and that is the point: the stochastic class samples an ensemble Reprolith chose, and the
spatial class runs every profile under a zero-flux boundary Reprolith imposes rather than one the
paper stated. Both are load-bearing assumptions, both are named on the certificate, and a class
does not get to publish a clean pass for a result resting on its own choice.

That zero-flux boundary is also why `ingest_spatial_sbml` refuses any other kind. A file in the
SBML L3 `spatial` package can state a Dirichlet wall; this solver would run it under Neumann walls
and produce a profile with nothing to say it had substituted one boundary for another. A refusal
names it instead. (No published spatial model is in this corpus, so that reader is checked against
files libSBML's own spatial API wrote — the spec's reference implementation, not the field.)

## What makes each row honest

- **Blind by construction.** The ground-truth label lives on the catalog entry but has no field in
  the blind view handed to the verdict path; every verdict is produced without reading it.
- **Non-circular ground truth.** The FBA, kinetic, and logical references come from *independent*
  implementations (COBRApy, libRoadRunner, CANA) that share no code with Reprolith's engines, and
  the PK/PD metformin value is read from the manuscript, not re-derived. Reprolith reproducing them
  is a genuine cross-check, not a tool agreeing with itself. For the logical class the exported
  rules are additionally *proven faithful* to CANA's model — checked against CANA's own per-node
  step over every input — before the attractor signatures are compared. The logical class also
  scales past enumeration for *fixed points*: three real signalling networks of 44–60 nodes (T-LGL
  leukemia, MAPK cancer cell-fate, guard-cell ABA — up to a 2⁶⁰ space) have their steady states
  found by SAT and cross-validated against an independent SAT solver (Reprolith's z3 vs the
  reference's sympy), each verified to be a genuine fixed point.
- **Depth beyond a single number.** FBA cross-validates the FROG **objective** across all eight
  models up to genome scale (iJO1366, 2583 reactions), spanning bacteria, a pathogen, and a
  eukaryote; the other two FROG components are cross-validated on fewer models — flux variability
  on two (E. coli core and iIT341) and gene/reaction deletion on E. coli core — plus **synthetic
  lethality** — its
  double-deletion analysis reproduces COBRApy pair-for-pair on E. coli core, both at reaction level
  (`double_reaction_deletion`, all 111 synthetic-lethal reaction pairs) and gene level
  (`double_gene_deletion`, all 53 synthetic-lethal gene pairs through the GPR rules) — an epistasis
  single deletion cannot see — and it generalizes: reaction synthetic lethality also reproduces
  COBRApy on a bounded subset of a second, different-organism model (iIT341, *H. pylori*) —
  **loopless FVA** — its loop-law MILP reproduces COBRApy's independent
  `flux_variability_analysis(loopless=True)` reaction-for-reaction on E. coli core — **pFBA**,
  whose minimized total flux matches COBRApy's `pfba` on the same model, and the **production
  envelope**, whose acetate-vs-growth frontier reproduces COBRApy's `production_envelope` point for
  point. Kinetic **and PK/PD** verdicts are additionally shown **engine-independent** — every
  model reproduces under COPASI and libRoadRunner to a published bound — the worst is the
  repressilator at a normalized distance of 3.2e-4, three orders inside the pass threshold
  (`corroborate_curve`, reported alongside the certificates rather than gating them; see
  `docs/kinetic-class.md`), so no verdict rests on one solver's quirk. PK/PD is corroborated **per
  claim, at the dose the claim was certified at**: metformin's two claims differ by a 779.9 mg
  free-base override, and checking both on the model's default arm would have compared one run to
  itself and reported stability for an arm neither claim uses. Both halves of this now reach the
  public registry, which said nothing about corroboration either way: the classes that have a
  second registered engine, with what it agreed to, **and the ones that do not** — for which
  nothing was checked, an absence rather than a pass, since a page listing only the corroborated
  classes leaves a reader to infer the rest were checked and passed.
- **The same contracts throughout.** All six classes flow through one catalog lifecycle, one
  agreement report, one certificate format, and one inescapable scope flag — the generalization is
  demonstrated, not asserted. The logical class proves the point hardest: a third, discrete oracle
  (attractors) with no continuous trajectory and no optimization, carried by the same contracts.

## Where the disagreements are explained

Every disagreement in the tables above carries a written note naming the stage responsible and
whether it was fixed or explained, and every failure-mode category and default tolerance names what
put it there. That record is committed data, and a gate audits it against the artifacts rather than
trusting the prose: see [`discipline-loop.md`](discipline-loop.md).

## Read it live

This track record is not just prose here — it is queryable through the same read surface that
serves verdicts, so an agent can weigh a class's proven reliability before citing one of its
certificates. `reprolith self-validation` (or the MCP `self_validation` tool) reports it per class
and overall, straight from the committed agreement reports:

```
$ reprolith self-validation
  class               matched  abstained  other  of total
  constraint-based          8          0      0  / 8
  ...
  ode-pkpd                  1         27      3  / 31
  overall: 30 matched, 27 honest abstentions, 3 other, over 60 labelled entries across 6 classes
  (an abstention is a 'blocked' verdict — insufficient information — not a wrong verdict)
  ode-pkpd: 3 labelled 'reproduced' came back 'partially-reproduced' — stricter than the label
```

It deliberately reports no single blended agreement rate: an *abstention* (a `blocked` verdict —
insufficient information) is counted apart from a wrong verdict, so the PK/PD run's honest
abstentions are never dressed up as agreement or misread as error.

And **`other` says which direction it ran in**. It is the one number here that records where
Reprolith was wrong, and for a long time it was the only one with no account of itself, sitting
beside abstentions that carry a sentence explaining they are not wrong verdicts. Two different
facts landed in it under one word: a label of `reproduced` against a blind `partially-reproduced`
is Reprolith withholding a pass somebody else gave, and a label of `not-reproduced` against a blind
`reproduced` is a **false pass** — the failure this project exists not to commit. The CLI, the
queried JSON (through each class's own `confusion` rows) and the public registry banner all name
them now. Today's three are all the first kind.

The per-entry rows behind these numbers stay in the committed report files and are not published
through the read surface. They pair an accession with its ground-truth label, and those same
accessions sit in the live work queue — publishing them would hand a reproducing agent the answer
key for the paper it is about to claim.

### The other question: was it one solver's answer?

Agreement with a ground-truth label says a verdict was *right*. It does not say the verdict was the
**model's** behaviour rather than one simulator's quirk — a solver-specific integration artifact
reproduces a paper for the wrong reason, and agrees with its label while doing it. That is what
cross-engine corroboration asks: run the same model under a second, independently-implemented
engine at the conditions each claim was certified at, and see whether the same numbers come out.

It is reported beside the verdicts and never gates them, and it is now queryable from the same
surface everything else here is (`reprolith corroboration`, or the MCP `corroboration` tool). Until
then it was computed, committed to each milestone directory as `corroboration.json`, and rendered
on the public registry page alone — so a reader at a terminal, and an agent reading over MCP, saw
six classes of verdicts with nothing saying which of them a second simulator had ever confirmed.

```
$ reprolith corroboration
CROSS-ENGINE CORROBORATION (a second, independent simulator on the same runs)
  reported beside the verdicts, never gating them
  constraint-based      8 model(s) on cobrapy, scipy-linprog — all engine-independent to 1e-08
                          as cobrapy 0.31.1, scipy-linprog highs (reprolith-fba rev 28080c800649)
  kinetic               6 model(s) on copasi, roadrunner — all engine-independent to 1e-03
                          as copasi 4.46.300 (Source), roadrunner 2.7.0
  logical               9 model(s) on cana, reprolith-logical, sympy-sat — all agree exactly
                          as cana 1.0.0, reprolith-logical synchronous-update, exhaustive-state-enumeration (rev 7641c872354c), reprolith-logical synchronous-update, sat-fixed-points (z3 5.0.0) (rev 7641c872354c), sympy-sat 1.14.0
  ode-pkpd             80 claim(s) on copasi, roadrunner — all engine-independent to 1e-06
                          as copasi 4.46.300 (Source), roadrunner 2.7.0
  spatial               3 model(s) on reprolith-fd, scipy-lsoda — all engine-independent to 1e-03
                          as reprolith-fd explicit-forward-euler-finite-difference (rev 15f00d5fb8fc), scipy-lsoda 1.13.1
  stochastic            3 model(s) on reprolith-ssa, roadrunner-gillespie — all engine-independent within 1.9 combined standard errors, resolving a bias above 6.5% of the mean
                          as reprolith-ssa gillespie-direct-method (rev b4d8d2ffc52b), roadrunner-gillespie 2.7.0

  overall: 6 of 6 classes re-run on a second engine — 80 claim(s), 29 model(s)
```

Three things about that output are deliberate.

**Every class is listed, including any with nothing to report.** All six carry a second engine
today; for most of this project's life two did not, and the reason they now do is worth keeping
rather than deleting with the line that said it. The record claimed no installed implementation
but this one answered their questions — a Gillespie ensemble and a finite-difference
reaction-diffusion solve. Neither half was ever checked, and neither held: libRoadRunner ships a
Gillespie integrator, and scipy's LSODA integrates a method-of-lines diffusion system, and both
were already installed here. The shape that prints an absence in the same list as the passes is
kept, because a class can lose an engine and a table of only the corroborated ones would read as
a whole-repository pass.

And **the stochastic line does not say "to 1.9"**, because it is not a distance. Two engines that
solve an ODE or a linear program agree to their last digits; two Gillespie *ensembles* of the same
model agree only up to Monte Carlo error, so what is compared there is the difference of the two
means over their combined standard error — a count, whose criterion is three. Rounded to a decade
and printed on the other classes' scale it would read as `2e+00`, four orders worse than the
kinetic class rather than as a pass. The wording is chosen by the *comparison*, in one shared
function, because the terminal, the agent surface and the public page had three copies of that
decision and a third comparison kind would have reached some of them and not others.

That line also carries **what the agreement could not have seen**. Two ensembles agree at any
criterion if they are small enough, so a bare "they agreed" is a claim whose strength is whatever
the ensembles happened to be. Three standard errors of the Poisson-mean-10 network's 400
trajectories is 6.5% of its mean — *wider than the 5% that class's own scalar verdict passes at*,
so this corroboration is weaker than the verdict it stands beside and the record says so. The
reversible-isomerization entry, whose equilibrium spread is much tighter, resolves 1.8%.

The **spatial line's 1e-03 is not a distance from the truth**, and it is the number most likely to
be quoted as one. scipy integrates the *semi-discrete* system essentially exactly, so what the two
engines differ by is what this class's fixed-step explicit stepper costs in time discretization —
first order in `dt`, and confirmed to halve when `dt` does. Against the continuum solution the
explicit scheme does *better* than that: 2.0e-05 from the closed-form Gaussian, six times closer
than the two engines are to each other, because central differencing and forward Euler have
truncation errors of opposite sign that cancel exactly at a diffusion number of 1/6 and nearly so
at the 0.2 these run at. And this pair does not separate the spatial discretization at all: both
sides take second-order central differences with the boundary cell mirrored. That is the scheme
the class certifies under, and two implementations of one scheme agree about the scheme's error.

And the **two counts are never added up.** The classes do not count the same thing: PK/PD re-runs
each *claim* at the dose it was certified at, and the kinetic class re-runs each *model*'s curve
once. Adding eighty claims to six models gives an `86` that reads as four times what was re-run, so
the total states the two units apart, and each class's unit is read off its own record's keys
rather than assumed.

And the record **names the builds it was measured on**. A certificate expires when the software
that computed it changes, and says which software that was; a corroboration bound carries the same
weight and for a long time named none at all, so a number measured against one libRoadRunner read
as current against every later build. The versions are read off the two libraries after they
produce the trajectories, never declared. A record written before they were captured prints
"engine builds unstated" rather than borrowing the versions installed today — filling that gap
would make a stale bound look fresh, which is the opposite of what naming it is for.

The bound published per class is the **worst** one in it, not the best, and each individual bound
is already rounded up to a decade — a distance between two agreeing engines is a difference of
nearly-equal numbers, and its leading digits are the engines' own last-place noise. The published
number never states better agreement than was measured.

### What these numbers do and do not establish

Read them as evidence about **abstention discipline**, not classification skill.

- The PK/PD labels are BioModels curation status, and curation status *is* the accession prefix —
  so "starts with `BIOMD` → reproduced" scores 31/31 on that set. The accession travels with the
  blind entry, so an agent guessing from the prefix would outscore honest work. What the PK/PD run
  shows is that Reprolith abstained on 27 of 31 entries, matched the label on one, and disagreed
  with it three times — every disagreement in the **stricter** direction, a label of `reproduced`
  against a blind `partially-reproduced`. That is a withheld pass, not a false one, and the
  distinction is the whole of what this row is worth: the failure this project exists not to commit
  is calling an irreproducible result reproduced, and that has happened zero times. Saying "zero
  wrong verdicts" collapsed the two, and this page said it while the run had three of the first
  kind. `reprolith self-validation` now names the direction of each, so the sentence cannot drift
  from the record again.
- Five of the six classes carry a single constant label (every entry `reproduced`, or every entry
  `partially-reproduced`), so "always answer reproduced" would score 100% on them. Their value is
  that an *independent implementation* — COBRApy, libRoadRunner, CANA — computed the same numbers,
  which is a check on the simulator, not a discrimination test.

Establishing blind discriminative skill needs a label source independent of the identifier, and a
set with real label variance. Reprolith does not have one yet, and does not claim to.

## Closed-form reproductions (the simulators themselves)

The table above is blind agreement with *independent tools* on *real* models. Underneath it, each
simulator is also checked directly against **exact analytical results** — no external tool, no
fitted data, the formula verified empirically before it is asserted. These run in the core CI job
(the spatial, stochastic, and logical simulators are pure Python; FBA uses scipy's LP solver), so
the whole catalogue below is reproduced on every commit.

| Class | Canonical result reproduced | Analytical law | Test |
|---|---|---|---|
| Spatial | Point-source diffusion (1-D & 2-D) | Gaussian, variance → var₀ + 2Dt | `test_pure_diffusion_reproduces_the_analytical_gaussian`, `…_2d_…_field` |
| Spatial | Diffusion with first-order decay | exponential decay of total mass | `test_first_order_decay_matches_the_exponential_analytical_solution` |
| Spatial | Fisher-KPP pulled front | c = 2·√(rD) | `test_fisher_kpp_reproduces_the_analytical_front_speed` |
| Spatial | Bistable (Nagumo) pushed front | c = √(D/2)·(1−2a) | `test_bistable_nagumo_reproduces_the_exact_pushed_front_speed` |
| Spatial | Morphogen gradient | decay length λ = √(D/k) | `test_morphogen_gradient_reproduces_the_analytical_decay_length` |
| Spatial | Turing dispersion relation | growth rate = dominant eigenvalue of J − k²·diag(D) | `test_two_species_reaction_diffusion_reproduces_the_dispersion_relation` |
| Spatial | Turing wavelength selection | emergent mode = argmax_m λ(kₘ) | `test_schnakenberg_reproduces_the_turing_wavelength_selection` |
| Spatial | Spatial-SIR epidemic wave | c = 2·√(D(β·S₀ − γ)) | `test_spatial_sir_reproduces_the_epidemic_wave_speed` |
| Stochastic | Birth-death stationary moments | mean = variance = k/γ (Poisson) | `test_immigration_death_reproduces_the_poisson_stationary_mean_and_variance` |
| Stochastic | Birth-death full distribution | χ² goodness-of-fit vs the exact Poisson PMF | `test_immigration_death_reproduces_the_full_poisson_stationary_distribution` |
| Stochastic | Transient relaxation | λ(t) = (k/γ)(1 − e^{−γt}) | `test_transient_poisson_percentile_envelope_is_reproduced` |
| Stochastic | Reversible reaction equilibrium | binomial equilibrium mean | `test_reversible_reaction_reproduces_the_binomial_equilibrium_mean` |
| Stochastic | Intrinsic-noise laws | Fano = 1, CV = 1/√mean | `test_poisson_fano_factor_and_noise_scaling_law` |
| Stochastic | Bursty expression | super-Poissonian Fano = (b+1)/2 | `test_bursty_production_reproduces_the_super_poissonian_fano_law` |
| Stochastic | Small-population extinction | mean time = H_{N₀}/γ (harmonic) | `test_pure_death_reproduces_the_harmonic_extinction_time` |
| Stochastic | Gillespie direct method | Exp(a_total) waiting time; firing ∝ propensity | `test_direct_method_reproduces_its_two_defining_probabilities` |
| Logical | Thomas' rules | positive circuit → multistability; negative → oscillation | `test_reproduces_thomas_rules_positive_and_negative_feedback_circuits` |
| Logical | Update-scheme artifact | synchronous spurious cycle absent under async | `test_synchronous_update_creates_a_spurious_cycle_that_async_resolves` |
| Logical | Derrida annealed slope | expected Hamming spread = 2·p·(1−p)·K | `test_derrida_slope_matches_the_annealed_law_2p1mpk` |
| Logical | Kauffman critical connectivity | order/critical/chaos at K = 1 / 2 / 3 (p = ½) | `test_critical_connectivity_is_two_for_unbiased_networks` |
| Logical | Expected fixed-point count | E[# fixed points] = 1, independent of N and K | `test_expected_fixed_point_count_is_one_independent_of_size`, `…_independent_of_connectivity` |
| FBA | Pasteur effect | anaerobic 0.2117 /h vs aerobic 0.8739 /h | `test_anaerobic_growth_rate_is_the_pasteur_effect_value` |
| FBA | Linear growth law | biomass affine in glucose uptake (R² = 1) | `test_biomass_is_exactly_affine_in_glucose_uptake` |
| FBA | Phenotypic phase plane | growth vs O₂ is concave, piecewise-linear, with a saturation breakpoint | `test_oxygen_phenotypic_phase_plane_is_concave_with_a_saturation_breakpoint` |
| FBA | LP duality (shadow prices) | dual = ∂Z*/∂b; complementary slackness; strong duality Z* = Σ rc·bound | `test_metabolite_shadow_prices_are_the_primal_optimum_sensitivity`, `test_strong_duality_reconstructs_the_optimum_from_the_binding_bounds` |
| FBA | Shadow price = phase-plane slope (real model) | O₂ marginal value falls then hits zero at the breakpoint (E. coli core) | `test_oxygen_marginal_value_is_positive_and_falling_then_zero_at_the_plateau` |
| FBA | Loopless FVA (toy + real) | an internal cycle's flux is thermodynamically infeasible → loopless range collapses to the hand-derived value where plain FVA inflates it; on E. coli core the textbook FRD7/SUCDi loop's spurious ~1000 range is stripped | `test_loopless_fva_collapses_the_cycle_to_its_thermodynamic_range`, `…_equals_standard_fva_on_a_loop_free_model`, `test_loopless_fva_removes_the_e_coli_core_frd7_sucdi_loop` |
| FBA | Production envelope (Varma & Palsson) | the growth-vs-byproduct frontier is concave and piecewise-linear (parametric-LP theorem), with E. coli core's overflow-metabolism acetate breakpoint | `test_production_envelope_frontier_is_concave_and_piecewise_linear` |

Non-circular by construction: the reference is a mathematical law (a front speed, a dispersion
relation, a noise law, an attractor theorem, an LP-duality consequence), not a number this engine
produced. Where a law is only approached asymptotically — the KPP pulled front converges
logarithmically — the tolerance is a stated, principled override rather than the 5% default.

## Regenerate it

```bash
pip install -e ".[dev,engine,fba]"
python scripts/run_milestone.py            # PK/PD
python scripts/run_fba_milestone.py        # constraint-based
python scripts/run_kinetic_milestone.py    # generic-kinetic
python scripts/run_logical_milestone.py    # logical (reads committed CANA references)
python scripts/run_stochastic_milestone.py # stochastic (closed-form Poisson/binomial ground truth)
python scripts/run_spatial_milestone.py    # spatial (closed-form Gaussian diffusion ground truth)
python scripts/render_worked_examples.py   # the three renders that live outside a milestone dir
python scripts/build_registry.py           # the public registry page
```

Run the last two after the milestone scripts. `render_worked_examples.py` exists because the three
worked-example certificate texts — metformin, *E. coli* core, and the logical toggle — are published
renders that no script regenerated, and the metformin one had drifted to naming an engine pin with
no judge revision while its own machine-readable certificate carried one. `tests/test_pins.py` now
fails on any committed render that does not name the current revision, and on any render in a
directory no freshness check covers.

The reference values themselves are regenerable from the independent tools with the `refgen` extra;
see [CONTRIBUTING.md](../CONTRIBUTING.md). Every certificate says, in plain text, that it attests
only to computational reproducibility — never biological correctness or clinical fitness.
