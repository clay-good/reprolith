"""Reloading the inspectable artifacts from their stored dicts (design goal 3).

Every durable Reprolith artifact serializes to a plain dict via ``to_dict``/``content``; this
module reconstructs them, so a stored certificate, dossier, or reconstruction bundle can be
re-opened, re-served, or re-hashed without the inputs that produced it. Reconstruction is exact,
so a round trip is byte-identical — but not credulous: a certificate whose stored overall verdict
does not follow from its own stored evidence is refused, because the honesty invariants would
otherwise hold only for certificates built in-process and not for the ones read back off disk.
"""

from __future__ import annotations

from typing import Any

from .certificate import derive_overall
from .dossier import (
    Dossier,
    DossierClaim,
    Equation,
    ExtractionConfidence,
    Gap,
    GapKind,
    ModelArtifact,
    Parameter,
)
from .enums import OverallVerdict, ReproductionLevel, Verdict
from .model import (
    Assumption,
    Certificate,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
)
from .oracle import ReferenceKind
from .reconstruction import (
    ModelOrigin,
    NonReconstructable,
    RecipeStep,
    ReconstructionBundle,
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
        protocol=record.get("protocol"),  # present only on a sampled judgment
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
        verification_item=record.get("verification_item"),
    )


def certificate_from_content(content: dict[str, Any]) -> Certificate:
    """Reconstruct a :class:`Certificate` from the dict produced by :meth:`Certificate.content`.

    The stored overall verdict is re-derived from the stored assessments and assumptions, and a
    file whose verdict does not follow from its own evidence is refused rather than loaded. The
    honesty invariants are enforced when a certificate is *built*; without this check a hand-edited
    or corrupted file could carry a clean green ``reproduced`` over assumption-qualified claims all
    the way to the public registry, which reads certificates from disk and never rebuilds them.
    """
    paper = content["paper"]
    pin = content["engine_pin"]
    scope = content["scope"]
    assessments = tuple(_assessment_from(a) for a in content["assessments"])
    assumptions = tuple(_assumption_from(a) for a in content["assumptions"])
    stored = OverallVerdict(content["overall"])
    derived = derive_overall(assessments, assumptions)
    if stored is not derived:
        raise ValueError(
            f"certificate overall verdict {stored.value!r} does not follow from its own "
            f"assessments and assumptions (which give {derived.value!r})"
        )
    return Certificate(
        paper=PaperIdentity(title=paper["title"], doi=paper["doi"], pubmed_id=paper["pubmed_id"]),
        engine_pin=EnginePin(engine=pin["engine"], version=pin["version"], algorithm=pin["algorithm"]),
        overall=stored,
        scope=Scope(machine=scope["machine"], human=scope["human"]),
        assessments=assessments,
        assumptions=assumptions,
        gap_report=tuple(content["gap_report"]),
        supersedes=content.get("supersedes"),
    )


def _parameter_from(record: dict[str, Any]) -> Parameter:
    return Parameter(
        name=record["name"],
        value=record["value"],
        unit=record["unit"],
        source_location=record["source_location"],
        confidence=ExtractionConfidence(record["confidence"]),
    )


def dossier_from_dict(record: dict[str, Any]) -> Dossier:
    """Reconstruct a :class:`~reprolith.dossier.Dossier` from its ``to_dict`` output."""
    return Dossier(
        entry=record["entry"],
        state_variables=tuple(record["state_variables"]),
        equations=tuple(
            Equation(target=e["target"], expression=e["expression"], source_location=e["source_location"])
            for e in record["equations"]
        ),
        parameters=tuple(_parameter_from(p) for p in record["parameters"]),
        initial_conditions=tuple(_parameter_from(p) for p in record["initial_conditions"]),
        claims=tuple(
            DossierClaim(
                id=c["id"],
                quantity=c["quantity"],
                conditions=c["conditions"],
                source_location=c["source_location"],
                targetable=c["targetable"],
                reference_kind=ReferenceKind(c["reference_kind"]) if c["reference_kind"] else None,
                reference_data=tuple(c["reference_data"]),
            )
            for c in record["claims"]
        ),
        gaps=tuple(
            Gap(element=g["element"], kind=GapKind(g["kind"]), detail=g["detail"],
                load_bearing=g["load_bearing"])
            for g in record["gaps"]
        ),
        artifacts=tuple(
            ModelArtifact(filename=a["filename"], detected_format=a["detected_format"],
                          validates=a["validates"])
            for a in record["artifacts"]
        ),
    )


def bundle_from_dict(record: dict[str, Any]) -> ReconstructionBundle:
    """Reconstruct a :class:`~reprolith.reconstruction.ReconstructionBundle` from its dict."""
    model = record["model"]
    pin = record["engine_pin"]
    return ReconstructionBundle(
        entry=record["entry"],
        engine_pin=EnginePin(engine=pin["engine"], version=pin["version"], algorithm=pin["algorithm"]),
        model=ModelArtifact(**model) if model else None,
        origin=ModelOrigin(record["origin"]),
        recipe=tuple(RecipeStep(**s) for s in record["recipe"]),
        assumptions=tuple(_assumption_from(a) for a in record["assumptions"]),
        non_reconstructable=tuple(NonReconstructable(**n) for n in record["non_reconstructable"]),
        mismatches=tuple(record["mismatches"]),
        source_dossier=record["source_dossier"],
    )


__all__ = ["bundle_from_dict", "certificate_from_content", "dossier_from_dict"]
