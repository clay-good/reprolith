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

### How many subjects, and why it is not a free parameter

An envelope is percentiles of a *finite* sample: draw the same population twice and the 5th
percentile moves. That movement is not a disagreement with the paper, and until now an envelope of
twenty subjects and one of a thousand were published in the same words and judged in the same 15%
band.

It is measurable with no paper and no engine — draw N subjects from a population whose true
percentiles are known in closed form and compare the sample envelope against the population it came
from. Nothing is wrong with the reconstruction in that comparison, because it is the right
population. How often the worst of the three bands still misses the 15% pass budget
(`tests/test_population_sampling_cost.py`, 400 replicates):

| Between-subject CV | N=20 | N=50 | N=100 | N=250 |
| --- | --- | --- | --- | --- |
| 30% | 47% | 12% | 2% | 0% |
| 50% | 80% | 51% | 24% | 3% |

At twenty subjects and a 30% CV, a reproduction that is right about everything fails about half the
time. An envelope read off a paper's *picture* is judged at 25% instead of 15%, and that widening
buys about a factor of five in ensemble size — 10% rather than 47% at twenty subjects — while
leaving a wide population exactly where it was: at a 50% CV, twenty subjects still miss almost half
the time. The subject count is a term in the verdict, so the run now states its own band's sampling
error in the protocol the certificate carries — `sampling error of the 5th band ~14% of the band at
20 subjects` — from the closed form `percentile_sampling_error`, which agrees with the replicates
within a factor of two and understates the tails at small N. It is published as a scale, never as a
bound, and it is not a refusal: a paper that ran twenty subjects ran twenty subjects, and Reprolith
reports what that costs rather than declining to judge it.

**Refused rather than run:** an ensemble too small to resolve the bands it is asked for — below
thirty subjects the spread is the sampling rather than the population, and a percentile needs about
`100/min(p, 100-p)` subjects before it is a percentile at all rather than the sample's own extreme
wearing a label. The stochastic class already refused on both counts for the same reason, measured
on its own model; the population path published them. Neither can be caught downstream, because
`judge_distribution` receives bare bands and never learns how many subjects made them. If a paper's
*own* population is that small its envelope carries the same noise, and that is a thing to say about
the paper rather than a verdict to compute.

Also refused: a parameter whose variability could not reach the run (undeclared, or
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

### What the data costs, before the optimizer is at fault

A re-fit recovers parameters from *noisy* observations. Fit the same experiment twice with the same
correct model and a perfect optimizer and the estimates move, because the data moved. That floor is
measurable with no paper and no engine — generate observations from known parameters, add assay
noise, recover them by exact least squares, and compare (`tests/test_estimation_noise_floor.py`,
600 replicates, eight points over a day).

| Assay noise (CV) | median error, rate | median error, scale | worse of the two misses the 10% budget |
| --- | --- | --- | --- |
| 5% | 0.6% | 2.2% | 0% |
| 10% | 1.2% | 4.4% | 14% |
| 20% | 2.4% | 8.8% | 45% |

Two things follow. **The asymmetry is large**: the same data that pins the elimination rate to
within 3% leaves the scale — a volume, a dose, a clearance — at nearly four times that. An
estimation verdict says much more about a paper's rate constants than about its volumes, and the
10% tolerance is set by the looser of the two.

And **more data does not rescue a noisy assay**: quadrupling the observations cuts the scale's
error by about a third, not by half, so at a 20% assay CV a flawless re-fit still misses the pass
budget one time in four at twenty points. It is the noise level that governs, which is why the
estimation level carries its own wider default rather than borrowing the scalar's.

This measures the statistical floor any correct optimizer shares — the fit is the closed-form
optimum for the model it generates from — not `refit_parameters`' own optimizer, which
[`tests/test_estimation_refit.py`](../tests/test_estimation_refit.py) checks.

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
