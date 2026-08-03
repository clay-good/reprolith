"""The fixed verdict and status vocabularies.

These mirror the vocabularies defined in the specs (``simulation-oracle``,
``reproduction-certificate``). They are closed sets on purpose: a verdict is never a
free-form string, so tooling and humans read the same words everywhere.
"""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    """A per-claim judgment from the simulation oracle."""

    REPRODUCED = "reproduced"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_EVALUABLE = "not-evaluable"


class OverallVerdict(str, Enum):
    """The certificate-level verdict, derived from per-claim verdicts."""

    REPRODUCED = "reproduced"
    PARTIALLY_REPRODUCED = "partially-reproduced"
    NOT_REPRODUCED = "not-reproduced"
    BLOCKED = "blocked"


class ReproductionLevel(str, Enum):
    """Which kind of reproduction a claim was evaluated at.

    Simulation reproduction (run the described model, check the shown output) is the
    primary target; estimation reproduction (re-fit from raw data) is reported
    separately.
    """

    SIMULATION = "simulation"
    ESTIMATION = "estimation"


class ModelClass(str, Enum):
    """The reproduction pathway an entry is routed to (spec: ``model-catalog`` —
    "Difficulty and class tagging").

    An entry whose class Reprolith does not yet support is retained as ``UNASSIGNED``
    backlog rather than discarded. The MVP only builds the ``ODE_PKPD`` pathway.
    """

    ODE_PKPD = "ode-pkpd"
    KINETIC = "kinetic"
    CONSTRAINT_BASED = "constraint-based"
    UNASSIGNED = "unassigned"


class LifecycleState(str, Enum):
    """The explicit, ordered lifecycle states a catalog entry moves through (spec:
    ``model-catalog`` — "Catalog entry lifecycle").

    ``CERTIFIED`` and ``FAILED`` are terminal only for a given engine-version pin; a
    new pin may re-open the entry. ``BLOCKED`` (a required input is missing) is kept
    distinct from ``FAILED`` (the attempt ran to completion but did not reproduce).
    """

    QUEUED = "queued"
    INGESTING = "ingesting"
    INGESTED = "ingested"
    RECONSTRUCTING = "reconstructing"
    RECONSTRUCTED = "reconstructed"
    VERIFYING = "verifying"
    CERTIFIED = "certified"
    FAILED = "failed"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"
