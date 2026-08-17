"""Ingesting a shipped SBML model into a dossier (artifact-intake path).

When a paper (or its catalog entry) ships a model file, ingestion recognizes it, records its
format, and preserves it as a candidate starting point for reconstruction (spec:
``paper-ingestion`` — "Recognizing an existing model artifact"). This turns a shipped SBML
model into a :class:`~reprolith.dossier.Dossier`: its dynamic species become state variables
with initial conditions, its parameters become parameters, and its rate and assignment rules
become the governing equations — every element citing the model file it came from.

This is the *artifact-intake* ingestion path, distinct from extracting a dossier from the
manuscript prose. It gives real models a real dossier without inventing anything: the source
is the model file, honestly recorded as such, and the claims a paper stakes are **not** here
(they live in the manuscript), so a dossier built this way carries model structure but no
targetable claims.

Uses the optional ``engine`` extra (python-libsbml), imported lazily.
"""

from __future__ import annotations

from typing import Any

from .dossier import (
    Dossier,
    Equation,
    EquationKind,
    ExtractionConfidence,
    Gap,
    GapKind,
    ModelArtifact,
    Parameter,
)
from .engine import EngineUnavailable


def _libsbml() -> Any:
    try:
        import libsbml
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise EngineUnavailable(
            "SBML ingestion needs the 'engine' extra (python-libsbml); "
            "install with pip install 'reprolith[engine]'"
        ) from exc
    return libsbml


def _initial_amount(model: Any, species: Any) -> float | None:
    """The species' stated initial value as an amount, or ``None`` when it states none.

    A species may state its initial value as an amount or as a concentration, and the two are
    the same number only in a compartment of size 1. Reconstruction
    (:func:`reprolith.build_model_sbml`) is amount-based in a unit compartment, so a
    concentration stated in a compartment of any other size would be rebuilt as an amount off
    by that volume — and the model's own rules, written in concentration terms, off with it.
    That is refused here rather than silently converted, since converting the value alone would
    still leave the equations describing something other than the source model.
    """
    if species.isSetInitialAmount():
        return float(species.getInitialAmount())
    if not species.isSetInitialConcentration():
        return None
    compartment = model.getCompartment(species.getCompartment())
    size = compartment.getSize() if compartment is not None and compartment.isSetSize() else None
    if size is None:
        raise ValueError(
            f"species {species.getId()!r} states an initial concentration but its compartment "
            f"{species.getCompartment()!r} states no size, so the amount it stands for is unknown"
        )
    if size != 1.0:
        raise ValueError(
            f"species {species.getId()!r} states an initial concentration in compartment "
            f"{species.getCompartment()!r} of size {size}; reconstruction is amount-based in a "
            "unit compartment and cannot represent this model without rewriting its equations"
        )
    return float(species.getInitialConcentration())


