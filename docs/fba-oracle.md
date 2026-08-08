# The constraint-based (FBA) oracle

Flux-balance analysis models make a different kind of claim than the PK/PD curve models: not
"does the model regenerate a time course" but "does the model's optimization reproduce the
reported outcome." So the constraint-based-class gets its own oracle in
[`reprolith.fba`](../python/reprolith/fba.py). It reuses the shared contracts — every judge
returns the same `ClaimAssessment` the certificate consumes, classified by the same tolerance
machinery as the PK/PD oracle — and adds only the FBA-specific comparisons.

The oracle lives behind the optional **`fba`** extra (scipy's linear solver), imported lazily so
the core stays dependency-free. Install with `pip install -e ".[fba]"`; the tests skip without it.

## Why FBA needs its own honesty rule

An FBA model's optimum is unique, but the *flux distribution* that achieves it usually is not:
many different flux vectors hit the same objective value (**alternate optima**). A naive oracle
that solved once and compared the returned flux vector to a paper's reported fluxes would report
disagreement that is an artifact of solver tie-breaking, not a real discrepancy — or, worse,
agreement that is luck. Both betray design goal 2: *a confidently wrong verdict is worse than an
honest abstention.*

Every method below is built to be well-defined regardless of which optimal vertex the solver
happens to land on.

## The fingerprints

| Function | Answers | Well-defined under alternate optima because… |
|---|---|---|
| `solve_objective` / `judge_objective` | What is the optimal objective value, and does it match the reported one? | the objective value is unique even when the flux vector isn't |
| `reaction_essentiality` / `essentiality_agreement` | Which reactions, knocked out, collapse the objective? Do they match the reported essential set? | essentiality is a property of the objective optimum, not of any one flux vector |
| `gene_essentiality` | Which *genes*, deleted, collapse the objective — honoring each reaction's AND/OR gene rule? | gene deletion forces to zero only the reactions whose GPR rule fails; essentiality is still an objective property |
| `flux_variability` | What min/max can each reaction's flux take while the objective stays optimal? | it reports the *whole* feasible interval instead of picking one vector |
| `loopless_flux_variability` | Same interval, but with thermodynamically infeasible internal loops removed | it adds the loop law (Schellenberger 2011) so a spurious internal cycle can't inflate the interval |
| `judge_flux` | Does a reported reaction flux reproduce? | it judges against the variability interval, and abstains when the model leaves the flux free |

### `judge_flux` — the honest verdict for a reported flux

Given a reported flux and its variability interval `(min, max)` (from `flux_variability`):

- **pinned and contains the report** (`min == max` within tolerance) → the model uniquely
  produces this flux: judged as a scalar, so it reproduces.
- **inside a non-trivial interval** → the model is *consistent with* the value but does not
  determine it. Certifying "reproduced" would overstate what the model earns, so the verdict is
  **`not-evaluable`** (abstain), with a reason naming the interval.
- **outside the feasible interval** → the model cannot reach this flux at the optimum: judged
  against the nearest feasible flux, so it lands `partial`/`failed` and — like any non-pass —
  requires a root-cause attribution.

## The FROG fingerprint

The spec makes the verdict for a curated model a *fingerprint comparison*, not a single number.
`frog_fingerprint` bundles the results into one standardized, solver-independent artifact — named
for the field's FROG analysis (Flux optimum, Reaction variability, Objective, Gene/reaction
deletion):

- the optimal **objective value**,
- each reaction's **flux-variability interval**,
- the **deletion objective** for each reaction (the optimum with that reaction knocked out), and
- the **gene-deletion objective** for each gene (the optimum with that gene deleted, forcing to
  zero every reaction whose gene–protein–reaction rule then fails).

Gene deletion is populated whenever the model carries GPR rules — `ingest_fbc_sbml` parses each
reaction's SBML-fbc `geneProductAssociation` into a boolean rule (`FbaModel.gene_associations`), so
a model with gene data gets the full four-part FROG and one without simply has an empty gene section.

`compare_frog` then checks two fingerprints component-wise, aligning reactions *and genes* by id and
naming every disagreement — an id present in only one fingerprint is a disagreement, so a structural
mismatch is never hidden behind a numeric pass.

```python
from reprolith import frog_fingerprint, compare_frog, judge_fingerprint, ingest_fbc_sbml

fp = frog_fingerprint(ingest_fbc_sbml(model_sbml))
comparison = compare_frog(fp, curated_fingerprint)   # comparison.agrees, comparison.disagreements
assessment = judge_fingerprint(                       # -> a certificate-ready ClaimAssessment
    claim_id="frog", quantity="FROG fingerprint", source_location="curation",
    comparison=comparison,
)
```

