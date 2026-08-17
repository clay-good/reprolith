"""Certifying a model against extracted claims (the pipeline's oracle-to-certificate glue).

Given a runnable model (SBML), the paper it came from, and the claims extracted from that paper,
this runs each claim under the pinned engine, derives the claimed quantity, judges it against the
reported value with the oracle, and assembles a certificate. It is the reusable form of the
metformin worked example: the same machinery that produced one certificate produces any, driven
by a list of :class:`Claim` specs.

A claim that reproduces only because of a load-bearing assumption is marked ``assumption_qualified``
so the certificate cannot round it up. A claim expected to possibly fall short must carry its
root-cause :class:`~reprolith.oracle.Attribution`; the oracle refuses a bare non-pass verdict.

Uses the optional ``engine`` extra (COPASI to run, libsbml to apply parameter overrides).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .certificate import build_certificate
from .engine import simulate
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    PercentileBand,
    ReferenceKind,
    Tolerance,
    judge_curve,
    judge_distribution,
    judge_estimation,
    judge_scalar,
)


@dataclass(frozen=True)
class Claim:
    """A published scalar claim to check: a quantity, where to read it, and its reported value.

    ``species`` is the model output to read; ``metric`` derives the scalar from that output's
    time course (``cmax`` peak, ``auc`` area, or ``final`` end value). ``parameter_overrides``
    set the claim's protocol (e.g. a dose) before running. ``assumption_qualified`` marks a
    claim whose reproduction rests on a load-bearing assumption; ``shortfall`` supplies the
    root cause a non-pass verdict requires.
    """

    claim_id: str
    quantity: str
    species: str
    reported: float
    source_location: str
    metric: str = "cmax"
    parameter_overrides: tuple[tuple[str, float], ...] = ()
    tolerance: Tolerance | None = None
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Claim:
        """Build a claim from a plain dict (a claims-dataset record).

        ``parameter_overrides`` may be given as a ``{name: value}`` mapping; ``reference_kind``
        as its string value. The engine-facing fields (``tolerance``, ``shortfall``) are not
        parsed here — dataset claims are the reproducing, default-tolerance case.
        """
        overrides = record.get("parameter_overrides", {})
        return cls(
            claim_id=record["claim_id"],
            quantity=record["quantity"],
            species=record["species"],
            reported=float(record["reported"]),
            source_location=record["source_location"],
            metric=record.get("metric", "cmax"),
            parameter_overrides=tuple((k, float(v)) for k, v in overrides.items()),
            reference_kind=ReferenceKind(record.get("reference_kind", "numeric")),
            assumption_qualified=bool(record.get("assumption_qualified", False)),
        )


def _metric(times: Sequence[float], values: Sequence[float], metric: str) -> float:
    if metric == "cmax":
        return max(values)
    if metric == "final":
        return values[-1]
    if metric == "auc":
        return sum(
            (values[i] + values[i + 1]) / 2.0 * (times[i + 1] - times[i])
            for i in range(len(values) - 1)
        )
    raise ValueError(f"unknown metric {metric!r} (use cmax, auc, or final)")


def _apply_overrides(sbml: str, overrides: tuple[tuple[str, float], ...]) -> str:
    from .sbml import _libsbml

    libsbml = _libsbml()  # the typed error that names the extra, not a bare ImportError

    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    for name, value in overrides:
        parameter = model.getParameter(name)
        if parameter is None:
            raise ValueError(f"parameter {name!r} is not in the model")
        parameter.setValue(float(value))
    return str(libsbml.writeSBMLToString(document))


def certify_model(
    sbml: str,
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[Claim],
    assumptions: Iterable[Assumption] = (),
    duration: float,
    steps: int = 480,
) -> Certificate:
    """Run each claim under the pin, judge it, and assemble the certificate.

    The overall verdict is derived by the certificate rule, so a certificate resting on a
    load-bearing assumption cannot report an unqualified ``reproduced``.
    """
    assessments = []
    for claim in claims:
        model = _apply_overrides(sbml, claim.parameter_overrides) if claim.parameter_overrides else sbml
        times, values = simulate(model, claim.species, duration=duration, steps=steps)
        predicted = _metric(times, values, claim.metric)
        assessments.append(
            judge_scalar(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reported=claim.reported,
                predicted=predicted,
                reference_kind=claim.reference_kind,
                tolerance=claim.tolerance,
                attribution=claim.shortfall,
                assumption_qualified=claim.assumption_qualified,
            )
        )
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


@dataclass(frozen=True)
class CurveClaim:
    """A published time-course to reproduce: a species curve judged by normalized distance.

    Unlike :class:`Claim` (a scalar metric), the whole trajectory is the claim. ``reference`` holds
    the reported values sampled at the same ``steps + 1`` uniform points over ``[0, duration]`` the
    simulation produces, so the oracle compares like with like. This is the curve counterpart of the
    scalar claim and the natural claim shape for the generic-kinetic class, where the reproducible
    result is the dynamics themselves.
    """

    claim_id: str
    quantity: str
    species: str
    reference: tuple[float, ...]
    source_location: str
    duration: float
    steps: int
    tolerance: Tolerance | None = None
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC
    parameter_overrides: tuple[tuple[str, float], ...] = ()
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)


def certify_curves(
    sbml: str,
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[CurveClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Run each curve claim under the pin, judge its trajectory, and assemble the certificate.

    The curve counterpart of :func:`certify_model`: it reproduces a whole species time-course with
    the shared curve oracle (:func:`reprolith.judge_curve`) instead of a scalar metric, and builds
    the certificate through the same rule and scope flag. Each claim carries its own ``duration``
    and ``steps``, so the reference and the simulation are sampled at identical points.
    """
    assessments = []
    for claim in claims:
        model = _apply_overrides(sbml, claim.parameter_overrides) if claim.parameter_overrides else sbml
        _, values = simulate(model, claim.species, duration=claim.duration, steps=claim.steps)
        assessments.append(
            judge_curve(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reference=claim.reference,
                predicted=values,
                reference_kind=claim.reference_kind,
                tolerance=claim.tolerance,
                attribution=claim.shortfall,
                assumption_qualified=claim.assumption_qualified,
            )
        )
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


