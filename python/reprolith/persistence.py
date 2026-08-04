"""Loading a certificate back from its stored content (design goal 3: inspectable files).

Certificates serialize to plain dicts via :meth:`Certificate.content`; this reconstructs one
from that dict, so a stored certificate can be re-opened, re-served, or re-hashed without the
inputs that produced it. The overall verdict is taken from the stored content exactly — a
loaded certificate must reproduce what was written, not re-derive it — so a round trip is
byte-identical: ``certificate_from_content(cert.content()).content() == cert.content()``.
"""

from __future__ import annotations

from typing import Any

from .enums import OverallVerdict, ReproductionLevel, Verdict
from .model import (
    Assumption,
    Certificate,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
)
from .scope import Scope


def _assessment_from(record: dict[str, Any]) -> ClaimAssessment:
    return ClaimAssessment(
        claim_id=record["claim_id"],
        quantity=record["quantity"],
        verdict=Verdict(record["verdict"]),
        source_location=record["source_location"],
        level=ReproductionLevel(record["level"]),
        method=record["method"],
        tolerance=record["tolerance"],
        tolerance_source=record["tolerance_source"],
        discrepancy=record["discrepancy"],
        root_cause=record["root_cause"],
        implicated=record["implicated"],
        fault_hypothesis=record["fault_hypothesis"],
        reference_kind=record["reference_kind"],
        assumption_qualified=record["assumption_qualified"],
    )


def _assumption_from(record: dict[str, Any]) -> Assumption:
    return Assumption(
        id=record["id"],
        description=record["description"],
        chosen=record["chosen"],
        basis=record["basis"],
        load_bearing=record["load_bearing"],
        alternatives=tuple(record["alternatives"]),
        attributed_to=record["attributed_to"],
    )


def certificate_from_content(content: dict[str, Any]) -> Certificate:
    """Reconstruct a :class:`Certificate` from the dict produced by :meth:`Certificate.content`."""
    paper = content["paper"]
    pin = content["engine_pin"]
    scope = content["scope"]
    return Certificate(
        paper=PaperIdentity(title=paper["title"], doi=paper["doi"], pubmed_id=paper["pubmed_id"]),
        engine_pin=EnginePin(engine=pin["engine"], version=pin["version"], algorithm=pin["algorithm"]),
        overall=OverallVerdict(content["overall"]),
        scope=Scope(machine=scope["machine"], human=scope["human"]),
        assessments=tuple(_assessment_from(a) for a in content["assessments"]),
        assumptions=tuple(_assumption_from(a) for a in content["assumptions"]),
        gap_report=tuple(content["gap_report"]),
        supersedes=content.get("supersedes"),
    )


__all__ = ["certificate_from_content"]
