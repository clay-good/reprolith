# Logical (Boolean-network) milestone — blind agreement

The walkable result of `scripts/run_logical_milestone.py`: the four real, published Boolean models
CANA independently characterizes, flowed through the **same** catalog lifecycle, certificate format,
agreement report, and scope flag as every other class. It is the fourth class demonstrating that the
shared contracts generalize — this time with a discrete-attractor oracle that shares nothing with
curve-matching or linear programming.

## What is here

- [`catalog.json`](catalog.json) — the four entries, each tagged `logical`, carrying a ground-truth
  label (`reproduced`) withheld from the verdict path, advanced to `certified`.
- [`certificates/`](certificates/) — one machine- and human-readable certificate per model. Each
  certifies a single claim — that Reprolith's attractor oracle reproduces CANA's independently
  computed steady-state (fixed-point) count — judged by `attractor-set-match`.
- [`agreement_report.json`](agreement_report.json) — **4/4** agreement with ground truth.

## Blind and non-circular

Each certificate is produced from only the model's Boolean rules and CANA's attractor count — never
the label. The count itself is CANA's, an independent library; the committed rules are *proven
faithful* to CANA's model before use (see the
[cross-validation](../cross_validation/README.md)). So a reproduced verdict here is Reprolith's own
attractor oracle agreeing with an independent tool on a real published model — e.g. the 11 fixed
points of the Li et al. 2004 yeast cell-cycle network — not a tool agreeing with itself.

Regenerate with `python scripts/run_logical_milestone.py` (reads committed data; no CANA, no
network).
