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
[cross-validation set](../datasets/kinetic/) holds curated BioModels models spanning three network
types, each with a reference curve computed by libRoadRunner (CVODE), a simulator sharing no code
with COPASI. Reprolith reproduces every reference (`tests/test_kinetic_cross_validation.py`), and the
[milestone blind run](../datasets/kinetic/milestone/) folds them into one agreement report through
the shared catalog: 3/3 agreement.

| Model | Network | Dynamics |
|---|---|---|
| `BIOMD0000000010` | signaling | Kholodenko2000 MAPK cascade (oscillatory) |
| `BIOMD0000000012` | gene-regulatory | Elowitz2000 repressilator (oscillator) |
| `BIOMD0000000051` | metabolic | Chassagnole2002 *E. coli* carbon metabolism |

## Scope and honesty

The cross-validation attests to **cross-implementation reproduction of the shipped models** — two
independent integrators agreeing — not to reproducing a specific paper-reported figure. As with
every Reprolith verdict, the certificate's scope flag states it attests only to computational
reproducibility, never biological correctness or clinical fitness.
