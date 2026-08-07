# Stochastic (SSA) milestone — blind agreement against closed-form ground truth

The walkable result of `scripts/run_stochastic_milestone.py`: three reaction networks whose
stationary/equilibrium mean is known in closed form, flowed through the same catalog lifecycle,
certificate format, agreement report, and scope flag as every other class. It is the fifth class
demonstrating the shared contracts generalize — this time with a *stochastic* simulator whose
reproducible result is a distribution, judged by the population/distributional oracle.

## What is here

- [`catalog.json`](catalog.json) — three entries, tagged `stochastic`, each with a ground-truth
  label withheld from the verdict path, advanced to `certified`.
- [`certificates/`](certificates/) — one certificate per system, each certifying that the SSA
  ensemble reproduces the analytical mean.
- [`agreement_report.json`](agreement_report.json) — **3/3** agreement.

## Non-circular and honest

The ground truth is closed-form mathematics, not a tool or a fabricated value: the immigration-death
process has a Poisson stationary distribution with mean `k/γ`, and the reversible isomerization
`A <-> B` has a binomial equilibrium with mean `N·kf/(kf+kr)`. Each certificate is produced from
only the network and the pinned sampling protocol (seed + trajectory count), never the label, and
the pinned seed makes it byte-reproducible. Every verdict is **partially-reproduced**, not clean:
the claim reproduces but a stochastic reproduction is qualified by its sampling dependence, so the
ground-truth label is partially-reproduced too — and they agree.

Regenerate with `python scripts/run_stochastic_milestone.py` (no extras, no network).
