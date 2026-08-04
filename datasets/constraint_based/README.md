# Constraint-based self-validation model

## `e_coli_core.xml`

The standard *Escherichia coli* core metabolic model — a small (72 metabolites, 95 reactions),
widely-used constraint-based model whose maximal aerobic growth rate on glucose minimal medium is
an independently-established, textbook-known result. It is Reprolith's ground-truth entry for the
constraint-based class: a real published model with a known optimum, not a synthetic fixture.

| Field | Value |
|---|---|
| Source | BiGG Models — <http://bigg.ucsd.edu/models/e_coli_core> (`static/models/e_coli_core.xml`) |
| Origin | Orth, Fleming & Palsson (2010), *EcoSal Plus* — the core *E. coli* reconstruction |
| Format | SBML Level 3 Version 1, fbc version 2 (`strict="true"`) |
| Objective | `R_BIOMASS_Ecoli_core_w_GAM` (maximize) |
| **Known maximal growth rate** | **0.873922** mmol · gDW⁻¹ · h⁻¹ (default medium, as distributed) |

## Why it is here

The constraint-based-class spec requires the pathway be measured against entries whose
reproducibility is independently known before its verdicts are trusted. This model's optimum is
such a known value. [`tests/test_fba_selfvalidation.py`](../../tests/test_fba_selfvalidation.py)
ingests the shipped SBML with `ingest_fbc_sbml`, solves it with `solve_objective`, and checks the
result against the published growth rate — a real reproduction of a real result. The check reads
the model as-distributed and takes the objective from the file itself, so it is blind in the sense
that matters: nothing in Reprolith's code encodes the expected optimum except the assertion.

Reproduce it directly:

```bash
pip install -e ".[engine,fba]"
python -c "from pathlib import Path; from reprolith import ingest_fbc_sbml, solve_objective as s; \
m = ingest_fbc_sbml(Path('datasets/constraint_based/e_coli_core.xml').read_text(encoding='utf-8')); \
print(s(m.stoichiometry, m.objective, m.lower, m.upper))"
# -> 0.8739215069684304
```
