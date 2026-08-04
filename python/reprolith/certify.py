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
from dataclasses import dataclass, field
from typing import Any

from .certificate import build_certificate
from .engine import simulate
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import Attribution, ReferenceKind, Tolerance, judge_scalar


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
    import libsbml

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


__all__ = ["Claim", "certify_model"]
