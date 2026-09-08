# The generic-kinetic (systems-biology ODE) model class

Reprolith's third model class is **generic kinetic models** — biochemical reaction networks
(signaling, metabolic, gene-regulatory) whose reproducible result is a species time-course. It is
the near neighbour of the PK/PD class: both are ODE models judged by curve reproduction, so this
class **reuses the PK/PD curve oracle unchanged** and specializes only in the breadth of networks it
covers. Passing it shows the time-course contract is not PK/PD-specific.

## What it reuses

- **Simulation** — the same pinned COPASI engine (`reprolith.simulate`), behind the `engine` extra.
- **Oracle** — the same `judge_curve` (normalized-distance) comparison and class-default tolerances.
- **Certification** — `certify_curves` runs each curve claim under the pin and assembles the shared,
  scope-flagged certificate, exactly as `certify_model` does for scalar claims. A curve claim
  (`CurveClaim`) is the natural claim shape here: the whole trajectory, not a single metric.
- **Catalog, blind run, agreement** — the same `Catalog`, `run_test_set`, and agreement report the
  other classes use; a kinetic entry is just `ModelClass.KINETIC`.

## The period, and why a curve is the wrong comparison for a limit cycle

Five of the six models in this class's milestone oscillate — a MAPK cascade, the repressilator, a
cell-cycle model, a circadian clock, coupled calcium oscillators — and for most of this class's life
the only thing it could certify about any of them was the **curve**. That is the one comparison a
limit cycle punishes. A curve distance is dominated by *phase*, and phase error accumulates with
every cycle, so a model that reproduces the biology exactly while drifting one percent in period
reads as a total failure.

Measured on this repository's own committed data: the repressilator's reference run spans about 75
cycles, and stretching its clock by **1%** — the same trajectory, every peak height and every shape
identical — moves the curve distance to **0.395 against a 0.10 pass line**, four times over. No
tolerance can tell that from a model that is simply wrong. Which is exactly why these papers report
a period and an amplitude rather than a picture.

So a claim can now state `metric="period"` or `metric="peak_to_trough"`, and the milestone publishes
both for the Drosophila circadian clock, against the values read off **libRoadRunner's** own
reference trajectory. Four decisions are what make them measurements rather than numbers:

- **Mean crossings, not peaks.** Every ripple near a maximum is a local maximum; a mean crossing is
  one level for the whole window. The crossing time is *interpolated* between the two samples that
  straddle it, which is why a period does not inherit the grid quantization that a time-to-peak
  does — eight samples per cycle still reads a sine's period to a tenth of a percent.
- **Hysteresis at the crossing.** A curve passing through its own mean with any noise on it crosses
  that level several times in a row, and counted naively each of those opens a new cycle — which
  does not make the period slightly wrong, it divides it. A counted cycle has to fall clearly below
  the mean first (5% of the window's own peak-to-trough), a margin far below any real oscillation's
  shape: all five oscillators here read the same period with it as without.
- **The window is honoured**, because "after transients" is how a source states which part of the
  run its period was measured over, and a period averaged across the approach to the limit cycle
  answers a different question.
- **Two ways to abstain.** A run that completes no cycle has no period — this class's non-oscillating
  metabolic model is the real case — and a period the *grid* has not settled is caught by the same
  convergence check every grid-dependent metric passes. That check earned its keep immediately: the
  cell-cycle model's peak-to-trough moves 8.7% between 200 and 400 samples, so its spike height is a
  property of the sampling and no verdict is published for it.

`peak_to_trough` is named for what it computes rather than "amplitude", because the field spells
that both ways — peak-to-trough and half of it — and a claim judged under the wrong convention is
out by exactly two.

## Self-validation

Because a paper's reported curve usually lives in a figure (not text-extractable here), the class is
validated non-circularly against an **independent simulator**: the
[cross-validation set](../datasets/kinetic/) holds curated BioModels models spanning six distinct
dynamic regimes, each with a reference curve computed by libRoadRunner (CVODE), a simulator sharing
no code with COPASI. Reprolith reproduces every reference (`tests/test_kinetic_cross_validation.py`),
and the [milestone blind run](../datasets/kinetic/milestone/) folds them into one agreement report
through the shared catalog: 7/7 agreement — the six curves, and the circadian clock's period and
peak-to-trough as a seventh entry.

| Model | Network | Dynamics |
|---|---|---|
| `BIOMD0000000010` | signaling | Kholodenko2000 MAPK cascade (oscillatory) |
| `BIOMD0000000012` | gene-regulatory | Elowitz2000 repressilator (oscillator) |
| `BIOMD0000000051` | metabolic | Chassagnole2002 *E. coli* carbon metabolism |
| `BIOMD0000000005` | cell-cycle | Tyson1991 cdc2/cyclin oscillator |
| `BIOMD0000000021` | circadian | Leloup1999 *Drosophila* PER/TIM clock |
| `BIOMD0000000058` | calcium | Bindschadler2001 coupled Ca²⁺ oscillators |

## Cross-engine corroboration

Because two independent integrators are already in play, the class also exercises the
`simulation-oracle` **engine-independence** requirement: `reprolith.corroborate_curve` runs a
species curve under both the pinned COPASI engine and libRoadRunner (CVODE) and reports whether the
verdict is *engine-independent* (the trajectories agree within tolerance) or *engine-sensitive*
(they diverge). All six cross-validation models are engine-independent
(`tests/test_corroboration.py`), so no kinetic verdict here rests on a single solver's quirk.
Needs the `engine` and `corroborate` extras.

Read it as **one measurement stated twice, not two independent confirmations**. The reference
curve each certificate is judged against *is* a libRoadRunner trajectory
(`scripts/regenerate_kinetic_references.py`), so the certified comparison is already COPASI
against libRoadRunner. Corroboration then measures the same two engines again, at a tighter
tolerance (2% rather than the class default 10%) — a stricter restatement, not a second signal.
Corroboration adds genuinely new information only where the reference comes from the paper rather
than from the corroborating engine.

Read it also as a **result about these six models, not a gate on the certificates**. The milestone
script writes its certificates first and runs corroboration afterwards into a separate
`corroboration.json`; a divergence would be reported there, but it does not currently downgrade a
verdict, add a `ClaimAssessment`, or flag `ENGINE_SENSITIVITY` on the certificate. Binding the two
is open work. What corroboration does *not* do is fail open: a missing second engine raises
`EngineUnavailable` and misaligned grids raise, so an absent engine can never read as agreement.

## Scope and honesty

The cross-validation attests to **cross-implementation reproduction of the shipped models** — two
independent integrators agreeing — not to reproducing a specific paper-reported figure. As with
every Reprolith verdict, the certificate's scope flag states it attests only to computational
reproducibility, never biological correctness or clinical fitness.
