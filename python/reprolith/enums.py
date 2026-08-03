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
