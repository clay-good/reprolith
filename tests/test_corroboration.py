"""Cross-engine corroboration: COPASI vs libRoadRunner (spec: simulation-oracle).

Running the same model under two independently-implemented engines and comparing trajectories turns
"engine-sensitive" from a hidden risk into a reported result. Needs both the ``engine`` (COPASI) and
``corroborate`` (libRoadRunner) extras; skips without either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")
pytest.importorskip("roadrunner", reason="the optional 'corroborate' extra (libRoadRunner) is not installed")

from reprolith import corroborate_curve, roadrunner_pin, simulate_with_roadrunner  # noqa: E402

_SBML = (
    Path(__file__).parent.parent / "datasets" / "kinetic" / "BIOMD0000000010.xml"
).read_text(encoding="utf-8")


def test_two_independent_engines_agree_so_the_verdict_is_engine_independent() -> None:
    result = corroborate_curve(_SBML, "MAPK_PP", duration=4000.0, steps=200)
    assert result.engines == ("copasi", "roadrunner")
    assert result.stable
    assert result.distance < 1e-3  # the two solvers land on the same oscillating trajectory
    assert "engine-independent" in result.summary()


def test_an_impossibly_tight_tolerance_reports_engine_sensitive() -> None:
    # The stable/sensitive decision responds to the declared tolerance: with zero tolerance even the
    # ~1e-7 solver difference is flagged, exercising the engine-sensitive branch honestly.
    result = corroborate_curve(_SBML, "MAPK_PP", duration=4000.0, steps=200, rel_tol=0.0)
    assert not result.stable
    assert "engine-sensitive" in result.summary()


def test_roadrunner_backend_matches_the_grid_and_carries_a_pin() -> None:
    times, values = simulate_with_roadrunner(_SBML, "MAPK_PP", duration=4000.0, steps=200)
    assert len(times) == len(values) == 201
    assert times[0] == 0.0 and times[-1] == pytest.approx(4000.0)
    pin = roadrunner_pin()
    assert pin.engine == "roadrunner" and pin.version
