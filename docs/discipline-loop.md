# The discipline loop's written record

Reprolith's failure-mode catalogue and its tolerance defaults are supposed to be *evidence-driven,
not guessed up front*, and every disagreement between a blind verdict and its ground-truth label is
supposed to carry a written explanation. Both are claims about process, and prose in a README
cannot keep them true. This is the machine-checked version.

[`datasets/loop_notes.json`](../datasets/loop_notes.json) holds the notes. Each one names what it
explains, what it rests on, and where to check it — at least one citation quoting the words it is
cited for, so a note that points at the wrong file fails rather than passing on the strength of the
path existing. `tests/test_loop_notes.py` audits the notes against the artifacts — every disagreeing entry in every committed agreement report, every `FailureMode`,
and every default tolerance. A new disagreement with no note, a new failure mode nobody justified,
a note whose subject no longer exists, or a citation that is missing — or that does not contain
what it was cited for — is a gate failure rather than a quiet omission.

## What a note rests on

The honest part is the `basis` field, because most of the catalogue has never fired:

| Basis | Meaning | Count |
|---|---|---|
| `observed` | a blind run produced it; the artifact is committed | the 31 PK/PD disagreements, the exact-match tolerance |
| `measured` | a deliberate measurement set the number | the scalar and curve tolerances, engine sensitivity |
| `spec` | a class spec requires the category, and no run has emitted it yet | every other failure mode, and the tolerances no certified claim has exercised |

Nineteen of the twenty catalogued failure modes are `spec`; the twentieth (engine sensitivity) is
`measured`, and what the measurement showed was its absence. That is the point of keeping the field:
a category that exists because a spec demands it must not read as loop experience it does not have.

## What the 30 disagreements say

Only the PK/PD run disagrees with its labels at all; the other five classes agree everywhere. One
of its thirty-one entries matches — the mouse model, which needed no salt conversion and so carries
no assumption to qualify it.

- **27 abstentions**, all one note, traced to **ingestion**: Reprolith holds no extracted claims
  for these papers, so there was nothing to reproduce and no model was run — the run abstains, and a
  `blocked` verdict can never equal a `reproduced` label. (This said "the shipped artifact carries
  no machine-checkable claim" until a regression audit noticed the code had been corrected and its
  two explanatory documents had not: nothing is fetched or opened on that path.) Recorded as *explained*, not fixed — closing them needs each paper's claims
  read from the manuscript (tasks 2.1–2.3), not a tolerance or oracle change.
- **3 more-careful verdicts** — the three human-dosed metformin models — traced to the **oracle**:
  every claim matched well inside tolerance, but each model's claims rest on a load-bearing
  salt-form assumption, so the overall verdict is `partially-reproduced` against a binary
  `reproduced` label. Recorded as *explained* — the down-grade is the honesty invariant working.
  Every one runs in the **stricter** direction: a withheld pass, never a false one, which is the
  distinction `reprolith self-validation` prints beside the count.

## What the measurements say

Two defaults are fully measured, both from perturbing a shipped reproduction until its published
verdict changed (see [`findings-note.md`](findings-note.md) for the full table):

- **Scalar, numeric — 5% / 15%.** Metformin's dose still reproduces at +8% and −3% and first drops
  to partial at +10%, against an unperturbed agreement of 2.2%.
- **Curve, numeric — 10% / 25%, and the effective budget is the 25%.** The verdict is the stricter
  of the RMSE and a worst-point check at 25% of span, and the worst point binds whenever the error
  concentrates in under about a sixth of the samples. Tightening it to the pass threshold was
  measured and rejected: about half of correct work fails at coarse per-point noise, where the
  present budget produced 0 false failures in 15,000 trials.

Three more are **partly** measured, and the distinction matters: what was measured is the part of
each budget the *method itself* spends before any model, optimizer or paper is at fault. The
tolerances stay declared, because no certified claim has exercised one — but each of these turns an
unqualified "wider, to absorb the extra uncertainty" into a number, and each produced guidance a
practitioner can act on.

- **Digitized figure, curve — 0.20 / 0.40.** Between two read points the reference is a straight line, so
  a *flawless* five-point reading of an oral PK curve misses the curve it was read off by 0.25:
  more than the whole pass budget, with no model involved. At ten points, 0.09; at twenty, 0.025.
  An exponential read off a log axis is recovered exactly at any spacing. Guidance: read about
  twenty points per curve, and more where it bends — which `figure-template` now says up front and
  `figure-check` says when a reading is coarser than that
  (`tests/test_digitization_interpolation_cost.py`). That measurement needed a function whose value
  is known everywhere, which a curator does not have; the same quantity is now estimated **from the
  reading itself** — drop each interior point, rejoin its neighbours, and the residual is the
  curve's own curvature in the units the verdict is in (`interpolation_cost`). It over-states in the
  safe direction, by a factor measured at 1.0x to 3.9x and therefore not corrected for, and it sees
  what the widest gap could not: a straight line or a log-axis exponential costs exactly zero
  however coarsely it is read, a reading that does cost too much is told *where* it bends, and a
  ten-point PK reading — 11% gaps, comfortably under the 20% the old warning fired at — is caught
  spending one and a half times the whole budget. It is charged over the run the claim is judged on
  rather than over the whole file — a reading is required to *cover* the run and so permitted to
  exceed it, and a bend past its end, with the range that bend adds to the scale, is cost nothing is
  judged on; measured, that ran 2.1x to 2.3x in the direction that under-states.
