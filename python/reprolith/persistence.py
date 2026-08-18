"""Reloading the inspectable artifacts from their stored dicts (design goal 3).

Every durable Reprolith artifact serializes to a plain dict via ``to_dict``/``content``; this
module reconstructs them, so a stored certificate, dossier, or reconstruction bundle can be
re-opened, re-served, or re-hashed without the inputs that produced it. Reconstruction is exact,
so a round trip is byte-identical — but not credulous: a certificate whose stored overall verdict
does not follow from its own stored evidence is refused, because the honesty invariants would
otherwise hold only for certificates built in-process and not for the ones read back off disk.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .certificate import (
    derive_overall,
    require_distinct_assumption_ids,
    require_stated_cause,
    require_stated_protocol,
)
from .dossier import (
    Dossier,
    DossierClaim,
    Equation,
    EquationKind,
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
from .scope import SCOPE_HUMAN, SCOPE_MACHINE, Scope


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


def require_pin_agrees_with_protocol(
    assessments: tuple[ClaimAssessment, ...], algorithm: str | None
) -> None:
    """Refuse a stored certificate whose pin contradicts its own protocol about what computed it.

    Both are on the certificate, and nothing compared them. A logical certificate carries "N nodes,
    SAT search" in its protocol and the solver in its pin, so a hand-edited pin could claim the
    stronger thing — that every one of 2^60 states was walked — over a space z3 searched, and load
    clean. `certify_logical` refuses exactly this on the way in; the public registry reads
    certificates off disk and never rebuilds them.
    """
    if not algorithm:
        return
    names_sat = "sat-fixed-points" in algorithm
    names_enumeration = "exhaustive-state-enumeration" in algorithm
    if names_sat and names_enumeration:
        # Naming both satisfies whichever branch is asked, so it reads as agreement with any
        # protocol. A run took one path.
        raise ValueError(
            f"the pin names both the SAT solver and exhaustive enumeration ({algorithm!r}); "
            "a certificate records the path that ran, not the ones available"
        )
    for assessment in assessments:
        protocol = assessment.protocol or ""
        # The pin must *positively* name the path the protocol states. Requiring it to name the
        # wrong one left the easier hand edit open: deleting "sat-fixed-points (z3 …)" leaves a pin
        # naming no path at all, which loaded clean while the builder refuses exactly that.
        # The markers are the phrases `logical.search_protocol` writes, and the SAT sentence
        # contains the words "exhaustive enumeration" (as the thing the space is beyond), so it is
        # tested first and the enumeration marker is the longer, unambiguous phrase.
        if "SAT search" in protocol and not names_sat:
            raise ValueError(
                f"claim {assessment.claim_id!r} records a SAT search but the pin ({algorithm!r}) "
                "does not name the solver that ran it: a certificate cannot leave the software "
                "that searched a state space off the record, or claim to have enumerated it"
            )
        if "exhaustive enumeration of all" in protocol and not names_enumeration:
            raise ValueError(
                f"claim {assessment.claim_id!r} records exhaustive enumeration but the pin "
                f"({algorithm!r}) does not say so"
            )


def certificate_from_content(content: dict[str, Any]) -> Certificate:
    """Reconstruct a :class:`Certificate` from the dict produced by :meth:`Certificate.content`.

    The stored overall verdict is re-derived from the stored assessments and assumptions, and a
    file whose verdict does not follow from its own evidence is refused rather than loaded. The
    honesty invariants are enforced when a certificate is *built*; without this check a hand-edited
    or corrupted file could carry a clean green ``reproduced`` over assumption-qualified claims all
    the way to the public registry, which reads certificates from disk and never rebuilds them.

    The scope statement is checked the same way. It is fixed text, not a per-certificate field:
    a file free to reword it could publish "validated as clinically safe" through every read
    surface, which is exactly the reading the scope statement exists to prevent.
    """
    paper = content["paper"]
    pin = content["engine_pin"]
    scope = content["scope"]
    assessments = tuple(_assessment_from(a) for a in content["assessments"])
    assumptions = tuple(_assumption_from(a) for a in content["assumptions"])
    if (scope["machine"], scope["human"]) != (SCOPE_MACHINE, SCOPE_HUMAN):
        raise ValueError(
            "certificate carries a scope statement that is not Reprolith's: the scope is fixed "
            "text and cannot be reworded by the file that carries it"
        )
    # The same two invariants the builder enforces. Deriving the verdict and pinning the scope
    # text was only half of "the honesty invariants hold for the ones read back off disk": a
    # stored estimation or population assessment with no protocol, or two assumptions sharing an
    # id, loaded clean while build_certificate refuses both — and the public registry reads
    # certificates from disk and never rebuilds them.
    require_stated_protocol(assessments)
    require_stated_cause(assessments)
    require_distinct_assumption_ids(assumptions)
    require_pin_agrees_with_protocol(assessments, pin["algorithm"])
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
            Equation(target=e["target"], expression=e["expression"],
                     source_location=e["source_location"],
                     kind=EquationKind(e.get("kind", EquationKind.RATE.value)))
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
                load_bearing=g["load_bearing"],
                carried_by_artifact=g.get("carried_by_artifact", False))
            for g in record["gaps"]
        ),
        artifacts=tuple(
            ModelArtifact(filename=a["filename"], detected_format=a["detected_format"],
                          validates=a["validates"])
            for a in record["artifacts"]
        ),
    )


def _recipe_step_from(record: dict[str, Any]) -> RecipeStep:
    """A recipe step from its record, with the overrides read back as an ordered pair list."""
    overrides = record.get("parameter_overrides", {})
    return RecipeStep(
        claim_id=record["claim_id"],
        protocol=record["protocol"],
        output=record["output"],
        time_span=record["time_span"],
        steps=record.get("steps"),
        parameter_overrides=tuple((k, float(v)) for k, v in overrides.items()),
        metric=record.get("metric"),
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
        recipe=tuple(_recipe_step_from(s) for s in record["recipe"]),
        assumptions=tuple(_assumption_from(a) for a in record["assumptions"]),
        non_reconstructable=tuple(NonReconstructable(**n) for n in record["non_reconstructable"]),
        mismatches=(
            None if record.get("mismatches") is None else tuple(record["mismatches"])
        ),
        source_dossier=record["source_dossier"],
    )


__all__ = [
    "bundle_from_dict",
    "certificate_from_content",
    "dossier_from_dict",
    "prune_certificate_directory",
]


def prune_certificate_directory(directory: Path, keep: Iterable[str]) -> list[str]:
    """Delete published certificate files for entries a regenerating run did not produce.

    A milestone runner writes one ``<key>.json`` (and ``.txt``) per entry and never cleared what
    was there before, so an entry withdrawn from a reference set stayed published: the next
    registry build listed it and counted it, while the self-validation report beside it did not —
    the published set and its own denominator disagreeing, with no error anywhere. Returns the
    stems removed, so a run can say what it withdrew.

    The badge goes with them. Withdrawing the certificate and its render while leaving the ``.svg``
    behind left a standalone, embeddable verdict — "reprolith: partially-reproduced" — for a
    certificate no longer published: the same failure this function closes, one suffix over.
    """
    kept = set(keep)
    removed = []
    for path in sorted(directory.glob("*")):
        if path.suffix in (".json", ".txt", ".svg") and path.stem not in kept:
            path.unlink()
            removed.append(path.stem)
    return sorted(set(removed))
