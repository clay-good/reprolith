# Worked example — constraint-based (FBA) reproduction

A real, end-to-end Reprolith certification of a constraint-based metabolic model, start to
finish, on a real published result. It is the constraint-based counterpart of the
[metformin PK/PD worked example](../../worked_examples/README.md): the same
dossier → reconstruction → oracle → certificate pipeline, driven by a different oracle
(linear programming, not curve-matching), producing an honest verdict with an inescapable scope
flag.

## The model and the claim

- **Model:** the standard *E. coli* core reconstruction, [`e_coli_core.xml`](../e_coli_core.xml)
  (BiGG Models, SBML L3 fbc v2; academic and non-profit use only — see
[`datasets/THIRD-PARTY-NOTICES.md`](../../THIRD-PARTY-NOTICES.md)).
- **Origin:** Orth, Fleming & Palsson (2010), *EcoSal Plus*
  ([doi:10.1128/ecosalplus.10.2.1](https://doi.org/10.1128/ecosalplus.10.2.1)).
- **Claim checked** (reference value from the literature, not from re-running the model, so the
  check is not circular): maximal **aerobic growth rate 0.873922 mmol · gDW⁻¹ · h⁻¹** on
  **glucose minimal medium** (glucose uptake ≤ 10 mmol/gDW/h, oxygen unlimited), maximizing the
  biomass reaction `R_BIOMASS_Ecoli_core_w_GAM`.

## The dossier shape

A constraint-based dossier ([`dossier.json`](dossier.json)) reuses the shared dossier unchanged.
The structural elements the outcome depends on — reaction stoichiometry, flux bounds, the
objective, and the gene–reaction associations — live in the paper's own SBML-fbc file, so the
dossier **adopts** that file as a validating `ModelArtifact` and recovers them with
`ingest_fbc_sbml` rather than re-encoding an S matrix by hand.

The one thing the file cannot pin down on its own is the **medium**, and the medium is
load-bearing: it is recorded as first-class dossier elements — here the glucose uptake limit and
the aerobic (oxygen) condition, each citing its source. Had the medium been left unstated, it
would be a `medium` **gap** marked load-bearing, because an unstated medium silently changes the
answer.

## What Reprolith found

Solved as a linear program under the recorded medium:

- **Reproduced cleanly.** Optimal growth **0.873922** vs the reported **0.873922** — a relative
  error of ~5 × 10⁻⁷, well inside the class-default tolerance, with no Reprolith assumption
  needed. The overall verdict is `reproduced` (see [`certificate.txt`](certificate.txt)).

The medium is not a formality. Reproduced under the same model but **anaerobic** (oxygen uptake
0), the maximal growth rate falls to **0.211663** — a 76% drop. That is precisely why the medium
is recorded as load-bearing: the same network reproduces a very different number under a different,
but equally plausible-if-unstated, medium.

## Files

| File | What it is |
|---|---|
| [`dossier.json`](dossier.json) | The constraint-based dossier: adopted model, medium, and the objective-value claim. |
| [`certificate.txt`](certificate.txt) | The rendered reproduction certificate. |
| [`../e_coli_core.xml`](../e_coli_core.xml) | The adopted SBML-fbc model (shared with the self-validation entry). |

## Reproduce it

```bash
pip install -e ".[engine,fba]"
pytest tests/test_fba_dossier.py -q
```
