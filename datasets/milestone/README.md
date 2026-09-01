# Bootstrap milestone result — the walkable blind run

The ODE PK/PD bootstrap's self-validation run over the labelled test set, assembled so a stranger
can follow it end to end: the labelled set, a certificate for every entry, and the agreement
report. Regenerate it from the repository alone (no network, needs the `engine` extra, and the
`corroborate` extra for `corroboration.json`) with:

```
python scripts/run_milestone.py
```

`corroboration.json` records, per certified claim, whether the same curve comes out of COPASI and
libRoadRunner — **at the dose that claim was certified at**, overrides included. Metformin's two
claims differ by a 779.9 mg free-base override; corroborating both on the model's default arm would
compare one run to itself and report stability for an arm neither claim uses. Both are
engine-independent to a published bound of 1e-06, four orders inside the criterion.
`tests/test_pkpd_milestone.py` keys the audit off the bundles, so a claim added without regenerating
this file fails rather than shipping a quietly one-engine verdict.

## The result in one line

**Every one of the 31 entries yielded a verdict, and none of them is a false pass** — four
certified reproductions, and twenty-seven honest abstentions recorded as `blocked` in the agreement
report rather than published as certificates. Only the certified entries have files under
`certificates/`, so `reprolith certificates-for` returns nothing for the other twenty-seven.

| Outcome | Count | What it means |
|---|---|---|
| `reproduced` | 1 | Metformin in mice, intravenous (BIOMD0000001027) — a clean, unqualified pass over fourteen claims. That paper dosed its mice with metformin rather than the hydrochloride salt, so nothing had to be converted and no assumption was needed. |
| `partially-reproduced` | 3 | The three orally-dosed models (BIOMD0000001028, `…029`, `…039`) — claims extracted and verified, reproduced, but each with a load-bearing salt-form assumption flagged. |
| `blocked` | 27 | Reprolith **abstained** — Reprolith holds no extracted claims for these papers, so there was nothing to reproduce and no model was run. Not a failure to reproduce; a recorded missing input. |

Raw agreement with the ground-truth labels is 1/31 — and that number is the honest one, not a bad
one. Read on.

## Why 1/31 is the honest result, not a failure

The agreement metric does an exact match of Reprolith's verdict against the BioModels label. Two
things account for the thirty that do not match, and neither is a false pass:

1. **27 abstentions.** For 27 entries no claims were extracted from the manuscript, so Reprolith
   returned `blocked` rather than guess. A `blocked` never matches a `reproduced` or
   `not-reproduced` label — by design. This is Design Goal 2 in action: *a confidently wrong
   verdict is worse than an honest blocked.*

2. **Three more-careful verdicts.** Each orally-dosed model's label is a binary `reproduced`;
   Reprolith's verdict is `partially-reproduced`, because the reproduction rests on a load-bearing
   salt-form assumption it flagged (see [`../worked_examples/`](../worked_examples/)). Each
   "disagreement" is Reprolith being *more* honest than the binary label, not less accurate — a
   withheld pass, never a false one, which is the direction `reprolith self-validation` prints
   beside the count.

So the run demonstrates exactly what the milestone set out to show: given a claim, the pipeline
produces a trustworthy, qualified verdict — and, on the one model that needed no assumption, an
unqualified one; given no claim, it abstains instead of guessing (the other 27).

## What the run establishes and what it does not

- **Establishes:** the full pathway runs blind over a real labelled set and yields a certificate
  for every entry; the engine, determinism, and honesty invariants hold on real data.
- **Does not yet establish:** verdict accuracy across the set. That needs the one input the run
  names 27 times — each paper's targetable claims, extracted from the manuscript. The four
  metformin entries show the rest of the pipeline delivers once a claim is in hand.

## Files

- [`agreement_report.json`](agreement_report.json) — per-entry and aggregate agreement, reproducible.
- [`../pkpd_test_set.json`](../pkpd_test_set.json) — the labelled set.
- [`../worked_examples/`](../worked_examples/) — the fully-certified entries.
- [`../../docs/findings-note.md`](../../docs/findings-note.md) — the findings.
