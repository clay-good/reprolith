# The two deferred halves: populations and re-fits

Two of Reprolith's reproduction levels shipped with their **oracle first and their engine later**.
A population figure could be judged but not simulated; a reported parameter estimate could be
judged but not re-derived. In both cases the certificate took the hard half from the caller, and
the caller had to be trusted to have produced it honestly.

Both halves are now built. This page says what they do, what they refuse, and — the part that
matters most for a reproducibility tool — what they cannot yet be pointed at.

## Why the oracle came first

The judging half is dependency-free and deterministic, so it could land, be tested, and be reasoned
about without an engine. The producing half needs a simulator, a sampler, or an optimizer, and each
of those brings a choice that changes the answer. Landing them separately meant the choices could
be made deliberately and written down, instead of being buried in whatever a library happened to
default to.

That is why every paragraph below is about a choice rather than about code.

## Populations: `simulate_population`

A population figure is a median with outer percentiles across a virtual population — how a large
slice of the PK/PD and QSP literature reports its results.

```python
from reprolith import SubjectVariability, simulate_population, PopulationClaim, certify_population

run = simulate_population(
    model_sbml, "C", duration=12.0, steps=12,
    variability=(SubjectVariability(parameter="V", cv=0.3),),
    subjects=500, seed=20260827,
)
claim = PopulationClaim(..., predicted=run.bands, protocol=run.protocol)
```

Three choices decide what an envelope means. All three are stated, and all three travel in the
protocol the certificate carries, because an envelope read without them is a picture rather than a
result.

| Choice | What Reprolith does | Why it matters |
|---|---|---|
| Variability model | `exp(eta)`, `eta ~ Normal(0, omega²)`, `omega = sqrt(ln(1 + cv²))` — median-preserving | The other common convention is mean-preserving, which shifts **every** band by `exp(omega²/2)` — 4.4% at a 30% CV |
| Draws | Seeded uniforms through `NormalDist.inv_cdf` | An explicit inverse CDF, not a sampler whose internal state could change between interpreter versions. Same seed, same population, any machine |
| Percentile | Linearly interpolated between order statistics | Definitions disagree materially at small ensembles: nearest-rank puts P5 of twenty subjects on the minimum |

**Validated against mathematics, not itself.** With a log-normal volume, `ln C(t)` is normal, so
every percentile band of a one-compartment model has a closed form. 500 subjects at 30% CV land
inside 10% of it at every grid point, where the empirical P5's own sampling error is about 3%
(`tests/test_population_simulation.py`).

**Refused rather than run:** a parameter whose variability could not reach the run (undeclared, or
determined by a rule, or shadowed by a kinetic law), a parameter with no stated value to vary
around, two variability specs for one parameter, a percentile of 0 or 100, and an ensemble of one.
The first is the important one — its failure is silent by nature: the ensemble runs, every subject
is identical, the bands come out as one line, and nothing says the variability was discarded.

**Not supported:** correlated variability. Independent draws are not offered as an approximation of
it, because they understate the width of every band whose parameters move together.

## Re-fits: `refit_parameters`

The strongest form of reproducibility is not "the shown curve comes out again" but "the *reported
estimates* come out again."

```python
from reprolith import refit_parameters, EstimationClaim, certify_estimation

result = refit_parameters(
    model_sbml, "C",
    observations=((0.7, 8.69), (1.3, 7.71), (2.9, 5.60), ...),
    start=(("k", 0.5),),
    dataset="Table 3 plasma samples",
)
claim = EstimationClaim(..., recovered=result.value("k"), protocol=result.protocol)
```

A re-fit is sensitive to four things, and an estimate reported without them cannot be repeated —
which is why `EstimationClaim` refuses a claim with no protocol. Running the fit does not exempt it
from stating how:

| Sensitive to | What Reprolith does |
|---|---|
| The objective | Ordinary least squares. Not weighted, not log-transformed — a weighted objective is a modelling choice a manuscript has to state, and inventing one changes the answer |
| The optimizer | Nelder-Mead written here rather than imported: fixed initial simplex, fixed coefficients, no randomness, no dependency whose version could move the fourth decimal |
| The starting values | The caller's, always. A starting point is part of an optimizer's answer for any objective that is not convex |
| The dataset and grid | The observations, and the uniform grid the trajectory is computed on before being interpolated to the observation times |

Parameters are searched on the **log scale**, so a rate or a volume cannot wander negative and the
search is scale-free.

**Validated against mathematics, not itself.** On exact data from a one-compartment model, `ln C` is
exactly linear in `t`, so a closed-form regression gives the rate constant. Started 2.5x away, the
fit lands within `1e-3` of it, and a two-parameter fit recovers both
(`tests/test_estimation_refit.py`).

**Refused rather than reported** — each of these would otherwise publish a fit that did not happen:

| Refused | What would have happened |
|---|---|
| An objective that does not move when the parameters do | Nelder-Mead on a flat landscape shrinks its simplex until the convergence test passes and hands back the caller's own starting values, reporting "converged in N iterations" over a residual that never improved. This was found by auditing the module's own first version |
| A fit that runs out of iterations | An optimizer that stopped early has not produced an estimate |
| A search that walks off the log scale | Used to end in an `OverflowError` naming nothing |
| Fewer observations than parameters | The fit returns whichever of infinitely many answers the optimizer reached first |

A parameter region the engine cannot integrate propagates its error rather than being scored as
infinitely bad. Scoring it is the usual practice and would quietly steer the search away, leaving
no trace that the fit went somewhere the model does not exist.

## What is still missing

Neither capability has yet been pointed at a **paper**. There is no published population figure and
no shipped raw dataset in the corpus, so both are demonstrated against closed-form mathematics
rather than against a published result. That is a genuine validation of the machinery and it is
not a certificate: no row in the [registry](../datasets/registry.html) comes from either path.

The blocker is the same one the rest of the repository names: reading a paper's claims — here, its
reported estimates and its figure's bands — out of a manuscript at scale is not built. See
[`findings-note.md`](findings-note.md).

The inline lint surface (`lint_distribution`, `lint_estimation`) still takes the produced values
rather than producing them, and deliberately so: it is dependency-free by contract, dispatchable
over MCP with no engine present. What changed is that a caller now has an honest way to produce
them.
