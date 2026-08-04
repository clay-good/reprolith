# Constraint-based cross-validation set

A small set of diverse, real, published genome-scale metabolic models used to check that
Reprolith's constraint-based ingester and solver reproduce the result an **independent**
implementation computes — a non-circular reproduction on far more structural variety than the
single [E. coli core self-validation](../README.md) model.

## What it checks

For each model, [`reference_growth.json`](reference_growth.json) records the maximal growth rate
the community-standard **COBRApy** computes on the model's distributed medium. The reference comes
from a *different* implementation, so Reprolith matching it is a genuine cross-tool reproduction:
[`tests/test_fba_cross_validation.py`](../../../tests/test_fba_cross_validation.py) ingests each
model with `ingest_fbc_sbml`, solves it, and asserts the optimum matches the committed reference.
A stoichiometry-, bound-, or objective-parsing bug in the ingester would surface here as a
disagreement that the single core model could not reveal.

## The models

| Model | Organism | Reactions | Metabolites | COBRApy reference growth |
|---|---|---|---|---|
| `iIT341` | *Helicobacter pylori* 26695 | 554 | 485 | 0.692813 |
| `iLJ478` | *Thermotoga maritima* MSB8 | 652 | 570 | 0.228407 |
| `iNF517` | *Lactococcus lactis* cremoris MG1363 | 754 | 650 | 0.042635 |

All three are from [BiGG Models](http://bigg.ucsd.edu/) (SBML L3 fbc), stored gzipped. The
reference values were generated once with COBRApy and committed; the test itself needs only the
`engine` and `fba` extras, not COBRApy.

## Essentiality cross-check

[`e_coli_core_essentiality.json`](e_coli_core_essentiality.json) records the essential-gene and
essential-reaction sets COBRApy's `single_gene_deletion` / `single_reaction_deletion` find for the
E. coli core model. Reprolith's `gene_essentiality` (with its GPR AND/OR logic) and
`reaction_essentiality` reproduce both sets exactly (7 genes, 18 reactions) — an independent
cross-tool check of the deletion analyses, not a self-asserted count.

[`e_coli_core_fva.json`](e_coli_core_fva.json) does the same for the third FROG component: the
flux-variability interval of every reaction at the optimum, from COBRApy's
`flux_variability_analysis`, which Reprolith's `flux_variability` reproduces. Together the two
files cross-check all three FROG components — objective (growth), variability, and deletion —
against the standard tool.

## Provenance and honesty

The reference is an independent tool's computation on the *distributed* model, not a value read
from a manuscript figure — so it is reproducible and non-circular, but it attests to
**cross-implementation agreement on the shipped model**, not to reproducing a specific
paper-reported number. Each model's source publication is cited in `reference_growth.json`.
