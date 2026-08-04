"""Cross-engine corroboration: is a curve verdict the model's, or one solver's quirk?

A single simulator can reproduce a paper for the wrong reason — a solver-specific integration
artifact. Running the *same* SBML model under two independently-implemented engines and checking
they produce the same trajectory separates a model's behavior from a single engine's quirks
(spec: ``simulation-oracle`` — engine-sensitivity). When they agree, the verdict is
engine-independent; when they diverge beyond tolerance, the result is **engine-sensitive** and a
verdict resting on one engine should be treated as such (the ``ENGINE_SENSITIVITY`` failure mode).

This uses the pinned COPASI engine and the libRoadRunner engine (CVODE), which share no code, so
agreement is real corroboration. Both are optional: it needs the ``engine`` and ``corroborate``
extras and imports them lazily.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine import ENGINE as _COPASI_ENGINE
from .engine import ROADRUNNER_ENGINE, simulate, simulate_with_roadrunner
from .oracle import normalized_curve_distance


@dataclass(frozen=True)
class EngineCorroboration:
    """The result of running one curve under two engines and comparing the trajectories."""

    species: str
    engines: tuple[str, str]
    distance: float
    stable: bool

    def summary(self) -> str:
        verdict = "engine-independent" if self.stable else "engine-sensitive"
        return (
            f"{self.species}: {self.engines[0]} vs {self.engines[1]} normalized distance "
            f"{self.distance:.4g} -> {verdict}"
        )


def corroborate_curve(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
    rel_tol: float = 0.02,
) -> EngineCorroboration:
    """Run a species curve under both engines and report whether the verdict is engine-independent.

    Simulates ``species`` over ``[0, duration]`` at ``steps`` intervals under both COPASI and
    libRoadRunner (same grid, so the curves align), then measures their normalized distance. A
    distance at or below ``rel_tol`` means the two independent engines agree — the curve is the
    model's behavior, not one solver's; above it, the result is engine-sensitive and should be
    flagged rather than trusted to a single engine.
    """
    _, copasi_values = simulate(sbml, species, duration=duration, steps=steps)
    _, roadrunner_values = simulate_with_roadrunner(sbml, species, duration=duration, steps=steps)
    distance = normalized_curve_distance(copasi_values, roadrunner_values)
    return EngineCorroboration(
        species=species,
        engines=(_COPASI_ENGINE, ROADRUNNER_ENGINE),
        distance=distance,
        stable=distance <= rel_tol,
    )


__all__ = ["EngineCorroboration", "corroborate_curve"]