`judge_fingerprint` maps the comparison onto the shared assessment contract — agreement
reproduces, otherwise it fails with the named component disagreements recorded as the discrepancy —
so a fingerprint verdict feeds `build_certificate` exactly like a scalar or curve one.

## The LP dual — shadow prices and reduced costs

The FROG fingerprint reads the optimum from the primal side. Its economic dual — what each
metabolite and each capacity limit is *worth* at the optimum — is a separate, standard FBA output
(COBRApy exposes it as `shadow_prices` / `reduced_costs`). `shadow_prices` returns both from the
LP's dual variables, signed as sensitivities of the *maximized* objective:

- each metabolite's **shadow price** — ∂Z\*/∂b, the change in the optimum per unit of net
  production imposed on that metabolite's mass balance, and
- each reaction's **reduced cost** — ∂Z\*/∂bound, the change per unit relaxation of its active flux
  bound, zero for any reaction not sitting at a bound (complementary slackness).

```python
from reprolith import shadow_prices, ingest_fbc_sbml

m = ingest_fbc_sbml(model_sbml)
dual = shadow_prices(m.stoichiometry, m.objective, m.lower, m.upper)  # .metabolites, .reactions
```

The duals are validated non-circularly: `tests/test_fba_shadow_prices.py` checks each returned
value against the derivative of the primal optimum estimated by re-solving perturbed LPs, and
confirms LP strong duality reconstructs the optimum from the binding bounds alone — a check that
shares nothing with reading the solver's dual marginals.

## Parsimonious FBA — a canonical flux vector

`judge_flux` abstains whenever the optimum does not *pin* a reaction's flux (the alternate-optima
rule above). `parsimonious_fluxes` gives the standard way to pick a single, motivated flux vector
anyway: pFBA (Lewis et al. 2010) holds the objective at its optimum and, among all vectors that
reach it, minimizes the total flux Σ|vᵢ| — the least-enzyme solution. It is a two-stage LP kept as
one solve by linearizing each |vᵢ| with an auxiliary variable.

```python
from reprolith import parsimonious_fluxes, ingest_fbc_sbml

m = ingest_fbc_sbml(model_sbml)
sol = parsimonious_fluxes(m.stoichiometry, m.objective, m.lower, m.upper)  # .fluxes, .total_flux
```

Parsimony is **load-bearing**: a flux certified from `sol.fluxes` is reproduced *under the parsimony
assumption*, and should be qualified as such rather than presented as the model's only behavior.
Validated non-circularly in `tests/test_fba_parsimonious.py` against analytically known
minimal-flux solutions (a short route chosen over a detour, a pinned chain recovered exactly) and,
on the real E. coli core model, shown to preserve the documented optimum.

## Loopless FVA — the range a real flux can reach

Plain `flux_variability` can report a spuriously wide interval for a reaction on an internal
stoichiometric cycle: the cycle satisfies `S·v = 0` for any magnitude yet carries no net
thermodynamic driving force, so that flux is a solver artifact, not real flexibility.
`loopless_flux_variability` adds the loop law (Schellenberger et al. 2011) — every internal
reaction's flux must be sign-opposed to a *conservative* energy field, one orthogonal to every
internal cycle, so no cycle runs uphill — encoded as a mixed-integer program. On a model with no
internal loops the internal null space is trivial and it reproduces `flux_variability` exactly.

```python
from reprolith import loopless_flux_variability

intervals = loopless_flux_variability(stoich, objective, lower, upper)  # one (min, max) per reaction
```

A loopless interval feeds `judge_flux` unchanged — it is just a tighter `(min, max)` — which is
where the honesty payoff lands: a reaction whose *only* flexibility was the loop is inflated by plain
FVA into a wide interval, so `judge_flux` abstains (`not-evaluable`) on a value the model actually
pins; the loopless interval collapses it, and the same reported value certifies cleanly.

Validated non-circularly in `tests/test_fba_loopless.py`: on a hand-built A→B→C→A cycle the loopless
range collapses to the value derivable from the network by hand (the pure-cycle reaction pinned to
zero, the productive reactions pinned to the boundary flux) where plain FVA reports the inflated
range; on a loop-free chain the two agree to solver tolerance; and end to end, a loop-inflated
abstention becomes a `reproduced` verdict once the loop is removed. It is also checked at real scale
on the E. coli core model, where it strips the textbook FRD7/SUCDi infeasible loop (Orth et al.
2010) — both reactions' spurious ~1000 plain-FVA range collapses to their physiological flux —
while every reaction's loopless interval stays contained in its standard one. And it is
cross-validated against an independent tool: on E. coli core the MILP reproduces COBRApy's
`flux_variability_analysis(loopless=True)` reaction-for-reaction to solver tolerance
(`tests/test_fba_cross_validation.py`, reference in `datasets/constraint_based/cross_validation/`).

## Self-validation

