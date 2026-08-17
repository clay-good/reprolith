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

## Self-validation

Because a paper's reported curve usually lives in a figure (not text-extractable here), the class is
validated non-circularly against an **independent simulator**: the
[cross-validation set](../datasets/kinetic/) holds curated BioModels models spanning six distinct
dynamic regimes, each with a reference curve computed by libRoadRunner (CVODE), a simulator sharing
no code with COPASI. Reprolith reproduces every reference (`tests/test_kinetic_cross_validation.py`),
and the [milestone blind run](../datasets/kinetic/milestone/) folds them into one agreement report
through the shared catalog: 6/6 agreement.

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
