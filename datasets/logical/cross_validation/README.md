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
| `budding_yeast` | 12 | 11 | Budding-yeast cell-cycle network (Li et al. 2004) |
| `marques_pita` | 7 | 1 | Two-symbol schemata example (Marques-Pita & Rocha 2013) |

For each, [`reference.json`](reference.json) stores the model's Boolean rules and CANA's
independently-computed **attractor signature** — the number of attractors and their periods.

## Why it is non-circular and faithful

- **Independent oracle.** The attractor counts come from CANA's own algorithm, not Reprolith's.
- **Provably faithful rules.** [`scripts/regenerate_logical_references.py`](../../../scripts/regenerate_logical_references.py)
  exports each node's CANA truth table to a Reprolith rule *and verifies it against CANA's own
  per-node step over every input combination* before committing — so the committed rules are
  provably CANA's model, not a transcription guess.
- **Representation-independent comparison.** The signature (count + periods) is invariant to CANA's
  constant-node reduction and to state encoding, so agreement is a genuine reproduction of each
  model's documented attractor structure — e.g. the 11 fixed points of the Li et al. 2004 yeast
  cell-cycle network.

[`tests/test_logical_cross_validation.py`](../../../tests/test_logical_cross_validation.py) runs
Reprolith's own `parse_boolean_network` + attractor computation on the committed rules and checks it
reproduces CANA's signature — using only runtime code, no CANA at test time. Regenerate the
reference with `pip install -e ".[refgen]"` then `python scripts/regenerate_logical_references.py`.
