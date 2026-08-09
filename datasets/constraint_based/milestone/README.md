# Constraint-based milestone result — the walkable blind run

The constraint-based (FBA) class's self-validation run, assembled so a stranger can follow it end
to end: the labelled entry, its blind certificate, and the agreement report — the FBA counterpart
of the [PK/PD bootstrap milestone](../../milestone/README.md). Regenerate it from the repository
alone (no network, needs the `engine` and `fba` extras) with:

```
python scripts/run_fba_milestone.py
```

## The result in one line

**Every constraint-based entry was certified blind and agrees with its label: 7/7.**

| Entry | Organism | Label source | Verdict | Agreement |
|---|---|---|---|---|
| `e_coli_core` | *E. coli* K-12 | documented growth rate 0.873922 (Orth 2010) | `reproduced` | ✓ |
| `iIT341` | *H. pylori* 26695 | COBRApy reference growth 0.692813 | `reproduced` | ✓ |
| `iLJ478` | *T. maritima* MSB8 | COBRApy reference growth 0.228407 | `reproduced` | ✓ |
| `iNF517` | *L. lactis* MG1363 | COBRApy reference growth 0.042635 | `reproduced` | ✓ |
| `iJO1366` | *E. coli* K-12 (genome-scale, 2583 rxns) | COBRApy reference growth 0.982372 | `reproduced` | ✓ |
| `iMM904` | *S. cerevisiae* S288C (eukaryote) | COBRApy reference growth 0.287866 | `reproduced` | ✓ |
| `iEK1008` | *M. tuberculosis* H37Rv (pathogen) | COBRApy reference growth 0.058174 | `reproduced` | ✓ |

Each label is held on the catalog entry but withheld from the verdict path, which sees only the
dossier and the model. The certificate is produced by solving the model's objective and comparing
the optimum to the labelled reference, so each agreement is a genuine blind match, not a label read
back. The E. coli core label is a documented literature value; the six genome-scale labels are
the growth rate an independent implementation ([COBRApy](../cross_validation/)) computes for the
distributed model — non-circular in both cases. Every label's exact source is recorded on the
entry.

## What this demonstrates

- **The class closes its self-validation loop on the shared machinery.** The same catalog
  lifecycle, blind view, `run_test_set`, and agreement report the PK/PD class uses carry the
  constraint-based entry unchanged — the certificate flows through them with no forked driver.
- **The scope is honest.** These seven entries attest to *cross-implementation reproduction on the
  distributed models* (and, for E. coli core, a documented literature value) — not to reproducing
  specific paper-reported numbers behind figures. Scaling further, or adding manuscript-reported
  claims, is a data-gathering step, not an engine one.

## Files

| File | What it is |
|---|---|
| [`agreement_report.json`](agreement_report.json) | Per-entry and aggregate agreement with ground truth. |
| [`certificates/e_coli_core.json`](certificates/) | The blind certificate's full content (verdict, scope, claim). |
| [`catalog.json`](catalog.json) | The catalog after the run, with the entry advanced to `certified`. |

See also the [worked example](../worked_example/) for the full dossier → certificate walk, and
[`docs/fba-oracle.md`](../../../docs/fba-oracle.md) for the oracle.
