# Generic-kinetic (systems-biology ODE) model class

Reprolith's third model class: **generic kinetic models** — biochemical reaction networks whose
reproducible result is a species time-course, checked with the *same* curve oracle as the PK/PD
class. Where PK/PD models drug concentration in compartments, this class covers signaling,
metabolic, and gene-regulatory dynamics. The point is generality: if the curve oracle reproduces
systems-biology models unchanged, the contract is not PK/PD-specific.

## Cross-validation set

The `simulate` + curve-oracle reuse is validated non-circularly against an **independent
simulator**. [`cross_validation.json`](cross_validation.json) lists curated BioModels kinetic models
spanning six distinct dynamic regimes; for each, it stores the species time-course computed by
**libRoadRunner** (CVODE) — a simulator that shares no code with the COPASI engine Reprolith runs.

[`tests/test_kinetic_cross_validation.py`](../../tests/test_kinetic_cross_validation.py) simulates
each model under Reprolith's pinned COPASI engine and confirms the shared `judge_curve` oracle
returns a `reproduced` verdict against that reference (and a pointwise trajectory match). Two
independent ODE integrators agreeing across an oscillating or metabolic trajectory is a genuine
cross-tool reproduction, not COPASI agreeing with itself.

| Model | Network | Dynamics |
|---|---|---|
| `BIOMD0000000010` | signaling | Kholodenko2000 MAPK cascade (oscillatory) |
| `BIOMD0000000012` | gene-regulatory | Elowitz2000 repressilator (oscillator) |
| `BIOMD0000000051` | metabolic | Chassagnole2002 *E. coli* carbon metabolism |
| `BIOMD0000000005` | cell-cycle | Tyson1991 cdc2/cyclin oscillator |
| `BIOMD0000000021` | circadian | Leloup1999 *Drosophila* PER/TIM clock |
| `BIOMD0000000058` | calcium-signaling | Bindschadler2001 coupled Ca²⁺ oscillators |

## Provenance

Each model is a curated BioModels entry; its source publication is cited in
[`cross_validation.json`](cross_validation.json). The reference curves are regenerable from the
committed models with
[`scripts/regenerate_kinetic_references.py`](../../scripts/regenerate_kinetic_references.py) (needs
libRoadRunner — a dev-time reference generator, not a Reprolith dependency), so the ground truth is
auditable, not a set of magic arrays.
