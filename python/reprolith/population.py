"""Simulating a virtual population: the deferred half of a population reproduction.

Many PK/PD and QSP figures are not a single trajectory but an **envelope** — a median with outer
percentiles across a simulated population (catalog-backlog roadmap #7). The oracle for those
landed first: :func:`reprolith.judge_distribution` compares reported bands to simulated ones, and
:func:`reprolith.certify_population` assembles the certificate. Both took the simulated bands as
given, because producing them — sampling a between-subject variability model and running the
ensemble — was deferred. This is that half.

It computes nothing the caller cannot check. A population is a set of parameter draws and one
deterministic run per draw, so the whole thing rests on three choices that are stated rather than
assumed, and that a reader has to be able to re-derive:

* **The variability model.** Each varied parameter is multiplied by ``exp(eta)`` with
  ``eta ~ Normal(0, omega**2)`` — the pharmacometric convention, in which the population *median*
  is the model's own value and ``omega`` relates to the coefficient of variation by
  ``omega = sqrt(ln(1 + cv**2))``. It is median-preserving, not mean-preserving: the population
  mean is ``exp(omega**2 / 2)`` times the typical value, which is a real difference at a CV of 50%
  and is the convention the literature reports.
* **The draws.** Uniform variates come from :class:`random.Random` seeded by the caller and are
  turned into normal ones through :meth:`statistics.NormalDist.inv_cdf`, an explicit inverse CDF
  rather than a sampler whose internal state could change between interpreter versions. Same seed,
  same population, on any machine.
* **The percentile.** Linearly interpolated between order statistics (the definition NumPy and R
  type 7 use). Definitions disagree materially at small ensembles — nearest-rank puts P5 of twenty
  subjects on the minimum — so the one in force is named here and in the protocol string.

Parameters vary independently. A correlated variability model (a covariance matrix over etas) is
not supported and is not approximated by independent draws, which would understate the width of
every band whose parameters move together.

Needs the ``engine`` extra: each subject is a run through :func:`reprolith.simulate`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist

from .engine import simulate
from .oracle import PercentileBand


@dataclass(frozen=True)
class SubjectVariability:
    """Between-subject variability on one model parameter, as a log-normal multiplier.

    ``cv`` is the coefficient of variation of that multiplier — 0.3 for the "30% CV" a paper
    typically reports — and is converted to the log-scale ``omega`` the draws use.
    """

    parameter: str
    cv: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.cv) or self.cv <= 0.0:
            raise ValueError(
                f"variability on {self.parameter!r} needs a positive coefficient of variation; "
                f"got {self.cv!r}. A parameter that does not vary is not a source of "
                "between-subject variability, it is a fixed value."
            )

    def omega(self) -> float:
        """The log-scale standard deviation this coefficient of variation corresponds to."""
        return math.sqrt(math.log(1.0 + self.cv**2))


@dataclass(frozen=True)
class PopulationRun:
    """A simulated population: its percentile bands, its time grid, and the sampling behind them."""

    times: tuple[float, ...]
    bands: tuple[PercentileBand, ...]
    #: What was sampled and how, in the form :class:`reprolith.PopulationClaim` requires — an
    #: envelope's verdict moves with its subject count and seed, so the bands are only evidence
    #: alongside them.
    protocol: str


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """The percentile of already-sorted values, linearly interpolated between order statistics."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _outermost(percentiles: tuple[float, ...]) -> float:
    """The band furthest from the median — the one whose sampling error is largest."""
    return max(percentiles, key=lambda p: abs(p - 50.0))


def percentile_sampling_error(*, cv: float, percentile: float, subjects: int) -> float:
    """The scale of a percentile band's own sampling error, as a fraction of the band.

    A population envelope is percentiles of a *finite* sample: draw the same population twice and
    the 5th percentile moves. That movement is not a disagreement with the paper, and nothing said
    how big it is — so an envelope of twenty subjects and one of a thousand were published in the
    same words, judged in the same band.

    This is the asymptotic standard error of a sample quantile, `sqrt(p(1-p)/n) / f(q_p)`, written
    out for the median-preserving log-normal these draws come from, which makes it a pure function
    of the CV, the percentile and the subject count. Measured against Monte-Carlo replicates in
    `tests/test_population_sampling_cost.py`: it agrees within a factor of two, and understates the
    tails at small N, so it is published as a scale and never as a bound.

    What it is for is the decision it informs. At a 30% CV and twenty subjects a *flawless*
    reproduction of the very population it is judged against misses the 15% pass budget about half
    the time; at fifty subjects, one time in eight; at two hundred and fifty, never in four hundred
    replicates. The subject count is not a free parameter.
    """
    if not 0.0 < percentile < 100.0:
        raise ValueError(
            f"a percentile band sits strictly inside (0, 100); got {percentile}"
        )
    if subjects < 2:
        raise ValueError(f"a population needs at least two subjects; got {subjects}")
    if cv <= 0.0:
        raise ValueError(f"a between-subject CV is positive; got {cv}")
    spread = math.sqrt(math.log(1.0 + cv * cv))
    fraction = percentile / 100.0
    z = NormalDist().inv_cdf(fraction)
    density = NormalDist().pdf(z)
    # d/dp of exp(spread * z_p) is exp(spread * z_p) * spread / phi(z_p), so the *relative* error
    # of the band drops the band's own value and leaves the spread over the normal density.
    return spread * math.sqrt(fraction * (1.0 - fraction) / subjects) / density


