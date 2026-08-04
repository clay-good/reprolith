"""The domain shapes a certificate is built from.

These are the on-disk shapes the MVP foundation calls for (bootstrap task 0.2): a
paper identity, an engine pin, the assumptions Reprolith had to make, the per-claim
assessments the oracle produced, and the run metadata. Everything here is immutable
and serializes to plain JSON-able dicts, split into deterministic *content* and
non-deterministic *run metadata* so the two never get confused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import OverallVerdict, ReproductionLevel, Verdict
from .scope import Scope


@dataclass(frozen=True)
class PaperIdentity:
    """Who the certificate is about."""

    title: str
    doi: str | None = None
    pubmed_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "doi": self.doi, "pubmed_id": self.pubmed_id}


@dataclass(frozen=True)
class EnginePin:
    """The engine (and algorithm) a reconstruction is pinned to run under.

    The pin is part of the deterministic content: change the pin and you may change
    the numbers, so a certificate is only meaningful alongside it.
    """

    engine: str
    version: str
    algorithm: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"engine": self.engine, "version": self.version, "algorithm": self.algorithm}


@dataclass(frozen=True)
class Assumption:
    """A value or structural choice Reprolith supplied to close a dossier gap.

    Assumptions are always attributed to Reprolith, never to the paper. A
    ``load_bearing`` assumption is one that plausibly changes whether a claim
    reproduces; the certificate refuses to call such a claim an unqualified success.
    """

    id: str
    description: str
    chosen: str
    basis: str
    load_bearing: bool
    alternatives: tuple[str, ...] = ()
    attributed_to: str = "reprolith"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "chosen": self.chosen,
            "basis": self.basis,
            "load_bearing": self.load_bearing,
            "alternatives": list(self.alternatives),
            "attributed_to": self.attributed_to,
        }


@dataclass(frozen=True)
class ClaimAssessment:
    """The oracle's judgment of a single published claim.

    ``assumption_qualified`` records that this claim reproduced only because of a
    load-bearing assumption; the overall-verdict rule uses it to forbid an
    unqualified full reproduction.
    """

    claim_id: str
    quantity: str
    verdict: Verdict
    source_location: str
    level: ReproductionLevel = ReproductionLevel.SIMULATION
    method: str | None = None
    tolerance: str | None = None
    tolerance_source: str | None = None
    discrepancy: str | None = None
    root_cause: str | None = None
    reference_kind: str | None = None
    assumption_qualified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "quantity": self.quantity,
            "verdict": self.verdict.value,
            "source_location": self.source_location,
            "level": self.level.value,
            "method": self.method,
            "tolerance": self.tolerance,
            "tolerance_source": self.tolerance_source,
            "discrepancy": self.discrepancy,
            "root_cause": self.root_cause,
            "reference_kind": self.reference_kind,
            "assumption_qualified": self.assumption_qualified,
        }


@dataclass(frozen=True)
class RunMetadata:
    """When and by whom a certificate was produced.

    This is deliberately excluded from the deterministic content hash: two runs of
    the same inputs under the same pin differ only here, and must still be recognized
    as the same certificate.
    """

    created_at: str
    actor: str
    tool_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "actor": self.actor,
            "tool_version": self.tool_version,
        }


@dataclass(frozen=True)
class Certificate:
    """The deliverable: a per-claim, qualified, scope-flagged reproduction record.

    Build these with :func:`reprolith.certificate.build_certificate`, which derives
    the overall verdict by the stated rule and enforces the honesty invariants. The
    ``content`` view excludes run metadata so it hashes reproducibly.
    """

    paper: PaperIdentity
    engine_pin: EnginePin
    overall: OverallVerdict
    scope: Scope
    assessments: tuple[ClaimAssessment, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    gap_report: tuple[str, ...] = field(default=())
    supersedes: str | None = None

    def content(self) -> dict[str, Any]:
        """The deterministic content of the certificate (no run metadata).

        ``supersedes`` is the content digest of the prior certificate this one replaces
        (``None`` for a first certification); it is part of the content because a
        re-certification that links to a different predecessor is a genuinely different
        record.
        """
        return {
            "paper": self.paper.to_dict(),
            "engine_pin": self.engine_pin.to_dict(),
            "overall": self.overall.value,
            "scope": self.scope.to_dict(),
            "assessments": [a.to_dict() for a in self.assessments],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "gap_report": list(self.gap_report),
            "supersedes": self.supersedes,
        }

    def to_dict(self, run: RunMetadata) -> dict[str, Any]:
        """The full certificate: deterministic content plus this run's metadata."""
        return {"content": self.content(), "run": run.to_dict()}
