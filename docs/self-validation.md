# Self-validation across all model classes

Reprolith's central discipline is that its verdicts are measured blind against reproducibility
whose truth is independently established, on the *same* shared machinery for every model class. This
page is the one-look summary of that evidence; each row links to a walkable milestone a stranger can
follow end to end, all regenerable from the repository alone.

| Class | Blind agreement | Independent ground truth | Milestone |
|---|---|---|---|
| **PK/PD (ODE)** | 1 partially-reproduced + 30 honest abstentions, **0 wrong verdicts** over 31 BioModels entries | BioModels manual-curation status; the metformin claim read from the paper | [`datasets/milestone/`](../datasets/milestone/) |
| **Constraint-based (FBA)** | **7/7** blind agreement across bacteria, a pathogen, and a eukaryote | E. coli core's documented growth rate; COBRApy references for the genome-scale set | [`datasets/constraint_based/milestone/`](../datasets/constraint_based/milestone/) |
| **Generic-kinetic (ODE)** | **6/6** blind agreement across six network types | libRoadRunner (independent CVODE) reference trajectories | [`datasets/kinetic/milestone/`](../datasets/kinetic/milestone/) |
| **Logical (Boolean)** | **4/4** blind agreement on real published models | CANA (independent Boolean-network library) attractors | [`datasets/logical/milestone/`](../datasets/logical/milestone/) |
| **Stochastic (SSA)** | **3/3** blind agreement | Closed-form Poisson / binomial means (analytical) | [`datasets/stochastic/milestone/`](../datasets/stochastic/milestone/) |
| **Spatial (reaction-diffusion)** | **3/3** blind agreement | Closed-form Gaussian diffusion (analytical) | [`datasets/spatial/milestone/`](../datasets/spatial/milestone/) |

## What makes each row honest

- **Blind by construction.** The ground-truth label lives on the catalog entry but has no field in
  the blind view handed to the verdict path; every verdict is produced without reading it.
- **Non-circular ground truth.** The FBA, kinetic, and logical references come from *independent*
  implementations (COBRApy, libRoadRunner, CANA) that share no code with Reprolith's engines, and
  the PK/PD metformin value is read from the manuscript, not re-derived. Reprolith reproducing them
  is a genuine cross-check, not a tool agreeing with itself. For the logical class the exported
  rules are additionally *proven faithful* to CANA's model — checked against CANA's own per-node
  step over every input — before the attractor signatures are compared.
- **Depth beyond a single number.** FBA cross-validates all three FROG components (objective,
  flux-variability, gene/reaction deletion) across seven models up to genome scale (iJO1366, 2583
  reactions) and spanning bacteria, a pathogen, and a eukaryote, plus **loopless FVA** — its loop-law MILP reproduces COBRApy's independent
  `flux_variability_analysis(loopless=True)` reaction-for-reaction on E. coli core — **pFBA**,
  whose minimized total flux matches COBRApy's `pfba` on the same model, and the **production
  envelope**, whose acetate-vs-growth frontier reproduces COBRApy's `production_envelope` point for
  point. Kinetic verdicts
  are additionally shown **engine-independent** — every model
  reproduces identically under COPASI and libRoadRunner (`corroborate_curve`), so no verdict rests
  on one solver's quirk.
- **The same contracts throughout.** All six classes flow through one catalog lifecycle, one
  agreement report, one certificate format, and one inescapable scope flag — the generalization is
  demonstrated, not asserted. The logical class proves the point hardest: a third, discrete oracle
  (attractors) with no continuous trajectory and no optimization, carried by the same contracts.

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
```

The reference values themselves are regenerable from the independent tools with the `refgen` extra;
see [CONTRIBUTING.md](../CONTRIBUTING.md). Every certificate says, in plain text, that it attests
only to computational reproducibility — never biological correctness or clinical fitness.
