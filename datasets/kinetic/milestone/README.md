# Generic-kinetic milestone result — the walkable blind run

The generic-kinetic class's self-validation run, assembled so a stranger can follow it end to end:
the labelled entries, a blind certificate for each, and the agreement report — the kinetic
counterpart of the [PK/PD](../../milestone/README.md) and
[constraint-based](../../constraint_based/milestone/README.md) milestones. Regenerate it from the
repository alone (no network, needs the `engine` extra) with:

```
python scripts/run_kinetic_milestone.py
```

## The result in one line

**All six kinetic entries were certified blind and agree with their label: 6/6.**

| Entry | Network | Label source | Verdict |
|---|---|---|---|
| `BIOMD0000000010` | signaling (MAPK cascade) | libRoadRunner reference curve | `reproduced` |
| `BIOMD0000000012` | gene-regulatory (repressilator) | libRoadRunner reference curve | `reproduced` |
| `BIOMD0000000051` | metabolic (E. coli carbon) | libRoadRunner reference curve | `reproduced` |
| `BIOMD0000000005` | cell-cycle (Tyson) | libRoadRunner reference curve | `reproduced` |
| `BIOMD0000000021` | circadian (Leloup) | libRoadRunner reference curve | `reproduced` |
| `BIOMD0000000058` | calcium (Bindschadler) | libRoadRunner reference curve | `reproduced` |

Each label is held on the catalog entry but withheld from the verdict path, which sees only the
model and the reference curve. The certificate is produced by simulating the model under Reprolith's
pinned COPASI engine and comparing the trajectory to the reference with the shared `judge_curve`
oracle (normalized distance), so each agreement is a genuine blind match — and non-circular, since
the reference comes from an independent simulator, not from COPASI.

## What this demonstrates

- **The curve oracle carries a third class unchanged.** The same catalog lifecycle, blind view,
  `certify_curves`, `run_test_set`, and agreement report the PK/PD and constraint-based classes use
  carry these systems-biology models with no forked driver.
- **Diversity, not one lucky model.** Signaling, gene-regulatory, and metabolic dynamics all
  reproduce, so the contract is general.

## Files

Every entry is additionally **engine-independent**: the same trajectory under both COPASI and
libRoadRunner (6/6), so no verdict here rests on a single solver's quirk — see
[`corroboration.json`](corroboration.json).

| File | What it is |
|---|---|
| [`agreement_report.json`](agreement_report.json) | Per-entry and aggregate agreement with ground truth. |
| [`certificates/`](certificates/) | Each blind certificate's full content (verdict, scope, curve distance). |
| [`catalog.json`](catalog.json) | The catalog after the run, entries advanced to `certified`. |
| [`corroboration.json`](corroboration.json) | Per-entry cross-engine agreement (COPASI vs libRoadRunner). |

See also the [cross-validation set](../cross_validation.json) and
[`docs/kinetic-class.md`](../../../docs/kinetic-class.md).