def simulate_population(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
    variability: tuple[SubjectVariability, ...],
    subjects: int,
    seed: int,
    percentiles: tuple[float, ...] = (5.0, 50.0, 95.0),
) -> PopulationRun:
    """Run a virtual population and return its percentile envelope over time.

    Draws ``subjects`` sets of parameter multipliers under ``seed``, applies each to a copy of the
    model, runs it through the pinned engine over ``[0, duration]`` at ``steps`` intervals, and
    reports the requested ``percentiles`` of the ensemble at each grid point. The module docstring
    states the variability model, the draw mechanism, and the percentile definition; all three are
    also written into :attr:`PopulationRun.protocol`, because an envelope read without them is a
    picture rather than a result.

    Every varied parameter goes through the same override path certification uses, so a parameter
    the model does not declare — or one whose value cannot reach the run, because a rule determines
    it or a kinetic law shadows it — is refused rather than sampled into a population that ignores
    it. That failure is silent by nature: the ensemble runs, the bands come out narrow and
    identical, and nothing says the variability never applied.

    Raises ``ValueError`` for an ensemble too small to have an envelope, for no variability at all,
    and for anything the override path refuses.
    """
    from .certify import _apply_overrides  # local: the engine extra is only needed on this path

    if subjects < 2:
        raise ValueError(
            f"a population needs at least two subjects to have an envelope; got {subjects}"
        )
    if not variability:
        raise ValueError(
            "no parameter varies, so every subject is the same run: that is a single trajectory, "
            "not a population, and reporting it as bands would state a spread that is not there"
        )
    if not percentiles:
        raise ValueError("a population run must report at least one percentile band")
    outside = [p for p in percentiles if not 0.0 < p < 100.0]
    if outside:
        # Refused here rather than left to PercentileBand: by then the whole ensemble has run, and
        # the error would name the band instead of the argument that was wrong.
        raise ValueError(
            f"percentiles must be in the open interval (0, 100); got {outside}. The 0th and 100th "
            "are the ensemble's extremes, which are properties of its size rather than of the "
            "population."
        )
    repeated = sorted({
        spec.parameter for spec in variability
        if [s.parameter for s in variability].count(spec.parameter) > 1
    })
    if repeated:
        # Two specs for one parameter apply as two overrides, and the later one wins — so the
        # earlier draw is silently discarded and the published CV is not the one in force.
        raise ValueError(
            "each parameter may carry one variability spec; repeated: " + ", ".join(repeated)
        )

    draws = random.Random(seed)
    standard = NormalDist()
    # Read once, not once per subject: the model does not change between draws, and re-parsing it
    # for every subject turns a thousand-subject run into a thousand model parses.
    typical = {spec.parameter: _typical(sbml, spec.parameter) for spec in variability}
    # Validate every varied parameter once, before any subject runs. The override path refuses a
    # value that cannot reach the run — one a rule or initial assignment determines, one a kinetic
    # law shadows — and finding that out on the first subject would waste the ensemble; finding it
    # out never is the silent failure this guards: every subject identical, the bands one line,
    # and nothing saying the variability was discarded.
    _apply_overrides(sbml, tuple((name, value) for name, value in typical.items()))
    # One row per subject, one column per grid point. Drawn subject-by-subject and parameter-by-
    # parameter in declared order, so the sequence a seed produces is fixed by the inputs alone.
    trajectories: list[tuple[float, ...]] = []
    times: tuple[float, ...] = ()
    for _ in range(subjects):
        overrides = tuple(
            (spec.parameter, typical[spec.parameter] * math.exp(
                spec.omega() * standard.inv_cdf(draws.random())
            ))
            for spec in variability
        )
        times, values = simulate(
            _apply_overrides(sbml, overrides), species, duration=duration, steps=steps
        )
        trajectories.append(values)

    bands = tuple(
        PercentileBand(
            percentile=percentile,
            curve=tuple(
                _percentile(sorted(row[i] for row in trajectories), percentile)
                for i in range(len(times))
            ),
        )
        for percentile in percentiles
    )
    varied = ", ".join(f"{s.parameter} (CV {s.cv:g})" for s in variability)
    return PopulationRun(
        times=times,
        bands=bands,
        protocol=(
            f"{subjects} subjects, seed {seed}, log-normal between-subject variability on "
            f"{varied}, median-preserving; percentiles linearly interpolated between order "
            f"statistics; duration={duration!r}, steps={int(steps)}, read=[{species}]; "
            # The band's own sampling error, from the widest-CV spec and the outermost band it
            # reports: an envelope of twenty subjects and one of a thousand read identically
            # without it, and are judged in the same tolerance.
            f"sampling error of the {_outermost(percentiles):g}th band ~"
            f"{percentile_sampling_error(cv=max(s.cv for s in variability), percentile=_outermost(percentiles), subjects=subjects):.0%} "
            f"of the band at {subjects} subjects"
        ),
    )


def _typical(sbml: str, parameter: str) -> float:
    """The model's own value for a parameter — the population median the draws multiply.

    Read from the model rather than taken from the caller: a variability spec that carried its own
    typical value could disagree with the model, and then the published envelope would be centred
    somewhere the model never was.
    """
    from .sbml import _libsbml

    libsbml = _libsbml()
    model = libsbml.readSBMLFromString(sbml).getModel()
    if model is None:
        raise ValueError("the artifact is not readable SBML")
    element = model.getParameter(parameter)
    if element is None:
        raise ValueError(
            f"the model declares no parameter {parameter!r} to vary between subjects"
        )
    if not element.isSetValue():
        # libSBML reports an unset value as 0.0, and a log-normal multiplier on zero is zero: every
        # subject would get the same value the model never stated, and the bands would collapse to
        # one flat line that looks like a population with no variability.
        raise ValueError(
            f"the model states no value for {parameter!r}, so there is no population median for "
            "the between-subject variability to be around"
        )
    return float(element.getValue())


__all__ = [
    "PopulationRun",
    "SubjectVariability",
    "percentile_sampling_error",
    "simulate_population",
]
