"""The linear growth law: E. coli core biomass is affine in the limiting glucose uptake.

A distinct canonical FBA reproduction alongside the Pasteur effect and the COBRApy cross-validation.
When oxygen is in excess so glucose is the sole limiting nutrient, the maximal growth rate is an
*exactly* affine function of the glucose uptake rate — the basis of Edwards & Palsson's phenotypic
phase planes, and a direct consequence of parametric linear programming (an LP optimum is piecewise
linear in a constraint's right-hand side). Non-circular: the linearity is a theorem, not a fit this
engine chose. Needs the engine and fba extras; skips without.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the fba extra (scipy) is not installed")

from reprolith.fba import solve_objective  # noqa: E402
from reprolith.sbml import ingest_fbc_sbml  # noqa: E402

_MODEL = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"


def test_biomass_is_exactly_affine_in_glucose_uptake() -> None:
    model = ingest_fbc_sbml(_MODEL.read_text(encoding="utf-8"))
    glucose = model.reaction_index("R_EX_glc__D_e")
    oxygen = model.reaction_index("R_EX_o2_e")

    def growth(glucose_uptake: float) -> float:
        lower = list(model.lower)
        lower[glucose] = -glucose_uptake  # uptake enters as a negative flux bound
        lower[oxygen] = -1000.0  # oxygen in excess: glucose is the sole limiting nutrient
        return solve_objective(model.stoichiometry, model.objective, lower, model.upper)

    uptakes = [float(v) for v in range(2, 11)]  # 2..10 mmol/gDW/h, all glucose-limited
    mu = [growth(v) for v in uptakes]

    # Ordinary least-squares line through (uptake, growth).
    n = len(uptakes)
    mean_x = sum(uptakes) / n
    mean_y = sum(mu) / n
    sxx = sum((x - mean_x) ** 2 for x in uptakes)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(uptakes, mu))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    residuals = [abs(y - (slope * x + intercept)) for x, y in zip(uptakes, mu)]
    ss_tot = sum((y - mean_y) ** 2 for y in mu)
    ss_res = sum(r * r for r in residuals)
    r_squared = 1.0 - ss_res / ss_tot

    assert slope > 0.0  # positive biomass yield per unit glucose
    assert intercept < 0.0  # the ATP-maintenance demand: an x-intercept > 0, so growth is affine
    assert max(residuals) < 1e-9  # the fit is exact, not approximate — a straight line
    assert r_squared == pytest.approx(1.0, abs=1e-12)
    # The uptake=10 endpoint is the documented aerobic maximum reused across the FBA milestone.
    assert mu[-1] == pytest.approx(0.873922, rel=1e-4)


def test_oxygen_phenotypic_phase_plane_is_concave_with_a_saturation_breakpoint() -> None:
    # Edwards & Palsson's phenotypic phase plane: at fixed glucose, growth versus oxygen uptake is a
    # *piecewise-linear, concave* curve — each linear segment a different optimal metabolic strategy,
    # the slopes falling as oxygen becomes progressively less valuable, until a breakpoint past which
    # extra oxygen adds nothing (glucose is then the sole limit). Concavity and the plateau are exact
    # consequences of parametric linear programming — an LP optimum is concave in a constraint's
    # right-hand side. Non-circular; the two endpoints are the documented Pasteur-effect values.
    model = ingest_fbc_sbml(_MODEL.read_text(encoding="utf-8"))
    glucose = model.reaction_index("R_EX_glc__D_e")
    oxygen = model.reaction_index("R_EX_o2_e")

    def growth(oxygen_uptake: float) -> float:
        lower = list(model.lower)
        lower[glucose] = -10.0  # glucose held fixed; oxygen is the swept axis
        lower[oxygen] = -oxygen_uptake
        return solve_objective(model.stoichiometry, model.objective, lower, model.upper)

    oxygen_uptakes = [float(v) for v in range(0, 31)]  # 0..30 mmol/gDW/h
    mu = [growth(v) for v in oxygen_uptakes]
    slopes = [mu[i + 1] - mu[i] for i in range(len(mu) - 1)]  # unit spacing → slope = difference

    assert all(s >= -1e-9 for s in slopes)  # monotone: more oxygen never lowers the optimum
    assert all(slopes[i + 1] <= slopes[i] + 1e-9 for i in range(len(slopes) - 1))  # concave

    # Documented endpoints (the Pasteur effect): anaerobic vs oxygen-saturated maximal growth.
    assert mu[0] == pytest.approx(0.211663, rel=1e-4)  # oxygen = 0: fermentation only
    saturated = growth(1000.0)
    assert saturated == pytest.approx(0.873922, rel=1e-4)  # oxygen in excess: glucose-limited

    # A genuine saturation breakpoint: growth is still rising in the oxygen-limited region but flat
    # once glucose limits — extra oxygen past the breakpoint yields exactly nothing.
    assert growth(15.0) < saturated  # below the breakpoint: oxygen still limits
    assert growth(30.0) == pytest.approx(saturated)  # above it: the plateau, no further gain
