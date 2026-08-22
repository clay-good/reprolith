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


def _judge_revision() -> str:
    """The revision of the code that decides what this engine's numbers mean.

    An external engine carries its own version, so the solver half of the pin already moves when
    the solver does. The judge half did not: a class-default tolerance in :mod:`reprolith.oracle`
    and the rule in :mod:`reprolith.certificate` decide the verdict, and changing either
    invalidated every COPASI and libRoadRunner certificate while leaving them looking fresh —
    the same failure :mod:`reprolith.pins` was written to remove, applied to the four classes
    Reprolith solves itself but not to the two it does not.

    It spans the glue as well as the judge. Between an external solver and the verdict rule sit two
    Reprolith modules that decide *which number is judged*: this one resolves the sampling grid and
    the species column (it once returned amounts where concentrations were meant — off by exactly
    the compartment volume), and :mod:`reprolith.certify` derives Cmax, AUC and final value from the
    trajectory. A change to either can flip a verdict without moving the solver's version or the
    judge's revision, which left every affected certificate reading fresh. Every self-solved class
    already pins its own analysis layer this way; these two now do too.
    """
    from .pins import algorithm_revision

    return algorithm_revision("engine", "certify", "oracle", "certificate")


def engine_pin() -> EnginePin:
    """The :class:`~reprolith.model.EnginePin` for the installed pinned engine."""
    return EnginePin(
        engine=ENGINE,
        version=engine_version(),
        algorithm=f"{ALGORITHM} (judge rev {_judge_revision()})",
    )


def _require_advancing_run(duration: float, steps: int) -> None:
    """Refuse a time course that cannot advance.

    A run of zero (or negative, or non-finite) duration returns the initial condition and
    nothing else, and the metric layer then reads that initial condition as the model's Cmax or
    final value — a claim stated at its own starting point judges as reproduced against a
    trajectory that never happened. ``steps`` of zero divides by zero when the grid is built.
    Both are refused here, at the one boundary every certified time course passes through.
    """
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError(f"duration must be a positive finite number of time units, not {duration!r}")
    if int(steps) < 1:
        raise ValueError(f"a time course needs at least one step, not {steps!r}")


def simulate(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Simulate an SBML model under the pinned engine and return a ``species`` time course.

    Runs a deterministic time course over ``[0, duration]`` at ``steps`` uniform intervals and
    returns ``(times, values)`` for the named species — a deterministic *method*, not a stochastic
    one, so the result can feed the oracle as a reproducible reconstruction output.

    It is not bit-identical, and this used to claim it was. Repeated calls on one model in one
    process alternate between two series with call parity, differing by about 1e-11 relative, on
    four of the six committed kinetic models. The cause is inside the engine, not in how this
    function manages its datamodel: adding and removing one per call alternates, never removing
    them settles after two calls, and reusing a single datamodel gives five distinct results in
    six calls. Nothing downstream reports at that precision — a certificate's discrepancy is four
    decimals — but a caller publishing raw engine output should round to a precision the engine
    reproduces, the way :meth:`reprolith.corroboration.EngineCorroboration.distance_bound` does.
    """
    _require_advancing_run(duration, steps)
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
        completed = task.process(True)

        series = task.getTimeSeries()
        column = _species_column(series, species, datamodel)
        recorded = series.getRecordedSteps()
        # The engine reports a run it abandoned — step-limit exceeded, integration failure — by
        # returning False and recording the samples it did reach, and every one of those samples
        # is finite, so require_finite's sibling check cannot see it. Read as-is, a run that
        # stopped at t=5 of 100 hands the metric layer a Cmax over 5% of the window while the
        # protocol published beside it names the full duration; a scalar claim stated at the end
        # of the course then judges as reproduced at relative error 0.0000 against a trajectory
        # that never got there. Curve claims are caught downstream by the oracle's sample-count
        # check; scalar claims — the whole PK/PD class — are not. An abandoned run is intractable,
        # which is the blocked-not-failed case this module already signals for divergence.
        if not completed or recorded != int(steps) + 1:
            # The time the engine actually reached, read from its own time column rather than
            # inferred from the grid: COPASI appends a duplicate final row when it abandons a
            # course, so `duration * (recorded - 1) / steps` overstated the stopping point by
            # exactly one grid step every time — and this text reaches an agent verbatim through
            # the MCP lint tools, erring in the direction of "the run got further than it did".
            reached = float(series.getData(recorded - 1, 0)) if recorded else 0.0
            raise NonFiniteSimulation(
                f"the pinned engine did not complete the time course for {species!r}: it stopped "
                f"at t={reached} of {float(duration)} ({recorded} of {int(steps) + 1} samples)"
            )
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
    return EnginePin(
        engine=ROADRUNNER_ENGINE,
        version=roadrunner_version(),
        algorithm=f"{ROADRUNNER_ALGORITHM} (judge rev {_judge_revision()})",
    )


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

    The selection is ``[species]``, the **concentration**, because :func:`simulate` reads COPASI's
    concentration data. A bare species id in libRoadRunner is the amount, so the two engines were
    reporting different physical quantities: identical for the compartment size of 1 every
    committed model happens to have, and off by exactly the volume for any model with a real
    compartment. That made a perfectly engine-independent model look engine-sensitive, and would
    have minted reference curves in the wrong units.
    """
    _require_advancing_run(duration, steps)
    roadrunner = _roadrunner()
    runner = roadrunner.RoadRunner(sbml)
    runner.timeCourseSelections = ["time", f"[{species}]"]
    result = runner.simulate(0.0, float(duration), int(steps) + 1)
    # The same short-run check :func:`simulate` makes, for the same reason: this engine's output
    # is what a corroboration distance is measured against, and a run that returned fewer samples
    # than it was asked for would set that distance over a window the model never crossed.
    if len(result) != int(steps) + 1:
        reached = float(duration) * max(len(result) - 1, 0) / int(steps)
        raise NonFiniteSimulation(
            f"the corroboration engine did not complete the time course for {species!r}: it "
            f"stopped at t={reached} of {float(duration)} ({len(result)} of {int(steps) + 1} samples)"
        )
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
