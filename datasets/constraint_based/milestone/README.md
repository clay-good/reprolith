# Constraint-based milestone result — the walkable blind run

The constraint-based (FBA) class's self-validation run, assembled so a stranger can follow it end
to end: the labelled entry, its blind certificate, and the agreement report — the FBA counterpart
of the [PK/PD bootstrap milestone](../../milestone/README.md). Regenerate it from the repository
alone (no network, needs the `engine` and `fba` extras) with:

```
python scripts/run_fba_milestone.py
```

## The result in one line

**Every constraint-based entry was certified blind and agrees with its label: 8/8.**

| Entry | Organism | Label source | Verdict | Agreement |
|---|---|---|---|---|
| `e_coli_core` | *E. coli* K-12 | documented growth rate 0.873922 (Orth 2010), plus COBRApy's essential sets, one flux and one flux range | `reproduced` | ✓ |
| `iIT341` | *H. pylori* 26695 | COBRApy reference growth 0.692813 | `reproduced` | ✓ |
| `iLJ478` | *T. maritima* MSB8 | COBRApy reference growth 0.228407 | `reproduced` | ✓ |
| `iNF517` | *L. lactis* MG1363 | COBRApy reference growth 0.042635 | `reproduced` | ✓ |
| `iAF1260` | *E. coli* K-12 (2007 reconstruction, 2382 rxns) | COBRApy reference growth 0.736701 | `reproduced` | ✓ |
| `iJO1366` | *E. coli* K-12 (genome-scale, 2583 rxns) | COBRApy reference growth 0.982372 | `reproduced` | ✓ |
| `iMM904` | *S. cerevisiae* S288C (eukaryote) | COBRApy reference growth 0.287866 | `reproduced` | ✓ |
| `iEK1008` | *M. tuberculosis* H37Rv (pathogen) | COBRApy reference growth 0.058174 | `reproduced` | ✓ |

Each label is held on the catalog entry but withheld from the verdict path, which sees only the
dossier and the model. The certificate is produced by solving the model's objective and comparing
the optimum to the labelled reference, so each agreement is a genuine blind match, not a label read
back. The E. coli core label is a documented literature value; the seven genome-scale labels are
the growth rate an independent implementation ([COBRApy](../cross_validation/)) computes for the
distributed model — non-circular in both cases. Every label's exact source is recorded on the
entry.

## The entry that carries every target this class can judge

`e_coli_core` is certified on **four kinds of claim**, which is every reproduction target the class
spec names, and the only entry here that is:

| Claim | Reference | Compared by |
|---|---|---|
| maximal aerobic growth rate | the distributing publication's 0.873922 | relative error |
| the set of essential **genes** (7) | COBRApy's single-gene deletion | exact set match |
| the set of essential **reactions** (18) | COBRApy's single-reaction deletion | exact set match |
| aconitase's flux at the optimum | COBRApy's flux-variability interval, which *pins* it | relative error |
| succinate dehydrogenase's flux **range** | the same interval, which does *not* pin it | its worse-matched bound |

The last two are the same analysis read two ways, and they are on one certificate on purpose:
`R_SUCDi` is one of the two reactions this model does not pin, so a claim reporting a *value* for it
is abstained on — the model permits that number rather than producing it — while a claim reporting
its *range* reproduces, because the range is exactly what the model says.

This certificate also mixes reference kinds — a publication's growth rate beside a tool's deletion
sets — which is why `tests/test_reference_provenance.py` classifies per *claim* and names this one.

## What this demonstrates

- **The class closes its self-validation loop on the shared machinery.** The same catalog
  lifecycle, blind view, `run_test_set`, and agreement report the PK/PD class uses carry the
  constraint-based entry unchanged — the certificate flows through them with no forked driver.
- **The scope is honest.** These eight entries attest to *cross-implementation reproduction on the
  distributed models* (and, for E. coli core, a documented literature value) — not to reproducing
  specific paper-reported numbers behind figures. Scaling further, or adding manuscript-reported
  claims, is a data-gathering step, not an engine one.

## Files

| File | What it is |
|---|---|
| [`agreement_report.json`](agreement_report.json) | Per-entry and aggregate agreement with ground truth. |
| [`certificates/e_coli_core.json`](certificates/) | The blind certificate's full content (verdict, scope, and its five claims). |
| [`catalog.json`](catalog.json) | The catalog after the run, with the entry advanced to `certified`. |

See also the [worked example](../worked_example/) for the full dossier → certificate walk, and
[`docs/fba-oracle.md`](../../../docs/fba-oracle.md) for the oracle.
