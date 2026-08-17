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

import math
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
            f"at most {self.distance_bound():.0e} -> {verdict}"
        )

    def distance_bound(self) -> float:
        """The distance rounded *up* to one significant figure — what is safe to publish.

        The distance between two engines that agree is a difference of nearly-equal numbers, so
        its leading digits are the engines' own last-place noise amplified. COPASI is not
        bit-identical across repeated calls in one process (a period-2 alternation at about 1e-11
        relative, present on four of the six committed kinetic models), and on one of them that
        moved the published distance by 8% — so a five-figure distance in a committed artifact
        reads as a measurement and is not reproducible even on the same machine.

        Rounding up rather than to nearest keeps the number honest under the only reading that
        matters: it never states better agreement than was measured.
        """
        if not math.isfinite(self.distance) or self.distance <= 0.0:
            return self.distance
        exponent = math.floor(math.log10(self.distance))
        scale = 10.0**exponent
        # Re-parsed from its own one-figure rendering, so the published number is the short
        # decimal it prints as rather than the binary noise of ceil-times-scale (3e-05, not
        # 3.0000000000000004e-05).
        return float(f"{math.ceil(self.distance / scale) * scale:.0e}")


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