- **Digitized figure, scalar — 0.15 / 0.30.** A scalar has no interpolation, so neither measurement
  above touches it. Its pixel-resolution half is measurable all the same, and it is the half a
  curator can act on: every digitizer maps a click through two calibration points, so a click off by
  a pixel is off by one pixel's worth of the axis. On a **linear** axis that is a constant
  *absolute* error, so what it costs depends on where in the axis the value sits — on a 0-10 axis
  drawn 600 px tall, half a pixel is 0.08% at the peak, 11% of the pass budget at a twentieth of it,
  56% at a hundredth, and the whole budget below 0.56% of the span (1.1% at one pixel, which is what
  a drawn line width costs in practice). On a **log** axis one pixel is a constant *ratio*: three
  decades over the same 600 px cost 0.58% of the value wherever it is read, a twenty-fifth of the
  budget. Guidance: a single value read low on a linear axis is not readable inside this band, and
  the same value on a log axis is (`tests/test_digitization_scalar_cost.py`). The tolerance itself
  stays declared — the digitizer's *calibration* error is the other half and is not computed here;
  it is what the axis-range refusal exists to catch instead. And this is not the curve band: a curve
  is judged against its own range, so one pixel is under half a percent of that budget wherever the
  curve sits.
- **Distributional band — 15% / 35%.** An envelope is percentiles of a finite sample, so drawing the
  *right* population twice moves the 5th percentile. The worst of three bands misses the 15% budget
  47% of the time at twenty subjects and a 30% CV, 12% at fifty, 2% at a hundred, and never in 400
  replicates at 250. Guidance: the subject count is a term in the verdict, and the run now states
  its own band's sampling error in the protocol. Both bands are measured: against the digitized
  band's 25%, twenty subjects miss 10% of the time at a 30% CV and 46% at a 50% one, so the
  widening buys ensemble size and not safety for a wide population
  (`tests/test_population_sampling_cost.py`).
- **The engine itself — measured on the committed corpus, not on a synthetic input.** Every other
  entry here measures a step between the paper and the verdict. This one measures the last step,
  and it was already computed and published — just never expressed in the units the verdict is in.
  Cross-engine corroboration re-runs a certified result under a second independent simulator and
  publishes the normalized distance between the two curves, which is the *same statistic*
  `judge_curve` compares against the pass budget. PK/PD's eighty claims, each re-run at the dose it
  was certified at, agree to 1e-06 — a hundredth of a percent of the 0.10 curve budget, and for
  this class that number is now a **floor** rather than a measurement: below 1e-07 the raw
  distance is the two engines' last places, it moves 13% between consecutive COPASI calls in
  one process, and three measurements of one claim on CI published two different decades with
  every draw already worst-of-two. Sixteen claims previously published 1e-07 and one 1e-08; a
  committed artifact that changes when it is regenerated is worth less than a decade of
  resolution, and the floor can only loosen a bound, never tighten one. Above the floor the
  decade rounding still has boundaries, and that residual risk is measured rather than
  assumed away: across the six kinetic models the smallest headroom between a lifted
  distance and the decade below it is **42.9%**, three times the alternation, with the rest
  from 60% to 84%. It is a guard, so an engine upgrade that moved one toward a boundary
  fails rather than starting to oscillate a committed file. The kinetic
  class's six models agree to 1e-03, one percent of it. So a numeric verdict is a statement about
  the model and not about COPASI, and none of the tolerance is absorbing solver disagreement
  (`tests/test_engine_floor.py`, read off the committed records so an engine upgrade that widened
  the gap fails rather than passing quietly). Two more classes have since acquired one, and both
  are measured in the units their own verdicts are in rather than in a curve distance: the eight
  constraint-based models agree with COBRApy on the optimal objective value — floored at 1e-08,
  because below that the digits are the machine's BLAS rather than the two implementations, which
  CI proved by producing 4e-11 where this machine produced 1e-13 — and all nine logical networks
  agree with CANA and with an independent SAT solver *exactly*, which is the only agreement an
  attractor set or a fixed-point set admits.

  The stochastic class has one now, and it is the entry that shows why this table needs the
  `basis` field. This paragraph used to say that class had no second registered engine and that
  what such a comparison *would* report is different in kind — "two Gillespie ensembles agree only
  up to Monte Carlo error." The second half was right and the first was never checked:
  libRoadRunner ships a Gillespie integrator and was already pinned here. Measured, the three
  certified networks agree at **1.9, 1.6 and 1.0 combined standard errors** against a criterion of
  three — and the number that makes those mean anything is the one beside them, the bias each
  comparison could *not* have seen: **6.5%, 5.2% and 1.8%** of the mean. The first is wider than
  the 5% the class's own scalar verdict passes at, so on that model the corroboration is weaker
  than the verdict it stands beside, and it says so rather than reading as a confirmation. That is
  the whole difference between this and the other four classes: their agreements are three to
  eight orders below the budget, and a pass there needs no caveat. Guidance: an ensemble
  corroboration is worth what its trajectory count buys, and 400 trajectories at a Poisson mean of
  10 buys less than the verdict needs (`tests/test_stochastic_corroboration.py`). The published
  numbers survive a change of machine *and* of engine build, which for a Monte Carlo statistic is
  not a given: they were measured under libRoadRunner 2.7.0 and CI reproduces every standard error
  and every resolution to the last digit under 2.10.0.

  The spatial class has one too now, and it makes the same correction twice: this paragraph also
  said no installed implementation but this one answers *its* question, and scipy — installed here
  since the constraint-based class needed a linear program — integrates a method-of-lines diffusion
  system under LSODA. All six classes are corroborated. Measured, the three certified profiles
  agree to **1e-03**, the same 1% of the curve budget the kinetic class spends.

  That number needs its own guard against being read as a distance from the truth, and this is the
  entry where the distinction is sharpest. LSODA integrates the *semi-discrete* system essentially
  exactly, so what is measured is what the fixed-step explicit stepper costs in time
  discretization — first order in `dt`, confirmed by halving it. Against the continuum solution the
  explicit scheme does **better**: 2.0e-05 from the closed-form Gaussian, six times closer than the
  two engines are to each other, because central differencing and forward Euler have truncation
  errors of opposite sign that cancel exactly at a diffusion number of 1/6 and nearly so at the 0.2
  these run at. Guidance: a cross-engine distance says two discretizations differ; only the
  certificate's own discrepancy says how near the answer the profile is, and on this class those
  two numbers point opposite ways. What the pair does not separate at all is the spatial
  discretization — both sides take second-order central differences with a mirrored boundary — and
  that limit is asserted rather than only written down
  (`tests/test_spatial_corroboration.py`, `tests/test_reference_provenance.py`).
