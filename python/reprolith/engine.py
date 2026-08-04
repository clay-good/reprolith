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

from typing import Any

from .model import EnginePin

ENGINE = "copasi"
ALGORITHM = "deterministic-lsoda"


class EngineUnavailable(RuntimeError):
    """Raised when a simulation is requested but the optional engine is not installed."""


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
        column = _species_column(series, species)
        recorded = series.getRecordedSteps()
        # The output grid is uniform over [0, duration], so the sample times are known
        # exactly; taking them from the grid avoids depending on the engine's time column.
        times = tuple(float(duration) * i / int(steps) for i in range(recorded))
        values = tuple(float(series.getConcentrationData(i, column)) for i in range(recorded))
        return times, values
    finally:
        copasi.CRootContainer.removeDatamodel(datamodel)


def _species_column(series: Any, name: str) -> int:
    for i in range(series.getNumVariables()):
        if series.getTitle(i) == name:
            return i
    raise ValueError(f"species {name!r} is not an output of the model")


__all__ = ["ALGORITHM", "ENGINE", "EngineUnavailable", "engine_pin", "engine_version", "simulate"]
