# Constraint-based milestone result — the walkable blind run

The constraint-based (FBA) class's self-validation run, assembled so a stranger can follow it end
to end: the labelled entry, its blind certificate, and the agreement report — the FBA counterpart
of the [PK/PD bootstrap milestone](../../milestone/README.md). Regenerate it from the repository
alone (no network, needs the `engine` and `fba` extras) with:

```
python scripts/run_fba_milestone.py
```

## The result in one line

**The one ground-truth constraint-based entry was certified blind and agrees with its label: 1/1.**

| Entry | Label | Verdict | Agreement |
|---|---|---|---|
| E. coli core (`e_coli_core`) | `reproduced` (known growth rate 0.873922) | `reproduced` | ✓ |

The label — the model's independently-known maximal aerobic growth rate on glucose minimal medium
(Orth, Fleming & Palsson 2010; BiGG) — is held on the catalog entry but withheld from the verdict
path, which sees only the dossier and the model. The certificate is produced by solving the model's
objective and comparing the optimum to the reported value, so the agreement is a genuine blind
match, not a label read back.

## What this demonstrates

- **The class closes its self-validation loop on the shared machinery.** The same catalog
  lifecycle, blind view, `run_test_set`, and agreement report the PK/PD class uses carry the
  constraint-based entry unchanged — the certificate flows through them with no forked driver.
- **The scope is honest.** This is one entry (`n=1`): the single constraint-based model whose
  reproducibility is independently known and ships in this repo. Scaling to a larger blind set
  needs more fingerprint-curated models, which is a data-gathering step, not an engine one.

## Files

| File | What it is |
|---|---|
| [`agreement_report.json`](agreement_report.json) | Per-entry and aggregate agreement with ground truth. |
| [`certificates/e_coli_core.json`](certificates/) | The blind certificate's full content (verdict, scope, claim). |
| [`catalog.json`](catalog.json) | The catalog after the run, with the entry advanced to `certified`. |

See also the [worked example](../worked_example/) for the full dossier → certificate walk, and
[`docs/fba-oracle.md`](../../../docs/fba-oracle.md) for the oracle.
