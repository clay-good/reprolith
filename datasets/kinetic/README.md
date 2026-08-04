# Generic-kinetic (systems-biology ODE) model class

Reprolith's third model class: **generic kinetic models** — biochemical reaction networks whose
reproducible result is a species time-course, checked with the *same* curve oracle as the PK/PD
class. Where PK/PD models drug concentration in compartments, this class covers signaling,
metabolic, and gene-regulatory dynamics. The point is generality: if the curve oracle reproduces a
systems-biology model unchanged, the contract is not PK/PD-specific.

## Cross-validation foundation

`ingest`/`simulate`/curve-oracle reuse is validated non-circularly against an **independent
simulator**. [`BIOMD0000000010.xml`](BIOMD0000000010.xml) is the curated Kholodenko2000 MAPK
cascade (BioModels), an oscillating signaling network.
[`mapk_reference_curve.json`](mapk_reference_curve.json) holds its `MAPK_PP` time-course computed by
**libRoadRunner** (CVODE) — a simulator that shares no code with the COPASI engine Reprolith runs.

[`tests/test_kinetic_cross_validation.py`](../../tests/test_kinetic_cross_validation.py) simulates
the model under Reprolith's pinned COPASI engine and checks the trajectory against that reference,
and confirms the shared `judge_curve` oracle returns a `reproduced` verdict. Two independent ODE
integrators agreeing on an oscillating trajectory is a genuine cross-tool reproduction, not COPASI
agreeing with itself.

| Model | Network | Species | Reactions | Reference simulator |
|---|---|---|---|---|
| `BIOMD0000000010` | Kholodenko2000 MAPK cascade (oscillatory) | 8 | 10 | libRoadRunner (CVODE) |

## Provenance

The model is a curated BioModels entry (Kholodenko 2000, *Eur J Biochem*,
doi:10.1046/j.1432-1327.2000.01197.x). The reference curve is regenerable from the committed model
with [`scripts/regenerate_kinetic_references.py`](../../scripts/regenerate_kinetic_references.py)
(needs libRoadRunner — a dev-time reference generator, not a Reprolith dependency), so the ground
truth is auditable, not a magic array.
