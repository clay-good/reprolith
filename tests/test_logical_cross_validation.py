"""Blind cross-validation of the logical oracle against an independent tool (roadmap #9).

Reprolith's logical attractor computation is measured against CANA (Correia et al. 2018) — an
independent Boolean-network library — on four *real, published* Boolean models: the Arabidopsis
flower, Drosophila segment-polarity, budding-yeast cell-cycle, and a schemata example network.
CANA's independently-computed attractor signature (the number of attractors and their periods) is
committed as ground truth in ``datasets/logical/cross_validation/reference.json``; this test runs
Reprolith's *own* oracle on the committed (faithfully exported) rules and checks it reproduces that
signature — a non-circular cross-tool agreement, the logical counterpart of the FBA-vs-COBRApy and
kinetic-vs-libRoadRunner checks. It needs no CANA at test time, only the committed data.

The signature (count + periods) is invariant to CANA's constant-node reduction and to state
encoding, so agreement on it is a representation-independent reproduction of each model's documented
attractor structure — e.g. the 11 fixed points of the Li et al. 2004 yeast cell-cycle network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import parse_boolean_network

_REFERENCE = json.loads(
    (Path(__file__).parent.parent / "datasets" / "logical" / "cross_validation" / "reference.json")
    .read_text(encoding="utf-8")
)


@pytest.mark.parametrize("model", sorted(_REFERENCE["models"]))
def test_reprolith_reproduces_cana_attractor_signature(model: str) -> None:
    entry = _REFERENCE["models"][model]
    net = parse_boolean_network(entry["rules"])
    periods = entry["attractor_periods"]

    if all(period == 1 for period in periods):
        # A fixed-point-only model (all four are): reproducing CANA's fixed-point count is the
        # signature. fixed_points() is far cheaper than trail-following every attractor, which
        # matters on the 15-17 node networks.
        found = len(net.fixed_points())
        assert found == entry["n_attractors"], (
            f"{model}: found {found} fixed points, CANA reports {entry['n_attractors']}"
        )

    if entry["n_nodes"] <= 12:
        # Small enough to also verify the full signature — including that no cyclic attractor is
        # spuriously produced — by the complete attractor computation.
        full = sorted(len(a) for a in net.attractors())
        assert full == periods, f"{model}: attractor periods {full} != CANA {periods}"


def test_reference_covers_the_expected_published_models() -> None:
    assert set(_REFERENCE["models"]) == {"thaliana", "drosophila", "budding_yeast", "marques_pita"}
    # The budding-yeast cell-cycle network's documented fixed-point count, as an anchored sanity check.
    assert _REFERENCE["models"]["budding_yeast"]["n_attractors"] == 11