Before the class's verdicts are trusted, the pathway is measured against a real published model
whose result is independently known. [`datasets/constraint_based/e_coli_core.xml`](../datasets/constraint_based/)
is the standard *E. coli* core model; [`tests/test_fba_selfvalidation.py`](../tests/test_fba_selfvalidation.py)
ingests it with `ingest_fbc_sbml`, solves it, and checks the optimum against the textbook maximal
growth rate (0.873922 mmol · gDW⁻¹ · h⁻¹). The expected value lives only in the test assertion —
nothing in the engine encodes it — so this is a genuine reproduction of a known result, and the
full FROG analyses are exercised on a real network rather than only the tiny fixtures. Gene
essentiality is validated the same way: e_coli_core's 69 GPR-annotated reactions span 137 genes,
and `gene_essentiality` recovers its essential-gene set — including the independently known
essential enolase (`b2779`) — computed from the model's own GPR rules.

Beyond the one core model, a [cross-validation set](../datasets/constraint_based/cross_validation/)
checks the ingester on structural variety: three diverse genome-scale models (*H. pylori*, *T.
maritima*, *L. lactis*; 500–750 reactions) whose growth rate the independent COBRApy implementation
computes are reproduced by `ingest_fbc_sbml` + `solve_objective` to six digits — a non-circular
cross-tool check where a stoichiometry-, bound-, or objective-parsing bug would surface. The
[milestone blind run](../datasets/constraint_based/milestone/) folds all four models (the documented
core model plus the three cross-validated ones) into one blind agreement report through the shared
catalog and `run_test_set`: 4/4 agreement with ground truth.

## From a paper to a certificate

The oracle above is the back end. The front end — turning a constraint-based *paper* into a
certified reproduction — is [`reprolith.constraint_based`](../python/reprolith/constraint_based.py),
the FBA counterpart of the PK/PD `certify_model`. It reuses the shared `Dossier` unchanged rather
than reshaping it: the structural elements (stoichiometry, bounds, objective, GPR) live in the
paper's own SBML-fbc file, so a constraint-based dossier **adopts** that validating `ModelArtifact`
and recovers them with `ingest_fbc_sbml` instead of re-encoding an S matrix. The one thing the file
cannot pin down on its own — the **medium** — is recorded as first-class dossier elements, because
it is load-bearing: each stated uptake limit is a `Parameter`, and any unstated exchange bound is a
`GapKind.MEDIUM` gap the validator requires be load-bearing.

- `constraint_based_dossier` / `validate_constraint_based` build and check that shape.
- `certify_constraint_based` adopts the model, applies the recorded medium, solves each
  objective-value claim, and assembles the certificate through the shared builder and scope flag. A
  `shortfalls` mapping supplies the root cause a failing claim requires, so the path emits an honest
  *not-reproduced* certificate, not only a reproduced one.

The worked example in [`datasets/constraint_based/worked_example/`](../datasets/constraint_based/worked_example/)
walks it end to end on E. coli core: the dossier reproduces the known growth rate cleanly, and the
same network run anaerobically drops to 0.211663 — a concrete demonstration of why the medium is
load-bearing.

## Failure modes

A `partial` or `failed` FBA verdict carries a first-class constraint-based root cause, not a
borrowed PK/PD one. The maintained set (`reprolith.FailureMode`) adds the recurring reasons
constraint-based reproductions fail — an unspecified or ambiguous medium/exchange bound, an
ambiguous biomass/objective definition, missing or inconsistent gene–reaction associations, and
alternate-optima flux ambiguity — with LP solver sensitivity named by the shared
`ENGINE_SENSITIVITY`. A failure fitting none of them is recorded as `UNCATEGORIZED`, which flags
the catalog to be extended rather than silently misclassifying.

## Example

```python
from reprolith import flux_variability, judge_flux

# S: rows = metabolites, columns = reactions. v_in -> A -> {r1, r2} -> B -> v_out.
stoich = [[1.0, -1.0, -1.0, 0.0],   # A
          [0.0,  1.0,  1.0, -1.0]]  # B
objective = [0.0, 0.0, 0.0, 1.0]    # maximize the outflow
lower = [0.0, 0.0, 0.0, 0.0]
upper = [10.0, None, None, None]

intervals = flux_variability(stoich, objective, lower, upper)
# intervals[1] == (0.0, 10.0): the two parallel routes split the optimum freely.

judge_flux(
    claim_id="r1", quantity="parallel-route flux", source_location="Table 2",
    reported=5.0, interval=intervals[1],
).verdict            # -> NOT_EVALUABLE: consistent, but the model doesn't pin it.
```

The resulting `ClaimAssessment` feeds `build_certificate` exactly like a PK/PD assessment, so an
FBA reproduction produces the same scope-flagged, honestly-qualified certificate as the rest of
the engine.
