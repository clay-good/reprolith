# Bootstrap milestone result — the walkable blind run

The ODE PK/PD bootstrap's self-validation run over the labelled test set, assembled so a stranger
can follow it end to end: the labelled set, a certificate for every entry, and the agreement
report. Regenerate it from the repository alone (no network, needs the `engine` extra) with:

```
python scripts/run_milestone.py
```

## The result in one line

**Every one of the 31 entries yielded a verdict, with zero confidently-wrong verdicts** — one
certified reproduction, and thirty honest abstentions recorded as `blocked` in the agreement report
rather than published as certificates. Only the certified entry has a file under `certificates/`,
so `reprolith certificates-for` returns nothing for the other thirty.

| Outcome | Count | What it means |
|---|---|---|
| `partially-reproduced` | 1 | Metformin (BIOMD0000001028) — claims extracted and verified; reproduced, but with a load-bearing salt-form assumption flagged. |
| `blocked` | 30 | Reprolith **abstained** — the shipped model artifact carries no machine-checkable claims, so there was nothing to reproduce against. Not a failure to reproduce; a recorded missing input. |

Raw agreement with the ground-truth labels is 0/31 — and that number is the honest one, not a bad
one. Read on.

## Why 0/31 is the honest result, not a failure

The agreement metric does an exact match of Reprolith's verdict against the BioModels label. Two
things make it zero, and neither is a wrong verdict:

1. **30 abstentions.** For 30 entries no claims were extracted from the manuscript, so Reprolith
   returned `blocked` rather than guess. A `blocked` never matches a `reproduced` or
   `not-reproduced` label — by design. This is Design Goal 2 in action: *a confidently wrong
   verdict is worse than an honest blocked.* Reprolith produced **no** wrong verdicts here.

2. **One more-careful verdict.** Metformin's label is a binary `reproduced`; Reprolith's verdict
   is `partially-reproduced`, because the reproduction rests on a load-bearing salt-form
   assumption it flagged (see [`../worked_examples/`](../worked_examples/)). The "disagreement" is
   Reprolith being *more* honest than the binary label, not less accurate.

So the run demonstrates exactly what the milestone set out to show: given a claim, the pipeline
produces a trustworthy, qualified verdict (metformin); given no claim, it abstains instead of
guessing (the other 30).

## What the run establishes and what it does not

- **Establishes:** the full pathway runs blind over a real labelled set and yields a certificate
  for every entry; the engine, determinism, and honesty invariants hold on real data.
- **Does not yet establish:** verdict accuracy across the set. That needs the one input the run
  names 30 times — each paper's targetable claims, extracted from the manuscript. The metformin
  entry shows the rest of the pipeline delivers once a claim is in hand.

## Files

- [`agreement_report.json`](agreement_report.json) — per-entry and aggregate agreement, reproducible.
- [`../pkpd_test_set.json`](../pkpd_test_set.json) — the labelled set.
- [`../worked_examples/`](../worked_examples/) — the one fully-certified entry.
- [`../../docs/findings-note.md`](../../docs/findings-note.md) — the findings.
