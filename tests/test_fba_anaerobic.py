"""The Pasteur effect: E. coli core's anaerobic growth rate (constraint-based-class).

A distinct canonical FBA reproduction alongside the aerobic milestone: removing oxygen forces
fermentation and collapses the maximal growth rate. Needs the engine and fba extras; skips without.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the fba extra (scipy) is not installed")

from reprolith import lint_objective  # noqa: E402

_MODEL = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"


def test_anaerobic_growth_rate_is_the_pasteur_effect_value() -> None:
    sbml = _MODEL.read_text(encoding="utf-8")
    # Glucose-limited, oxygen removed (anaerobic): the model ferments, and the maximal growth rate
    # drops from the aerobic 0.8739 to the documented 0.211663 /h — the Pasteur effect.
    result = lint_objective(
        sbml, reported=0.211663, medium={"R_EX_glc__D_e": 10.0, "R_EX_o2_e": 0.0}
    )
    assert result.verdict.value == "reproduced"
    assert result.method == "scalar-relative-error"


def test_removing_oxygen_lowers_the_growth_rate_versus_aerobic() -> None:
    sbml = _MODEL.read_text(encoding="utf-8")
    aerobic = lint_objective(sbml, reported=0.873922, medium={"R_EX_glc__D_e": 10.0, "R_EX_o2_e": 1000.0})
    anaerobic = lint_objective(sbml, reported=0.211663, medium={"R_EX_glc__D_e": 10.0, "R_EX_o2_e": 0.0})
    # Both reproduce their respective reported values, and anaerobic is the smaller — respiration
    # yields far more biomass per glucose than fermentation.
    assert aerobic.verdict.value == "reproduced" and anaerobic.verdict.value == "reproduced"
    assert 0.211663 < 0.873922
