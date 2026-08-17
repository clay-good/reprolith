"""Cross-engine corroboration: COPASI vs libRoadRunner (spec: simulation-oracle).

Running the same model under two independently-implemented engines and comparing trajectories turns
"engine-sensitive" from a hidden risk into a reported result. Needs both the ``engine`` (COPASI) and
``corroborate`` (libRoadRunner) extras; skips without either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")
pytest.importorskip("roadrunner", reason="the optional 'corroborate' extra (libRoadRunner) is not installed")

from reprolith import corroborate_curve, roadrunner_pin, simulate_with_roadrunner  # noqa: E402

_KIN = Path(__file__).parent.parent / "datasets" / "kinetic"
_MODELS = {m["id"]: m for m in json.loads((_KIN / "cross_validation.json").read_text())["models"]}
_SBML = (_KIN / "BIOMD0000000010.xml").read_text(encoding="utf-8")


@pytest.mark.parametrize("model_id", sorted(_MODELS))
def test_verdict_is_engine_independent_across_the_kinetic_class(model_id: str) -> None:
    # Verdict stability reported across two engines for every supported kinetic model (roadmap #5):
    # COPASI and libRoadRunner land on the same trajectory, so each verdict is the model's, not a
    # single solver's.
    spec = _MODELS[model_id]
    result = corroborate_curve(
        (_KIN / f"{model_id}.xml").read_text(encoding="utf-8"),
        spec["species"], duration=spec["duration"], steps=spec["steps"],
    )
    assert result.engines == ("copasi", "roadrunner")
    assert result.stable
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


def test_the_published_distance_is_a_bound_the_engines_can_reproduce() -> None:
    """Five figures of a distance between two agreeing engines is not a measurement.

    COPASI is not bit-identical across repeated calls in one process — a period-2 alternation at
    about 1e-11 relative — and the distance between two engines that agree is a difference of
    nearly-equal numbers, so that noise is amplified into the leading digits. On one committed
    model it moved the distance by 8%, and the committed five-figure value was not among the
    values a re-run produced. The bound rounds up, so it never claims better agreement than was
    measured, and it survives the wobble.
    """
    from reprolith.corroboration import EngineCorroboration

    def bound(distance: float) -> float:
        return EngineCorroboration(
            species="X", engines=("copasi", "roadrunner"), distance=distance, stable=True
        ).distance_bound()

    assert bound(2.328e-06) == bound(2.143e-06) == 3e-06  # the pair that moved 8% between runs
    assert bound(3.2e-04) == 4e-04
    assert bound(1.0e-05) == 1e-05  # already one figure: unchanged, never rounded down
    assert bound(0.0) == 0.0

    # And it is genuinely an upper bound on every model in the committed corpus.
    committed = json.loads((_KIN / "milestone" / "corroboration.json").read_text())
    for model_id, record in committed.items():
        spec = _MODELS[model_id]
        result = corroborate_curve(
            (_KIN / f"{model_id}.xml").read_text(encoding="utf-8"),
            spec["species"], duration=spec["duration"], steps=spec["steps"],
        )
        assert result.distance <= record["distance_at_most"]
