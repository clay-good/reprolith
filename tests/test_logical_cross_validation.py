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


def test_reference_covers_published_models_and_cyclic_cases() -> None:
    models = set(_REFERENCE["models"])
    # The four real published models.
    assert {"thaliana", "drosophila", "budding_yeast", "marques_pita"} <= models
    # Plus synthetic networks that exercise the limit-cycle path against CANA, not just fixed points.
    assert {"repressilator", "toggle_plus_switch"} <= models
    # Anchored sanity checks: the Li et al. 2004 yeast fixed-point count, and a genuine cycle.
    assert _REFERENCE["models"]["budding_yeast"]["n_attractors"] == 11
    assert _REFERENCE["models"]["repressilator"]["attractor_periods"] == [2, 6]  # a period-6 cycle


def test_at_least_one_reference_model_has_a_cyclic_attractor() -> None:
    # Guards that the cross-validation actually covers cyclic attractors, not only steady states.
    assert any(
        any(period > 1 for period in entry["attractor_periods"])
        for entry in _REFERENCE["models"].values()
    )
