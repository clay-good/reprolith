# The discipline loop's written record

Reprolith's failure-mode catalogue and its tolerance defaults are supposed to be *evidence-driven,
not guessed up front*, and every disagreement between a blind verdict and its ground-truth label is
supposed to carry a written explanation. Both are claims about process, and prose in a README
cannot keep them true. This is the machine-checked version.

[`datasets/loop_notes.json`](../datasets/loop_notes.json) holds the notes. Each one names what it
explains, what it rests on, and where to check it; `tests/test_loop_notes.py` audits them against
the artifacts — every disagreeing entry in every committed agreement report, every `FailureMode`,
and every default tolerance. A new disagreement with no note, a new failure mode nobody justified,
a note whose subject no longer exists, or a citation that is not in the repository is a gate
failure rather than a quiet omission.

## What a note rests on

The honest part is the `basis` field, because most of the catalogue has never fired:

| Basis | Meaning | Count |
|---|---|---|
| `observed` | a blind run produced it; the artifact is committed | the 31 PK/PD disagreements, the exact-match tolerance |
| `measured` | a deliberate measurement set the number | the scalar and curve tolerances, engine sensitivity |
| `spec` | a class spec requires the category, and no run has emitted it yet | every other failure mode, and the tolerances no certified claim has exercised |

Nineteen of the twenty catalogued failure modes are `spec`; the twentieth (engine sensitivity) is
`measured`, and what the measurement showed was its absence. That is the point of keeping the field:
a category that exists because a spec demands it must not read as loop experience it does not have.

## What the 31 disagreements say

Only the PK/PD run disagrees with its labels at all; the other five classes agree everywhere.

- **30 abstentions**, all one note, traced to **ingestion**: the shipped artifact carries no
  machine-checkable claim, so the run abstains, and a `blocked` verdict can never equal a
  `reproduced` label. Recorded as *explained*, not fixed — closing them needs each paper's claims
  read from the manuscript (tasks 2.1–2.3), not a tolerance or oracle change.
- **1 more-careful verdict** (metformin), traced to the **oracle**: both claims matched well inside
  tolerance, but one rests on a load-bearing salt-form assumption, so the overall verdict is
  `partially-reproduced` against a binary `reproduced` label. Recorded as *explained* — the
  down-grade is the honesty invariant working.

## What the measurements say

Two defaults have real numbers behind them, both from perturbing a shipped reproduction until its
published verdict changed (see [`findings-note.md`](findings-note.md) for the full table):

- **Scalar, numeric — 5% / 15%.** Metformin's dose still reproduces at +8% and −3% and first drops
  to partial at +10%, against an unperturbed agreement of 2.2%.
- **Curve, numeric — 10% / 25%, and the effective budget is the 25%.** The verdict is the stricter
  of the RMSE and a worst-point check at 25% of span, and the worst point binds whenever the error
  concentrates in under about a sixth of the samples. Tightening it to the pass threshold was
  measured and rejected: about half of correct work fails at coarse per-point noise, where the
  present budget produced 0 false failures in 15,000 trials.

Read the record with any JSON reader; it is data, not a rendering of this page.
