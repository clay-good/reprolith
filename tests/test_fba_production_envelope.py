"""The production envelope is a concave frontier: an exact parametric-LP theorem.

A distinct canonical FBA reproduction alongside the linear growth law and the phenotypic phase
plane. The maximum byproduct flux achievable at a fixed growth rate is a *concave*, piecewise-linear
function of growth — a direct consequence of parametric linear programming: the feasible flux
polytope is convex, the growth level enters as a single linear equality, so a convex combination of
two feasible (growth, product) points is itself feasible, and the frontier can only bow outward.
Non-circular: concavity is a theorem, not a shape this engine chose. The classic acetate-vs-growth
envelope of E. coli core also shows the overflow-metabolism breakpoint where secretion engages.
Needs the engine and fba extras; skips without.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the fba extra (scipy) is not installed")

from reprolith.fba import production_envelope  # noqa: E402
from reprolith.sbml import ingest_fbc_sbml  # noqa: E402

_MODEL = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"


def test_production_envelope_frontier_is_concave_and_piecewise_linear() -> None:
    model = ingest_fbc_sbml(_MODEL.read_text(encoding="utf-8"))
    acetate = model.reaction_index("R_EX_ac_e")
    envelope = production_envelope(
        model.stoichiometry, model.objective, model.lower, model.upper,
        target=acetate, points=25,
    )

    # The frontier is the maximum acetate secretion at each growth level.
    frontier = envelope.target_max

    # Concavity: every interior point lies on or above the chord between its neighbours. This is the
    # exact parametric-LP theorem — the optimum of a maximization over a convex set is concave in a
    # linear constraint's right-hand side (here the pinned growth level).
    for i in range(1, len(frontier) - 1):
        chord = (frontier[i - 1] + frontier[i + 1]) / 2.0
        assert frontier[i] >= chord - 1e-9

    # It is a genuine trade-off, not a flat line: acetate is highest at zero growth and pinned to
    # zero once all carbon must go to biomass at the maximum growth rate.
    assert frontier[0] > frontier[-1]
    assert envelope.target_max[-1] == pytest.approx(0.0, abs=1e-6)
    assert envelope.target_min[-1] == pytest.approx(0.0, abs=1e-6)
    assert envelope.growth[-1] == pytest.approx(0.873922, rel=1e-4)

    # Piecewise-linear with a breakpoint: the segment slopes are not all equal (overflow secretion
    # engages at a growth rate below the maximum), yet each segment is itself a straight line.
    slopes = [
        (frontier[i + 1] - frontier[i]) / (envelope.growth[i + 1] - envelope.growth[i])
        for i in range(len(frontier) - 1)
    ]
    assert max(slopes) - min(slopes) > 1.0  # a real bend, not a single line
    # Concavity again, read on the slopes: they are non-increasing as growth rises.
    for a, b in zip(slopes, slopes[1:]):
        assert b <= a + 1e-9


def test_production_envelope_rejects_a_degenerate_point_count() -> None:
    model = ingest_fbc_sbml(_MODEL.read_text(encoding="utf-8"))
    acetate = model.reaction_index("R_EX_ac_e")
    with pytest.raises(ValueError, match="at least 2 points"):
        production_envelope(
            model.stoichiometry, model.objective, model.lower, model.upper,
            target=acetate, points=1,
        )
