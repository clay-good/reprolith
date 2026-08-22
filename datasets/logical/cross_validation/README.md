# Logical-class cross-validation — real published models vs an independent tool

Non-circular ground truth for the logical (Boolean-network) oracle, the counterpart of the FBA
[cross-validation](../../constraint_based/cross_validation/) against COBRApy and the kinetic
cross-validation against libRoadRunner. Here the independent tool is **CANA** (Correia et al.
2018), a separate Boolean-network library that shares no code with Reprolith.

## What is checked

Four **real, published** Boolean models bundled by CANA:

| Model | Nodes | Attractors (all fixed points) | Source |
|---|---|---|---|
| `thaliana` | 15 | 10 | Arabidopsis flower morphogenesis (Chaos et al. 2006) |
| `drosophila` | 17 | 10 | Drosophila segment polarity, single cell (Albert & Othmer 2003) |
| `budding_yeast` | 12 | 11 | Budding-yeast cell cycle, CANA's 12-node variant (after Li et al. 2004) |
| `marques_pita` | 7 | 1 | Two-symbol schemata example (Marques-Pita & Rocha 2013) |

For each, [`reference.json`](reference.json) stores the model's Boolean rules and CANA's
independently-computed **attractor signature** — the number of attractors and their periods.

Two synthetic networks are added so the **limit-cycle** path is cross-validated too, not only fixed
points: a three-gene `repressilator` ring (a period-6 synchronous cycle plus a period-2 one) and a
`toggle_plus_switch` (four fixed points crossed with two 2-cycles). CANA remains the independent
oracle for these; they exercise cyclic attractors that the published models above (all fixed-point
only under synchronous updating) do not.

## Why it is non-circular and faithful

- **Independent oracle.** The attractor counts come from CANA's own algorithm, not Reprolith's.
- **Provably faithful rules.** [`scripts/regenerate_logical_references.py`](../../../scripts/regenerate_logical_references.py)
  exports each node's CANA truth table to a Reprolith rule *and verifies it against CANA's own
  per-node step over every input combination* before committing — so the committed rules are
  provably CANA's model, not a transcription guess.
- **Representation-independent comparison.** The signature (count + periods) is invariant to CANA's
  constant-node reduction and to state encoding, so agreement is a genuine reproduction of each
  model's documented attractor structure — e.g. the 11 attractors of CANA's 12-node budding-yeast network, whose seven `CellSize=0`
  fixed points are exactly Li et al. 2004's published steady states (basins
  1764/151/109/9/7/7/1)
  cell-cycle network.

[`tests/test_logical_cross_validation.py`](../../../tests/test_logical_cross_validation.py) runs
Reprolith's own `parse_boolean_network` + attractor computation on the committed rules and checks it
reproduces CANA's signature — using only runtime code, no CANA at test time. Regenerate the
reference with `pip install -e ".[refgen]"` then `python scripts/regenerate_logical_references.py`.

## Scalable fixed points on a large model

The four models above are small enough to enumerate. [`scalable_fixed_points.json`](scalable_fixed_points.json)
cross-validates the **scalable** path on three real signalling networks that are not — their state
spaces are far beyond 2ⁿ enumeration:

| Model | Nodes | Fixed points | Source |
|---|---|---|---|
| `leukemia` | 60 | 71 | T-LGL leukemia signalling (Zhang et al. 2008) |
| `mapk_cancer` | 53 | 12 | MAPK network / cancer cell-fate (Grieco et al. 2013) |
| `guard_cell_aba` | 44 | 16 | Guard-cell abscisic-acid signalling (Cell Collective) |

Their **fixed points** (steady states) are found by SAT instead of enumeration. For each, the
committed reference — the model's rules, the fixed-point count, and a SHA-256 of the sorted
fixed-point set — is computed by **sympy's** SAT solver, an implementation independent of the **z3**
solver Reprolith uses, so agreement is again a cross-tool check.
[`tests/test_logical_scalable.py`](../../../tests/test_logical_scalable.py) checks Reprolith
reproduces each exact set, verifies every returned state is a genuine steady state, and separately
confirms the SAT path equals exhaustive enumeration on many small random networks. It needs the
`sat` extra (z3) and skips without it. The rules are exported from CANA (Cell Collective models via
`load_cell_collective_model`) and *proven faithful* before use, exactly as for the small models.
