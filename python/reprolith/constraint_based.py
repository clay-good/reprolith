"""Constraint-based (FBA) paper-ingestion front-end (spec: constraint-based-class).

This is the constraint-based analogue of :mod:`reprolith.certify` for PK/PD: it turns a
constraint-based paper into the shared :class:`~reprolith.dossier.Dossier` and certifies it end
to end, reusing the shared contracts unchanged (the generalization requirement).

The class's structural elements — reaction stoichiometry, per-reaction flux bounds, the objective
(a reaction and its direction), and the gene–protein–reaction associations — all live in the
paper's own SBML-fbc file. So a constraint-based dossier records them *by reference* to that
adopted, validating :class:`~reprolith.dossier.ModelArtifact` (adopt-and-verify), from which
:func:`reprolith.ingest_fbc_sbml` recovers them; it never re-encodes an S matrix by hand. This is
deliberate: re-shaping the shared dossier to carry stoichiometry would be speculative, and the
adopted-artifact reading needs no such change.

What the paper states *outside* that file is the one thing the file cannot pin down on its own:
the **medium** — the uptake limits under which each claimed objective value holds. The medium is
recorded as first-class dossier elements, because it is load-bearing: an unstated medium silently
changes the answer. Each stated uptake limit is a :class:`~reprolith.dossier.Parameter` (an
exchange reaction's maximum uptake); each unstated but outcome-changing exchange bound is a
:class:`~reprolith.dossier.Gap` of kind :attr:`~reprolith.dossier.GapKind.MEDIUM`, which the
validator requires be load-bearing.

Certifying uses the optional ``engine`` extra (python-libsbml with fbc, to adopt the model) and
the ``fba`` extra (scipy, to solve the LP); both are imported lazily so the core stays
dependency-free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Gap, GapKind, ModelArtifact, Parameter
from .fba import FbaModel, judge_objective
from .model import Certificate, EnginePin, PaperIdentity
from .oracle import Attribution, ReferenceKind, Tolerance

#: The field-standard flux unit; the unit every medium uptake limit is recorded in.
FLUX_UNIT = "mmol/gDW/h"


def constraint_based_dossier(
    entry: str,
    *,
    model: ModelArtifact,
    objective_claims: Sequence[DossierClaim],
    medium: Sequence[Parameter] = (),
    medium_gaps: Sequence[Gap] = (),
) -> Dossier:
    """Assemble a well-formed constraint-based dossier, or raise if it is ill-formed.

    ``model`` is the adopted SBML-fbc artifact that carries the stoichiometry, bounds, objective,
    and gene–reaction associations. ``objective_claims`` are the reported optimal objective values
    (each a numeric :class:`~reprolith.dossier.DossierClaim` carrying its reported value in
    ``reference_data``). ``medium`` is the stated uptake limits and ``medium_gaps`` the unstated,
    load-bearing exchange bounds. The result is validated by :func:`validate_constraint_based`;
    a structural problem is an error, never a silently-accepted dossier.
    """
    dossier = Dossier(
        entry=entry,
        parameters=tuple(medium),
        claims=tuple(objective_claims),
        gaps=tuple(medium_gaps),
        artifacts=(model,),
    )
    problems = validate_constraint_based(dossier)
    if problems:
        raise ValueError("ill-formed constraint-based dossier: " + "; ".join(problems))
    return dossier


def validate_constraint_based(dossier: Dossier) -> list[str]:
    """Structural problems that make a *constraint-based* dossier ill-formed; empty when well-formed.

    Adds the class's invariants on top of the shared :meth:`Dossier.validate`: it must adopt a
    validating SBML artifact (adopt-and-verify — there is nothing to reproduce without the model),
    it must target at least one objective-value claim carrying a single numeric reference value,
    and every medium gap must be load-bearing (an unstated medium is high-impact by construction).
    """
    problems = dossier.validate()

    sbml = [a for a in dossier.artifacts if a.detected_format.startswith("sbml")]
    if not sbml:
        problems.append("a constraint-based dossier must adopt an SBML model artifact")
    elif not any(a.validates for a in sbml):
        problems.append("the adopted SBML model artifact must validate (adopt-and-verify)")

    targetable = dossier.targetable_claims()
    if not targetable:
        problems.append("a constraint-based dossier must target at least one objective-value claim")
    for claim in targetable:
        if claim.reference_kind is not ReferenceKind.NUMERIC or len(claim.reference_data) != 1:
            problems.append(
                f"objective-value claim {claim.id!r} must carry exactly one numeric reference value"
            )

    for gap in dossier.gaps:
        if gap.kind is GapKind.MEDIUM and not gap.load_bearing:
            problems.append(
                f"medium gap {gap.element!r} must be load-bearing: "
                "an unstated medium silently changes the objective"
            )

    return problems


def _apply_medium(model: FbaModel, medium: Sequence[Parameter]) -> FbaModel:
    """Return ``model`` with the recorded medium applied: each named exchange's uptake limit.

    A medium parameter's value is a maximum uptake (a positive magnitude); applying it sets that
    exchange reaction's lower bound to its negation, the standard COBRA medium convention. A
    parameter naming a reaction the model does not contain is a real adopt-and-verify mismatch and
    raises, rather than being silently ignored.
    """
    lower = list(model.lower)
    for parameter in medium:
        try:
            index = model.reaction_index(parameter.name)
        except ValueError as exc:
            raise ValueError(
                f"medium names reaction {parameter.name!r}, which the adopted model does not contain"
            ) from exc
        lower[index] = -abs(parameter.value)
    return FbaModel(
        species_ids=model.species_ids,
        reaction_ids=model.reaction_ids,
        stoichiometry=model.stoichiometry,
        objective=model.objective,
        lower=tuple(lower),
        upper=model.upper,
        gene_associations=model.gene_associations,
    )


def _gap_report(dossier: Dossier) -> tuple[str, ...]:
    return tuple(
        f"medium not fully specified: {gap.element} — {gap.detail}"
        for gap in dossier.load_bearing_gaps()
        if gap.kind is GapKind.MEDIUM
    )


def certify_constraint_based(
    dossier: Dossier,
    *,
    sbml: str,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    tolerance: Tolerance | None = None,
    shortfalls: Mapping[str, Attribution] | None = None,
) -> Certificate:
    """Certify a constraint-based dossier end to end and assemble its certificate.

    Adopts the dossier's SBML model (:func:`reprolith.ingest_fbc_sbml`), applies the recorded
    medium to its exchange bounds, solves each objective-value claim under those constraints, and
    judges it with the shared FBA oracle (:func:`reprolith.judge_objective`). The certificate is
    built by the shared builder, so its overall verdict and inescapable scope flag come from the
    same rules as every other class; any unstated, load-bearing medium is surfaced in the gap
    report. ``sbml`` is the adopted model's text (it must be the artifact the dossier names).

    ``shortfalls`` maps a claim id to its root-cause :class:`~reprolith.oracle.Attribution` — a
    constraint-based failure mode such as an unspecified medium or an ambiguous objective. It is
    required for any claim expected to fall short, exactly as the oracle refuses a bare non-pass
    verdict; supplying it lets this path emit an honest *not-reproduced* certificate, not only a
    reproduced one.
    """
    from .sbml import ingest_fbc_sbml

    model = _apply_medium(ingest_fbc_sbml(sbml), dossier.parameters)
    attributions = shortfalls or {}
    assessments = [
        judge_objective(
            claim_id=claim.id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.reference_data[0],
            stoichiometry=model.stoichiometry,
            objective=model.objective,
            lower=model.lower,
            upper=model.upper,
            tolerance=tolerance,
            attribution=attributions.get(claim.id),
        )
        for claim in dossier.targetable_claims()
    ]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        gap_report=_gap_report(dossier),
    )


__all__ = [
    "FLUX_UNIT",
    "certify_constraint_based",
    "constraint_based_dossier",
    "validate_constraint_based",
]
