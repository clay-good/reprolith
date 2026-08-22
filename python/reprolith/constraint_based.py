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
from dataclasses import replace

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Gap, GapKind, ModelArtifact, Parameter
from .fba import FbaModel, judge_objective
from .model import Certificate, EnginePin, PaperIdentity
from .oracle import Attribution, ReferenceKind, Tolerance, undetermined_shortfall

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
    """Every load-bearing gap, not only the medium ones.

    Filtering on ``GapKind.MEDIUM`` meant a load-bearing gap of any other kind — an objective the
    paper never named, say — passed validation and then reached neither the gap report nor the
    per-claim qualification, so the certificate published a clean unqualified `reproduced` with
    the gap gone from the record entirely. The medium is only the most common way this class is
    under-specified, never the only one.
    """
    return tuple(
        (
            f"medium not fully specified: {gap.element} — {gap.detail}"
            if gap.kind is GapKind.MEDIUM
            else f"{gap.kind.value} not fully specified: {gap.element} — {gap.detail}"
        )
        for gap in dossier.load_bearing_gaps()
    )


def _medium_protocol(medium: Sequence[Parameter], model: FbaModel) -> str:
    """The bounds and objective a constraint-based number was actually solved under.

    An FBA optimum is a function of its medium, and the medium is the thing this class names as
    its own first failure mode — so a growth rate published without one cannot be re-derived from
    the certificate. The other sampled classes record the sampling behind their number; this is
    the same statement for a class whose "sampling" is a set of uptake limits.
    """
    stated = (
        # Full precision for the same reason the ODE protocol uses it: the bound printed here is
        # the bound the LP was solved under, and a re-run from a rounded one is a different run.
        ", ".join(f"{p.name}<={p.value!r} {p.unit}" for p in medium)
        if medium
        else "the model's own distributed bounds (none stated by the paper)"
    )
    maximized = ", ".join(
        model.reaction_ids[i] for i, c in enumerate(model.objective) if c
    ) or "no reaction"
    return f"medium: {stated}; maximize: {maximized}"


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

    # The class's own rules are written down in validate_constraint_based, and this path — the one
    # that publishes — never consulted them. It reads `claim.reference_data[0]` and lets
    # judge_objective default to a NUMERIC reference, so a claim the dossier records as digitized
    # off a figure was judged at the numeric tolerance and then published as `reference_kind:
    # "numeric"`: the certificate asserting a precision of reference the dossier never claimed,
    # and a verdict flipping on it. The milestone's own e_coli_core entry reaches here through
    # dossier_from_dict, which validates nothing. Guarding only the way in left the way out open.
    # …but only for a dossier that is going to publish a number. A dossier with no targetable
    # claim states nothing to be wrong about — the loop below is empty and the certificate comes
    # out `blocked`, which is first-class output here (30 of the 31 PK/PD entries are exactly
    # that). Raising on it turned an available abstention into an abort, and one not-yet-extractable
    # entry would take down a whole milestone run.
    if dossier.targetable_claims():
        problems = validate_constraint_based(dossier)
        if problems:
            raise ValueError(
                "a constraint-based dossier cannot be certified while it is ill-formed: "
                + "; ".join(problems)
            )

    model = _apply_medium(ingest_fbc_sbml(sbml), dossier.parameters)
    attributions = shortfalls or {}
    gap_report = _gap_report(dossier)
    # A load-bearing gap the paper never closed — a medium applied here as the model's own default
    # bound, an objective nobody named — means any claim that reproduces did so under a guessed
    # value: qualify it, exactly as every other class marks a reproduction that rests on an
    # assumption. Without this the objective claim would certify as a clean `reproduced` while the
    # same fact sits, unheeded, only in the gap report.
    rests_on_a_gap = bool(gap_report)
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
            assumption_qualified=rests_on_a_gap,
            # Without a fallback cause an objective that misses raises instead of certifying,
            # so this path could publish a reproduction or nothing at all — and the class's
            # agreement rate could not have come out any other way.
            attribution=attributions.get(claim.id) or undetermined_shortfall(claim.quantity),
        )
        for claim in dossier.targetable_claims()
    ]
    protocol = _medium_protocol(dossier.parameters, model)
    assessments = [replace(a, protocol=protocol) for a in assessments]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        gap_report=gap_report,
    )


__all__ = [
    "FLUX_UNIT",
    "certify_constraint_based",
    "constraint_based_dossier",
    "validate_constraint_based",
]