def ingest_sbml(sbml: str, *, entry: str, source_label: str = "SBML model file") -> Dossier:
    """Parse a shipped SBML model into a dossier of its structure.

    ``entry`` is the catalog-entry key the dossier belongs to; ``source_label`` names the file
    for provenance. Dynamic (non-constant, non-boundary) species become state variables with
    their initial conditions; valued parameters become parameters; rate and assignment rules
    become equations, each recording which kind of rule it was so reconstruction rebuilds the
    same model. Units come from the SBML where stated, and fall back to ``dimensionless``. A
    species stating a concentration in a compartment that is not unit-sized is refused rather
    than read as an amount (see :func:`_initial_amount`).
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the artifact is not readable SBML")

    source = f"{source_label}"
    state_variables: list[str] = []
    initial_conditions: list[Parameter] = []
    for i in range(model.getNumSpecies()):
        species = model.getSpecies(i)
        if species.getConstant() or species.getBoundaryCondition():
            continue  # a fixed input, not a dynamic state variable
        value = _initial_amount(model, species)
        if value is None:
            continue  # no stated initial value; a reconstruction gap, not a fabricated one
        state_variables.append(species.getId())
        initial_conditions.append(
            Parameter(
                name=species.getId(),
                value=float(value),
                unit=species.getSubstanceUnits() or "dimensionless",
                source_location=source,
                confidence=ExtractionConfidence.QUOTED,
            )
        )

    # A parameter that is the target of a rate rule is a state variable, not a constant — the
    # "parameter + rateRule" idiom common in PK/PD models that ship no species. Its value is the
    # initial condition, and it must not be recorded as a fixed parameter.
    rate_targets = {
        model.getRule(i).getVariable()
        for i in range(model.getNumRules())
        if model.getRule(i).isRate()
    }

    parameters: list[Parameter] = []
    for i in range(model.getNumParameters()):
        parameter = model.getParameter(i)
        if not parameter.isSetValue():
            continue  # value-less parameter (rule-assigned); not a directly-stated value
        extracted = Parameter(
            name=parameter.getId(),
            value=float(parameter.getValue()),
            unit=parameter.getUnits() or "dimensionless",
            source_location=source,
            confidence=ExtractionConfidence.QUOTED,
        )
        if parameter.getId() in rate_targets:
            state_variables.append(parameter.getId())
            initial_conditions.append(extracted)
        else:
            parameters.append(extracted)

    equations: list[Equation] = []
    for i in range(model.getNumRules()):
        rule = model.getRule(i)
        if not (rule.isRate() or rule.isAssignment()):
            continue
        math = rule.getMath()
        if math is None:
            continue
        equations.append(
            Equation(
                target=rule.getVariable(),
                expression=str(libsbml.formulaToL3String(math)),
                source_location=source,
                kind=EquationKind.RATE if rule.isRate() else EquationKind.ASSIGNMENT,
            )
        )

    fatal = any(
        document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        for i in range(document.getNumErrors())
    )
    artifact = ModelArtifact(filename=source_label, detected_format="sbml", validates=not fatal)

    return Dossier(
        entry=entry,
        state_variables=tuple(state_variables),
        equations=tuple(equations),
        parameters=tuple(parameters),
        initial_conditions=tuple(initial_conditions),
        artifacts=(artifact,),
        gaps=_unread_constructs(model),
    )


def _unread_constructs(model: Any) -> tuple[Gap, ...]:
    """Record, as load-bearing gaps, the constructs this ingester reads past.

    Rules become equations here, so unlike the stochastic and fbc ingesters this path can carry
    most of a model — but not all of it. An event doses at a moment in time (the single most common
    PK/PD construct there is), an initial assignment overrides the initial values the dossier just
    recorded, and a conversion factor rescales every amount. Dropping any of them silently produces
    a dossier that describes a different model than the artifact, and the shipped worked example
    carries thirty-two initial assignments and an oral-dose event — so this is not hypothetical.

    They are recorded rather than refused because the artifact itself stays usable: adopt-and-verify
    runs the author's own file, where the constructs are still in force. It is the *dossier* that
    cannot represent them, and a reconstruction built from one carries the gap into its certificate
    instead of quietly leaving the dose out.
    """
    gaps: list[Gap] = []
    if model.getNumReactions():
        # The largest thing this path reads past, and for a reaction-based model it is the model:
        # the rules it does read are observables and volumes, so a dossier of a 10-reaction
        # cascade records eight state variables and nothing that moves any of them.
        gaps.append(Gap(
            element="reaction network",
            kind=GapKind.EQUATION,
            detail=(
                f"the artifact's dynamics are {model.getNumReactions()} reaction(s), which this "
                "dossier records no equation for; the state variables listed here have no stated "
                "law of motion, and a model rebuilt from the dossier alone does not move"
            ),
            load_bearing=True,
        ))
    if model.getNumFunctionDefinitions():
        gaps.append(Gap(
            element="function definitions",
            kind=GapKind.EQUATION,
            detail=(
                f"{model.getNumFunctionDefinitions()} functionDefinition(s) are referenced by the "
                "model's own expressions and are not recorded here, so an equation that calls one "
                "cannot be evaluated from this dossier"
            ),
            load_bearing=True,
        ))
    if model.getNumEvents():
        gaps.append(Gap(
            element="events",
            kind=GapKind.DOSING,
            detail=(
                f"the artifact carries {model.getNumEvents()} event(s) — a state change at a moment "
                "in time, usually a dose — which this dossier cannot represent; a model rebuilt "
                "from it alone runs without them"
            ),
            load_bearing=True,
        ))
    if model.getNumInitialAssignments():
        gaps.append(Gap(
            element="initial assignments",
            kind=GapKind.INITIAL_CONDITION,
            detail=(
                f"{model.getNumInitialAssignments()} initialAssignment(s) override initial values at "
                "the start of the run; the initial conditions recorded here are the stated ones, not "
                "the assigned ones"
            ),
            load_bearing=True,
        ))
    if model.isSetConversionFactor():
        gaps.append(Gap(
            element="conversion factor",
            kind=GapKind.UNIT,
            detail=(
                "the model declares a conversionFactor, which rescales every species amount and is "
                "not applied here"
            ),
            load_bearing=True,
        ))
    for j in range(model.getNumReactions()):
        rxn = model.getReaction(j)
        refs = [rxn.getReactant(k) for k in range(rxn.getNumReactants())]
        refs += [rxn.getProduct(k) for k in range(rxn.getNumProducts())]
        if any(ref.isSetConstant() and not ref.getConstant() for ref in refs):
            gaps.append(Gap(
                element=f"stoichiometry of reaction {rxn.getId()!r}",
                kind=GapKind.EQUATION,
                detail="a non-constant stoichiometry varies during the run and is read here as fixed",
                load_bearing=True,
            ))
            break
    return tuple(gaps)


__all__ = ["ingest_sbml"]
