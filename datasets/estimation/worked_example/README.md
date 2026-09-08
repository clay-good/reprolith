# A parameter re-fitted from data, walked to a certificate

The first published artifact the **estimation** reproduction level has produced, and the sibling of
[the population worked example](../../population/worked_example/README.md): its oracle also shipped
before its optimizer, and `certify_estimation` took the recovered estimate as given.

- [`certificate.txt`](certificate.txt) — the human render.
- [`certificate.json`](certificate.json) — the same certificate, machine-readable.
- [`reference.json`](reference.json) — the observations the fit ran against and the value they were
  generated from, so the recovered estimate has a right answer that is not Reprolith's.

## What it is, and what it is not

The data is the model's own trajectory at `k = 0.2`, **standing in for a paper's raw dataset**: no
shipped dataset in this corpus is a paper's own data. Starting from `k = 0.05` — a factor of four
away — the fit recovers 0.2, so what this demonstrates is that the optimizer finds the value the
data came from, not that some paper's estimate reproduces.

The verdict is `reproduced` at **estimation level**, and the certificate says what that does not
include: a re-fit recovering the paper's parameter is not the same as the model reproducing the
paper's simulated results, and the gap report says so on the claim line rather than leaving a reader
to assume the stronger thing. The tolerance is the wider estimation default, because a re-fit is
sensitive to the objective, the optimizer, the starting values and the dataset — all four of which
the protocol records.

Regenerate with `python scripts/render_worked_examples.py` (needs the `engine` extra).
