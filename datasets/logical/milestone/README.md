# Logical (Boolean-network) milestone — blind agreement

The walkable result of `scripts/run_logical_milestone.py`: real Boolean networks CANA and an
independent SAT solver characterize, flowed through the **same** catalog lifecycle, certificate
format, agreement report, and scope flag as every other class. It is the fourth class demonstrating
that the shared contracts generalize — this time with a discrete-attractor oracle that shares
nothing with curve-matching or linear programming.

## What is here

- [`catalog.json`](catalog.json) — the seven entries, each tagged `logical`, carrying a ground-truth
  label (`reproduced`) withheld from the verdict path, advanced to `certified`.
- [`certificates/`](certificates/) — one machine- and human-readable certificate per model. Each
  certifies a single claim, judged by `attractor-set-match`: for the small networks, that Reprolith
  reproduces the independent **attractor count** (fixed points *and* cyclic attractors — the two
  synthetic networks contribute synchronous limit cycles); for the 60-node **leukemia** network,
  that it reproduces the **steady-state count** via the scalable SAT fixed-point path, where 2⁶⁰
  enumeration is impossible.
- [`agreement_report.json`](agreement_report.json) — **7/7** agreement with ground truth.

## Blind and non-circular

Each certificate is produced from only the model's Boolean rules and the independent count — never
the label. The counts are CANA's (small models) or an independent SAT solver's (sympy, for the large
leukemia network — reproduced here by z3); the committed rules are *proven faithful* to CANA's model
before use (see the [cross-validation](../cross_validation/README.md)). So a reproduced verdict here
is Reprolith's own oracle agreeing with an independent tool — e.g. the 11 fixed points of the Li et
al. 2004 yeast cell-cycle network, or the 71 steady states of the 60-node leukemia network — not a
tool agreeing with itself.

Regenerate with `python scripts/run_logical_milestone.py` (reads committed data; no CANA, no
network).
