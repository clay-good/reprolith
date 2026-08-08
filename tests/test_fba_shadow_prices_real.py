"""The economic dual on a real model: E. coli core shadow prices and the phase-plane breakpoint.

`test_fba_shadow_prices.py` pins the dual's definition and sign on toy LPs. This carries it onto a
real genome-scale-ingested model and ties it to a result already established independently — the
oxygen phenotypic phase plane. The marginal value of a nutrient is exactly the slope of that plane,
so the dual and the primal must tell the same story:

- below the oxygen breakpoint, oxygen has a *positive, falling* marginal value (the concave phase
  plane's decreasing slope), and
- above it, oxygen's shadow price is *exactly zero* — complementary slackness, the same plateau the
  phase-plane test sees from the primal side.

Non-circular: each dual is checked against the derivative of the primal optimum (a finite
difference of `solve_objective`), and the qualitative structure against the independently-known
Pasteur-effect phase plane — never against a number this engine chose. Needs the engine and fba
extras; skips without.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the fba extra (scipy) is not installed")

from reprolith.fba import shadow_prices, solve_objective  # noqa: E402
from reprolith.sbml import ingest_fbc_sbml  # noqa: E402

_MODEL = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"


def _model():
    return ingest_fbc_sbml(_MODEL.read_text(encoding="utf-8"))


def _bounds_at(model, oxygen_uptake: float) -> list[float]:
    """Glucose held at 10 mmol/gDW/h; oxygen uptake set to ``oxygen_uptake`` (as a lower bound)."""
    glucose = model.reaction_index("R_EX_glc__D_e")
    oxygen = model.reaction_index("R_EX_o2_e")
    lower = list(model.lower)
    lower[glucose] = -10.0
    lower[oxygen] = -oxygen_uptake
    return lower


def test_oxygen_shadow_price_equals_the_primal_bound_derivative() -> None:
    # On the real model, the oxygen exchange's reduced cost must equal dZ*/d(its lower bound),
    # computed independently as a finite difference of the primal optimum.
    model = _model()
    oxygen = model.reaction_index("R_EX_o2_e")
    eps = 1e-4
    for oxygen_uptake in (5.0, 15.0, 25.0):
        lower = _bounds_at(model, oxygen_uptake)
        base = solve_objective(model.stoichiometry, model.objective, lower, model.upper)
        dual = shadow_prices(model.stoichiometry, model.objective, lower, model.upper)
        relaxed = list(lower)
        relaxed[oxygen] = -(oxygen_uptake + eps)  # allow eps more uptake: lower moves by -eps
        raised = solve_objective(model.stoichiometry, model.objective, relaxed, model.upper)
        finite_difference = (raised - base) / (-eps)  # dZ*/d(lower bound)
        assert dual.reactions[oxygen] == pytest.approx(finite_difference, abs=1e-4)


def test_oxygen_marginal_value_is_positive_and_falling_then_zero_at_the_plateau() -> None:
    # The marginal value of oxygen uptake is -reduced_cost (uptake enters as a negative lower bound).
    # It reproduces the concave phase plane: positive and decreasing while oxygen limits, then exactly
    # zero once glucose alone limits — complementary slackness, matching the phase-plane breakpoint.
    model = _model()
    oxygen = model.reaction_index("R_EX_o2_e")

    def marginal_value(oxygen_uptake: float) -> float:
        lower = _bounds_at(model, oxygen_uptake)
        return -shadow_prices(model.stoichiometry, model.objective, lower, model.upper).reactions[oxygen]

    limited_low = marginal_value(5.0)
    limited_high = marginal_value(15.0)
    plateau = marginal_value(30.0)

    assert limited_low > limited_high > 0.0  # positive and falling — the concave, decreasing slope
    assert plateau == pytest.approx(0.0, abs=1e-9)  # past the breakpoint, oxygen is worth nothing


def test_glucose_stays_limiting_with_a_strictly_positive_value() -> None:
    # Glucose is the sole substrate held scarce, so it limits growth at every oxygen level: its
    # exchange reduced cost is nonzero throughout, and its marginal value rises as oxygen grows
    # (each glucose is worth more when it can be fully respired).
    model = _model()
    glucose = model.reaction_index("R_EX_glc__D_e")

    def glucose_value(oxygen_uptake: float) -> float:
        lower = _bounds_at(model, oxygen_uptake)
        return -shadow_prices(model.stoichiometry, model.objective, lower, model.upper).reactions[glucose]

    values = [glucose_value(u) for u in (5.0, 15.0, 30.0)]
    assert all(v > 0.0 for v in values)  # glucose always limits
    assert values[0] < values[1] < values[2]  # worth more as oxygen becomes abundant
