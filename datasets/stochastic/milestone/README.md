# Stochastic (SSA) milestone — blind agreement against closed-form ground truth

The walkable result of `scripts/run_stochastic_milestone.py`: four reaction networks whose
stationary, equilibrium or first-passage result is known in closed form, flowed through the same
catalog lifecycle, certificate format, agreement report, and scope flag as every other class. It is the fifth class
demonstrating the shared contracts generalize — this time with a *stochastic* simulator whose
reproducible result is a distribution, judged by the population/distributional oracle.

## What is here

- [`catalog.json`](catalog.json) — four entries, tagged `stochastic`, each with a ground-truth
  label withheld from the verdict path, advanced to `certified`.
- [`certificates/`](certificates/) — one certificate per system: three certifying that the SSA
  ensemble reproduces the analytical mean, and one that it reproduces an analytical **mean time to
  extinction**.
- [`agreement_report.json`](agreement_report.json) — **4/4** agreement.

## Non-circular and honest

The ground truth is closed-form mathematics, not a tool or a fabricated value: the immigration-death
process has a Poisson stationary distribution with mean `k/γ`, the reversible isomerization
`A <-> B` has a binomial equilibrium with mean `N·kf/(kf+kr)`, and a pure death process's mean
first passage to zero from `n₀` molecules is `H(n₀)/k` — the harmonic number over the rate, since
the wait in state `i` is exponential with rate `k·i`. Each certificate is produced from
only the network and the pinned sampling protocol (seed + trajectory count), never the label, and
the pinned seed makes it byte-reproducible. Every verdict is **partially-reproduced**, not clean:
the claim reproduces but a stochastic reproduction is qualified by its sampling dependence, so the
ground-truth label is partially-reproduced too — and they agree.

The first-passage entry has **no second engine** behind it, and the corroboration surface says so
rather than counting three of four as a clean sweep: libRoadRunner's Gillespie gives a mean at a
time, not a first passage.

Regenerate with `python scripts/run_stochastic_milestone.py` (no extras, no network).
