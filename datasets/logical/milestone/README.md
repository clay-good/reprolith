# Logical (Boolean-network) milestone — blind agreement

The walkable result of `scripts/run_logical_milestone.py`: real Boolean networks CANA and an
independent SAT solver characterize, flowed through the **same** catalog lifecycle, certificate
format, agreement report, and scope flag as every other class. It is the fourth class demonstrating
that the shared contracts generalize — this time with a discrete-attractor oracle that shares
nothing with curve-matching or linear programming.

## What is here

- [`catalog.json`](catalog.json) — the nine entries, each tagged `logical`, carrying a ground-truth
  label (`reproduced`) withheld from the verdict path, advanced to `certified`.
- [`certificates/`](certificates/) — one machine- and human-readable certificate per model. Each
  certifies a single claim. The six small networks are judged by `attractor-signature-match` — the
  weaker of the two comparisons, and named so: it checks the attractor **count and periods**, which
  is all a reference reporting counts can support, and two networks can agree on both while sharing
  no state. The three large signalling networks are judged by `attractor-set-match` against the
  steady states themselves. Concretely: for the small networks, that Reprolith reproduces the
  independent **attractor count** (fixed points *and* cyclic attractors — the two
  synthetic networks contribute synchronous limit cycles); for the three large signalling networks —
  the 60-node **leukemia**, 53-node **MAPK cancer cell-fate** (Grieco et al. 2013), and 44-node
  **guard-cell ABA** networks — that it reproduces the **steady-state count** via the scalable SAT
  fixed-point path, where 2⁴⁴–2⁶⁰ enumeration is impossible.
- [`agreement_report.json`](agreement_report.json) — **9/9** agreement with ground truth.

## Blind and non-circular

Each certificate is produced from only the model's Boolean rules and the independent count — never
the label. The counts are CANA's (small models) or an independent SAT solver's (sympy, for the large
leukemia network — reproduced here by z3); the committed rules are *proven faithful* to CANA's model
before use (see the [cross-validation](../cross_validation/README.md)). So a reproduced verdict here
is Reprolith's own oracle agreeing with an independent tool — e.g. the 11 attractors of CANA's
12-node budding-yeast network (whose seven `CellSize=0` fixed points are Li et al. 2004's published
steady states; the paper's own network is 11 nodes with 7), or the 71 steady states of the 60-node
leukemia network — not a tool agreeing with itself.

Regenerate with `python scripts/run_logical_milestone.py` (reads committed data; no CANA, no
network).
