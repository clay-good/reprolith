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
| `iEK1008` | *Mycobacterium tuberculosis* H37Rv | 1226 | 998 | 0.058174 |
| `iMM904` | *Saccharomyces cerevisiae* S288C (eukaryote) | 1577 | 1226 | 0.287866 |
| `iAF1260` | *E. coli* K-12 MG1655 (2007 reconstruction) | 2382 | 1668 | 0.736701 |
| `iJO1366` | *E. coli* K-12 MG1655 (genome-scale) | 2583 | 1805 | 0.982372 |

All are from [BiGG Models](http://bigg.ucsd.edu/) (SBML L3 fbc), stored gzipped. The set spans
clades on purpose: a gastric pathogen (*H. pylori*), a hyperthermophile, a lactic-acid bacterium,
an actinobacterial pathogen (*M. tuberculosis*), a **eukaryote** (*S. cerevisiae*, with
compartmentalized metabolism), and two independent *E. coli* reconstructions of different vintages
(`iAF1260` 2007, `iJO1366` 2011) — so a parsing assumption that holds only for one cell type or one
reconstruction style surfaces as a disagreement. `iJO1366` — the canonical full *E. coli*
reconstruction, 27× the core model — stress-tests the ingester at true genome scale. The reference
values were generated once with COBRApy and committed; the test itself needs only the `engine` and
`fba` extras, not COBRApy.

## Essentiality cross-check

[`e_coli_core_essentiality.json`](e_coli_core_essentiality.json) records the essential-gene and
essential-reaction sets COBRApy's `single_gene_deletion` / `single_reaction_deletion` find for the
E. coli core model. Reprolith's `gene_essentiality` (with its GPR AND/OR logic) and
`reaction_essentiality` reproduce both sets exactly (7 genes, 18 reactions) — an independent
cross-tool check of the deletion analyses, not a self-asserted count.

[`e_coli_core_synthetic_lethal.json`](e_coli_core_synthetic_lethal.json) records the
synthetic-lethal reaction pairs COBRApy's `double_reaction_deletion` finds for the E. coli core
model — pairs viable to delete singly but lethal together. Reprolith's `synthetic_lethal_reactions`
reproduces the whole set exactly (all 111 pairs), a cross-tool check of the double-deletion
(epistasis) analysis that single deletion is blind to: redundant pathways that back each other up
look dispensable one at a time and only the pair reveals the dependency.

[`e_coli_core_synthetic_lethal_genes.json`](e_coli_core_synthetic_lethal_genes.json) is the
gene-level counterpart, from COBRApy's `double_gene_deletion`: the synthetic-lethal *gene* pairs —
viable to delete singly but lethal together through the model's GPR rules. Reprolith's
`synthetic_lethal_genes` reproduces the whole set exactly (all 53 pairs), the classic
synthetic-lethality screen that underlies combination-therapy target discovery.

[`e_coli_core_fva.json`](e_coli_core_fva.json) does the same for the third FROG component: the
flux-variability interval of every reaction at the optimum, from COBRApy's
`flux_variability_analysis`, which Reprolith's `flux_variability` reproduces. Together the two
files cross-check all three FROG components — objective (growth), variability, and deletion —
against the standard tool.

[`iIT341_fva.json`](iIT341_fva.json) repeats the flux-variability cross-check on a model 6× the
core's size and a different organism (*H. pylori*, 554 reactions), so the variability code is shown
to generalize beyond one small toy network, not just to reproduce a single stoichiometry.

## Provenance and honesty

The reference is an independent tool's computation on the *distributed* model, not a value read
from a manuscript figure — so it is reproducible and non-circular, but it attests to
**cross-implementation agreement on the shipped model**, not to reproducing a specific
paper-reported number. Each model's source publication is cited in `reference_growth.json`.
