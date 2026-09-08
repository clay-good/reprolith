# A population envelope, walked from a model to a certificate

The first published artifact the **population** reproduction level has produced. Its oracle shipped
before its simulator, and for a while the two halves met only in a docstring: every test of
`simulate_population` stopped at its bands, and every test of `certify_population` started from
bands somebody typed. They meet here, with nothing hand-written between the model and the verdict.

- [`certificate.txt`](certificate.txt) — the human render.
- [`certificate.json`](certificate.json) — the same certificate, machine-readable.
- [`reference.json`](reference.json) — what it was judged **against**: the closed-form percentiles
  of `C(t)` for a one-compartment IV bolus whose volume is log-normal,
  `(D/V)·exp(-k·t)·exp(omega·z_p)`, and the peak's coefficient of variation, which is the volume's
  since the peak is `D/V`.

It carries **both** halves of a population claim, which is what these papers print: the envelope,
and the between-subject **%CV** of the peak — a statistic of the subjects rather than of the bands.
The population is 1,500 subjects rather than the 500 an envelope needs, because a 30% CV's own
standard error is 3.6% of it at 500 against a 5% pass threshold; at that size the spread claim is
abstained on rather than judged. Each claim's protocol line carries what *it* rests on: the
envelope's says what the outermost band's sampling error is, and the CV's says what its own
jackknife error bar is.

## What it is, and what it is not

The reference is **mathematics standing in for a paper's figure**. No published population figure is
in this corpus — reading a paper's bands out of its plot is not built — so what this demonstrates is
that the whole path runs and that its envelope is the one the distribution actually has, not that
some paper's figure reproduces. The certificate says as much in its own claim line.

The verdict is `partially-reproduced` on a claim that reproduces cleanly, and that is the class's
honesty invariant rather than a shortfall: a population verdict rests on a reconstructed
between-subject variability model and a sampling choice Reprolith made, so the certificate carries
that sampling as a load-bearing assumption and cannot call itself an unqualified pass.

Regenerate with `python scripts/render_worked_examples.py` (needs the `engine` extra).
