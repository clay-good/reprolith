"""The fixed verdict and status vocabularies.

These mirror the vocabularies defined in the specs (``simulation-oracle``,
``reproduction-certificate``). They are closed sets on purpose: a verdict is never a
free-form string, so tooling and humans read the same words everywhere.
"""

from __future__ import annotations

from enum import Enum


class MetricDimension(str, Enum):
    """What kind of quantity a metric read off a trajectory *is*.

    Three modules have to agree about this and used to state it three times. The unit a claim's
    number is read in is composed from it (`reprolith.claim_units`); which of a paper's table
    columns names that unit is matched with it; and the engine dispatches on the metric name
    itself. A metric classified in one place and not another is the defect this exists to prevent:
    an oscillation's **period** was added to the dispatcher and left out of the unit rule, which
    then composed a *concentration* for a number a paper prints in hours.
    """

    #: Read entirely in the run's own clock — a time to peak, an oscillation's period.
    TIME = "time"
    #: The output's own unit times the clock — an area under a curve.
    OUTPUT_TIMES_TIME = "output-times-time"
    #: The output's own unit — a peak, an end value, a peak-to-trough height.
    OUTPUT = "output"


#: Every metric a claim may read off a trajectory, and what kind of quantity each one is. The
#: single source of truth: `reprolith.certify._metric` computes exactly these names,
#: `reprolith.claim_units` composes a unit from the dimension, and the table-column vocabulary in
#: `reprolith.claim_candidates` proposes only names that appear here.
METRIC_DIMENSIONS: dict[str, MetricDimension] = {
    "cmax": MetricDimension.OUTPUT,
    "tmax": MetricDimension.TIME,
    "auc": MetricDimension.OUTPUT_TIMES_TIME,
    "final": MetricDimension.OUTPUT,
    "period": MetricDimension.TIME,
    "peak_to_trough": MetricDimension.OUTPUT,
}


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
    LOGICAL = "logical"
    STOCHASTIC = "stochastic"
    SPATIAL = "spatial"
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
