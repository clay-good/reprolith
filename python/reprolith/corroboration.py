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
from dataclasses import dataclass, replace

from .engine import ENGINE as _COPASI_ENGINE
from .engine import ROADRUNNER_ENGINE, simulate, simulate_with_roadrunner
from .oracle import normalized_curve_distance

#: How far a raw distance is lifted before it is rounded up to a decade. Two: the measured
#: cross-run spread on the model that exposed the problem was about 12%, and a factor of two keeps
#: a value that close to a boundary on the same side of it in every observation, at the cost of at
#: most one decade of looseness in the published bound.
_MARGIN = 2.0


@dataclass(frozen=True)
class EngineCorroboration:
    """The result of running one curve under two engines and comparing the trajectories."""

    species: str
    engines: tuple[str, str]
    distance: float
    stable: bool
    #: The tolerance the caller asked for. The verdict is decided on the *published* bound, so the
    #: criterion actually applied is :meth:`effective_criterion` — never looser than this, and up
    #: to five times tighter when this is not itself a power of ten.
    criterion: float = 0.02

    def effective_criterion(self) -> float:
        """The largest decade at or below :attr:`criterion` — what the verdict was really held to."""
        if not math.isfinite(self.criterion) or self.criterion <= 0.0:
            return self.criterion
        return 10.0 ** math.floor(math.log10(self.criterion))

    def summary(self) -> str:
        verdict = "engine-independent" if self.stable else "engine-sensitive"
        return (
            f"{self.species}: {self.engines[0]} vs {self.engines[1]} normalized distance "
            f"at most {self.distance_bound():.0e} against a {self.effective_criterion():.0e} "
            f"criterion -> {verdict}"
        )

    def distance_bound(self) -> float:
        """The distance rounded *up* to the next power of ten — what is safe to publish.

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
        # One significant figure was not coarse enough: the distance also moves between machines
        # (a committed 4e-07 bound was exceeded on CI at 4.55e-07, with different engine builds),
        # so the published granularity is the decade. It still says what the number is for —
        # agreement three to five orders below the tolerance — without pretending to digits no
        # second machine reproduces.
        #
        # The decade alone was not enough either, for a distance sitting near a boundary. Measured
        # on the metformin reconstruction: three runs of one milestone script on one machine
        # published 1e-06 twice and 1e-07 once, because the raw distance straddles 1e-07 (1.11e-07
        # in isolation, just under it inside a longer run). A committed number that moves a decade
        # between two runs is the very thing this method exists to prevent. So the distance is
        # lifted by a margin before it is rounded up: a value within a factor of `_MARGIN` of the
        # decade below is published at the decade above, and both draws land on the same number.
        # The change is one-directional by construction — the margin is greater than one, so the
        # published bound can only ever loosen, and it still never states better agreement than
        # was measured.
        return float(f"{10.0 ** math.ceil(math.log10(self.distance * _MARGIN)):.0e}")


def corroborate_curve(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
    rel_tol: float = 0.02,
    overrides: tuple[tuple[str, float], ...] = (),
) -> EngineCorroboration:
    """Run a species curve under both engines and report whether the verdict is engine-independent.

    Simulates ``species`` over ``[0, duration]`` at ``steps`` intervals under both COPASI and
    libRoadRunner (same grid, so the curves align), then measures their normalized distance. A
    published distance bound at or below ``rel_tol`` means the two independent engines agree — the
    curve is the model's behavior, not one solver's; above it, the result is engine-sensitive and
    should be flagged rather than trusted to a single engine. The criterion is applied to the
    *published* bound rather than the raw distance, so the record and its verdict never disagree.

    ``overrides`` are the parameter values the claim sets before running, in the same
    ``(name, value)`` form a certified claim carries — and they are applied through the same
    function certification uses, so an override that would not take effect is refused here too. A
    claim that runs at a non-default dose is otherwise uncorroborable: without them, the only arm
    a model's curves can be checked on is its default one, which for the metformin reconstruction
    is one of its two claims.
    """
    if overrides:
        from .certify import _apply_overrides

        sbml = _apply_overrides(sbml, overrides)
    _, copasi_values = simulate(sbml, species, duration=duration, steps=steps)
    _, roadrunner_values = simulate_with_roadrunner(sbml, species, duration=duration, steps=steps)
    distance = normalized_curve_distance(copasi_values, roadrunner_values)
    result = EngineCorroboration(
        species=species,
        engines=(_COPASI_ENGINE, ROADRUNNER_ENGINE),
        distance=distance,
        stable=False,
    )
    # The verdict answers to the number that is published, not the one that was measured. The
    # artifact records the distance rounded *up* to the next decade, so a raw 0.011 was published
    # as "at most 1e-01 -> engine-independent" against a 0.02 criterion — a record that contradicts
    # itself on its face. Judging the bound keeps the two in step and errs toward engine-sensitive.
    # It also means the criterion actually applied is the largest decade at or below ``rel_tol``
    # (0.01 for the 0.02 default), which is up to five times tighter than the number passed in —
    # so it is reported rather than left for a reader to derive. Every committed model measures at
    # most 1e-03, three orders inside even the tightened criterion.
    return replace(result, stable=result.distance_bound() <= rel_tol, criterion=rel_tol)


__all__ = ["EngineCorroboration", "corroborate_curve"]