- **Stochastic mean — 5% / 15%, and the ensemble is the cost.** The number judged is the mean of an
  ensemble Reprolith drew, so drawing the *right* model twice moves it. The class already refuses to
  publish a verdict when the standard error of that mean is more than half the pass threshold, and
  what that rule buys is one number for every model, because both sides of it scale with the
  reported mean: on the boundary the pass band is exactly two standard errors wide either side, and
  a correct ensemble lands outside it **4.6%** of the time — measured at 4.0% over 2000 drawn
  ensembles, and about half of those ensembles abstain rather than publishing at all, since the
  sample variance straddles the boundary. Guidance: the three committed entries sit at **3.2, 4.0
  and 12.2** standard errors, so each is published wrongly less than once in three hundred, and the
  binomial one has four times the headroom of a Poisson of the same mean at the same 400
  trajectories. The trajectory counts are read out of the committed certificates, so an ensemble
  that shrinks is caught here (`tests/test_ssa_ensemble_cost.py`).
- **Estimation level — 10% / 25%.** A re-fit recovers parameters from noisy data: at a 20% assay
  CV, the median error is 2.4% on a rate and 8.8% on a scale, and the worse of the two misses the
  pass budget 45% of the time — with an exact optimizer and the true model. Quadrupling the data
  cuts that by a third, not a half. Guidance: an estimation verdict says much more about a paper's
  rate constants than about its volumes (`tests/test_estimation_noise_floor.py`).

Read the record with any JSON reader; it is data, not a rendering of this page.

## Checking that the checks fail

A test that passes tells you nothing about whether it would fail. `scripts/mutation_check.py` runs
the other direction: it removes one guard at a time from a *copy* of the package and asserts the
named tests go red.

```bash
python scripts/mutation_check.py
```

Every entry is a defect this repository has already been wrong about once — a term silently
dropped, a published schema nobody enforced, an attribute SBML makes inert read as a value — so the
list doubles as the record of what has bitten. It is not in CI: it runs the suite once per
mutation, and it is a deliberate pass, not a per-push gate.

Which modules it covers is itself worth looking at. Counting the guards by module found the two
honesty invariants this repository states first — the overall-verdict rule and the fixed scope
statement — with none at all, and adding one to each found a **survivor**: the refusal that stops a
scope being *reworded* (as against emptied) could be deleted with the entire suite still green. Not
emptiable was never the whole invariant — a scope reading "clinically validated" is worse than a
missing one, and it travels through the badge, the registry, the human render and the query — and
only the load path had ever been tested for it. It is held now.

It fails two ways, and the second is the one worth having. A **surviving** mutation means the guard
has no test, or the test never reaches the case that makes it load-bearing — which is how the
manuscript check's suppression of a model-computed parameter was found passing with its branch
deleted, because the test never gave the document a value to run. A **stale** anchor means the code
moved and the list did not; that is reported as a failure rather than skipped, because a checker
that quietly counts fewer things than it did last week is precisely the defect it exists to catch.
