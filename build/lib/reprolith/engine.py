"""Running a reconstruction under the pinned registered engine (bootstrap task 0.1).

The MVP pins COPASI — a BioSimulators-registered simulation engine — driven headless and
deterministically through ``python-copasi``. A reconstruction bundle is only meaningful
alongside its pin: the same SBML model, run under the same engine and version, must return the
same numbers, so anyone can re-run the bundle and reproduce a certificate (spec:
``model-reconstruction`` — "Determinism and pinning").

This is the one place a real third-party engine is used, so it is an **optional** dependency:
the rest of the engine (catalog, oracle, certificate) stays dependency-free and the fast
required-checks gate does not need COPASI. ``COPASI`` is imported lazily inside the functions
below, and its absence raises a clear :class:`EngineUnavailable` rather than breaking import of
the package. Install it with the ``engine`` extra.
"""

from __future__ import annotations

import math
from typing import Any

from .model import EnginePin

ENGINE = "copasi"
ALGORITHM = "deterministic-lsoda"

# A second, independently-implemented registered engine, used for cross-engine corroboration
# (spec: simulation-oracle — engine-sensitivity). libRoadRunner shares no code with COPASI, so
# agreement between the two separates a model's behavior from a single solver's quirks.
ROADRUNNER_ENGINE = "roadrunner"
ROADRUNNER_ALGORITHM = "cvode"


class EngineUnavailable(RuntimeError):
    """Raised when a simulation is requested but the optional engine is not installed."""


class NonFiniteSimulation(RuntimeError):
    """Raised when a model diverges under the pin (inf/nan) — intractable, so blocked not failed."""


def _copasi() -> Any:
    try:
        import COPASI
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise EngineUnavailable(
            "the pinned engine is not installed; install the 'engine' extra "
            "(pip install 'reprolith[engine]')"
        ) from exc
    return COPASI


def engine_version() -> str:
    """The version string of the installed pinned engine."""
    return str(_copasi().CVersion.VERSION.getVersion())


def engine_pin() -> EnginePin:
    """The :class:`~reprolith.model.EnginePin` for the installed pinned engine."""
    return EnginePin(engine=ENGINE, version=engine_version(), algorithm=ALGORITHM)


def simulate(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Simulate an SBML model under the pinned engine and return a ``species`` time course.

    Runs a deterministic time course over ``[0, duration]`` at ``steps`` uniform intervals and
    returns ``(times, values)`` for the named species. Deterministic: the same SBML and
    arguments return byte-identical series, so the result can feed the oracle as a
    reproducible reconstruction output.
    """
    copasi = _copasi()
    datamodel = copasi.CRootContainer.addDatamodel()
    try:
        if not datamodel.importSBMLFromString(sbml):
            raise ValueError("the pinned engine could not import the SBML model")

        task = datamodel.getTask("Time-Course")
        task.setMethodType(copasi.CTaskEnum.Method_deterministic)
        task.setScheduled(True)

        problem = task.getProblem()
        problem.setAutomaticStepSize(False)
        problem.setOutputStartTime(0.0)
        problem.setDuration(float(duration))
        problem.setStepNumber(int(steps))

        task.initialize(copasi.CCopasiTask.OUTPUT_UI)
        task.process(True)

        series = task.getTimeSeries()
        column = _species_column(series, species, datamodel)
        recorded = series.getRecordedSteps()
        # The output grid is uniform over [0, duration], so the sample times are known
        # exactly; taking them from the grid avoids depending on the engine's time column.
        times = tuple(float(duration) * i / int(steps) for i in range(recorded))
        values = tuple(float(series.getConcentrationData(i, column)) for i in range(recorded))
        return times, require_finite(values, species)
    finally:
        copasi.CRootContainer.removeDatamodel(datamodel)


def _roadrunner() -> Any:
    try:
        import roadrunner
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise EngineUnavailable(
            "the roadrunner corroboration engine is not installed; install the 'corroborate' extra "
            "(pip install 'reprolith[corroborate]')"
        ) from exc
    return roadrunner


def roadrunner_version() -> str:
    """The version string of the installed libRoadRunner corroboration engine."""
    return str(_roadrunner().__version__)


def roadrunner_pin() -> EnginePin:
    """The :class:`~reprolith.model.EnginePin` for the libRoadRunner corroboration engine."""
    return EnginePin(engine=ROADRUNNER_ENGINE, version=roadrunner_version(), algorithm=ROADRUNNER_ALGORITHM)


def simulate_with_roadrunner(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Simulate an SBML model under libRoadRunner and return a ``species`` time course.

    The independent-engine counterpart of :func:`simulate`, with the same ``(times, values)`` shape
    and the same uniform grid over ``[0, duration]``, so the two engines' outputs are directly
    comparable for cross-engine corroboration. Needs the ``corroborate`` extra (libRoadRunner).
    """
    roadrunner = _roadrunner()
    runner = roadrunner.RoadRunner(sbml)
    runner.timeCourseSelections = ["time", species]
    result = runner.simulate(0.0, float(duration), int(steps) + 1)
    times = tuple(float(duration) * i / int(steps) for i in range(len(result)))
    values = tuple(float(row[1]) for row in result)
    return times, require_finite(values, species)


def require_finite(values: tuple[float, ...], species: str) -> tuple[float, ...]:
    """Return ``values`` unless any is non-finite (inf/nan), in which case raise.

    A diverging or too-stiff model produces inf/nan; signalling it lets the caller record the
    entry as blocked (intractable), not failed, rather than pass garbage numbers downstream.
    """
    if not all(math.isfinite(v) for v in values):
        raise NonFiniteSimulation(
            f"the model did not produce a finite result for {species!r} under the pin "
            "(diverged or too stiff)"
        )
    return values


def _species_column(series: Any, name: str, datamodel: Any) -> int:
    # Resolve by SBML id first: real models often reuse the same display name across
    # several species (the column title is then ambiguous), but the SBML id is unique.
    for i in range(series.getNumVariables()):
        if series.getSBMLId(i, datamodel) == name:
            return i
    for i in range(series.getNumVariables()):
        if series.getTitle(i) == name:
            return i
    raise ValueError(f"species {name!r} is not an output of the model")


__all__ = [
    "ALGORITHM",
    "ENGINE",
    "ROADRUNNER_ALGORITHM",
    "ROADRUNNER_ENGINE",
    "EngineUnavailable",
    "NonFiniteSimulation",
    "engine_pin",
    "engine_version",
    "roadrunner_pin",
    "roadrunner_version",
    "simulate",
    "simulate_with_roadrunner",
]
