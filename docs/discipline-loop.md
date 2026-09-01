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

## What the 31 disagreements say

Only the PK/PD run disagrees with its labels at all; the other five classes agree everywhere.

- **30 abstentions**, all one note, traced to **ingestion**: Reprolith holds no extracted claims
  for these papers, so there was nothing to reproduce and no model was run — the run abstains, and a
  `blocked` verdict can never equal a `reproduced` label. (This said "the shipped artifact carries
  no machine-checkable claim" until a regression audit noticed the code had been corrected and its
  two explanatory documents had not: nothing is fetched or opened on that path.) Recorded as *explained*, not fixed — closing them needs each paper's claims
  read from the manuscript (tasks 2.1–2.3), not a tolerance or oracle change.
- **1 more-careful verdict** (metformin), traced to the **oracle**: both claims matched well inside
  tolerance, but one rests on a load-bearing salt-form assumption, so the overall verdict is
  `partially-reproduced` against a binary `reproduced` label. Recorded as *explained* — the
  down-grade is the honesty invariant working.

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
  judged on; measured, that ran 2.1x to 2.3x in the direction that under-states. The *scalar*
  digitized band is untouched by
  this: one value read off a picture is limited by the digitizer's calibration and the plot's pixel
  resolution, not by anything computed here, so it stays declared rather than borrowing a number
  measured for something else.
- **Distributional band — 15% / 35%.** An envelope is percentiles of a finite sample, so drawing the
  *right* population twice moves the 5th percentile. The worst of three bands misses the 15% budget
  47% of the time at twenty subjects and a 30% CV, 12% at fifty, 2% at a hundred, and never in 400
  replicates at 250. Guidance: the subject count is a term in the verdict, and the run now states
  its own band's sampling error in the protocol. Both bands are measured: against the digitized
  band's 25%, twenty subjects miss 10% of the time at a 30% CV and 46% at a 50% one, so the
  widening buys ensemble size and not safety for a wide population
  (`tests/test_population_sampling_cost.py`).
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

It fails two ways, and the second is the one worth having. A **surviving** mutation means the guard
has no test, or the test never reaches the case that makes it load-bearing — which is how the
manuscript check's suppression of a model-computed parameter was found passing with its branch
deleted, because the test never gave the document a value to run. A **stale** anchor means the code
moved and the list did not; that is reported as a failure rather than skipped, because a checker
that quietly counts fewer things than it did last week is precisely the defect it exists to catch.