@dataclass(frozen=True)
class EstimationClaim:
    """A published *parameter estimate* to reproduce by re-fitting from the paper's raw data.

    The estimation counterpart of :class:`Claim`. ``reported`` is the paper's stated estimate and
    ``recovered`` is the estimate Reprolith's re-fit produced; the re-fitting itself — running the
    paper's stated estimation over the shipped raw data — is the deferred, engine-dependent half,
    exactly as the simulator is for a scalar claim, so this glue takes an already-``recovered``
    value. ``shortfall`` supplies the root cause a non-pass estimation verdict requires.
    """

    claim_id: str
    quantity: str
    reported: float
    recovered: float
    source_location: str
    tolerance: Tolerance | None = None
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)


def certify_estimation(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[EstimationClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Assemble a certificate of estimation verdicts (re-fit estimates vs reported estimates).

    The estimation counterpart of :func:`certify_model`: each claim is judged with
    :func:`reprolith.judge_estimation`, so every verdict is recorded at the estimation
    reproduction level and reported separately from simulation. Needs no engine extra — the
    re-derived estimates are supplied, the re-fitter being the deferred half.
    """
    assessments = [
        judge_estimation(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.reported,
            recovered=claim.recovered,
            tolerance=claim.tolerance,
            attribution=claim.shortfall,
            assumption_qualified=claim.assumption_qualified,
        )
        for claim in claims
    ]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


@dataclass(frozen=True)
class PopulationClaim:
    """A published population figure to reproduce: a percentile envelope over time.

    The population counterpart of :class:`CurveClaim`. ``reported`` and ``predicted`` are the
    paper's and the simulated population's percentile bands (median plus outer percentiles);
    simulating a virtual population is the deferred, engine-and-sampling half, so this glue takes
    the already-``predicted`` bands. ``assumption_qualified`` defaults to ``True`` because a
    population reproduction depends on the reconstructed variability model and the sampling, so its
    verdict is qualified unless the paper fully specifies both.

    ``protocol`` records the sampling the bands came from — how many subjects were simulated and
    under what seed. An envelope's verdict moves with its ensemble size (a correct model reads as
    failed at twenty subjects, and a wrong one passes at a thousand), so without the protocol a
    reader cannot tell a reproduction from a sample size chosen until one appeared. The stochastic
    class records the same thing for the same reason.
    """

    claim_id: str
    quantity: str
    reported: tuple[PercentileBand, ...]
    predicted: tuple[PercentileBand, ...]
    source_location: str
    tolerance: Tolerance | None = None
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)
    protocol: str | None = None


def certify_population(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[PopulationClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Assemble a certificate of population-envelope verdicts (reported vs simulated bands).

    The population counterpart of :func:`certify_curves`: each claim is judged with
    :func:`reprolith.judge_distribution` — governed by its worst-matched percentile band and
    qualified by default — so a reproduced population figure yields a partially-reproduced
    certificate. Needs no engine extra: the simulated bands are supplied, the population
    simulation being the deferred half.

    Each assessment carries the claim's sampling ``protocol`` when it states one, because a
    distributional verdict rests on the ensemble that produced the bands as much as on the model.
    """
    assessments = [
        replace(
            judge_distribution(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reference=claim.reported,
                predicted=claim.predicted,
                reference_kind=claim.reference_kind,
                tolerance=claim.tolerance,
                attribution=claim.shortfall,
                assumption_qualified=claim.assumption_qualified,
            ),
            protocol=claim.protocol,
        )
        for claim in claims
    ]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


__all__ = [
    "Claim",
    "CurveClaim",
    "EstimationClaim",
    "PopulationClaim",
    "certify_curves",
    "certify_estimation",
    "certify_model",
    "certify_population",
]
