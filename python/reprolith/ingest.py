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
from .sbml import _rule_names_in

#: What a parameter's unit says when the model states none. `Parameter` requires a non-empty unit,
#: and the value itself *is* stated — so the honest record is a value whose unit is missing, plus a
#: gap saying so. It used to read ``dimensionless``, which is not an absence but a physical claim,
#: and a wrong one for 81 of the 94 parameters in the shipped metformin dossier: blood flows, a
#: glomerular filtration rate, transporter maxima, all recorded at `quoted` confidence.
UNSTATED_UNIT = "unstated"


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
    same model. A unit the model does not state is recorded as *unstated* and reported as a gap,
    never filled in with ``dimensionless`` — a hepatic blood flow is not dimensionless, and
    ``Parameter`` says in its own contract that an unstated unit is a gap rather than a value. A
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
    unstated_ics: list[str] = []
    for i in range(model.getNumSpecies()):
        species = model.getSpecies(i)
        if species.getConstant() or species.getBoundaryCondition():
            continue  # a fixed input, not a dynamic state variable
        value = _initial_amount(model, species)
        if value is None:
            # No stated initial value: never fabricated, but it used to vanish with no gap either
            # — the dossier then listed an equation of motion for a state variable it did not
            # declare, and reported no gap at all. A missing required element is a Gap.
            unstated_ics.append(species.getId())
            continue
        state_variables.append(species.getId())
        # SBML L3 makes `<model substanceUnits=...>` the default for every species that omits the
        # attribute, so reading only the species attribute reported a unit the model does state as
        # absent — a load-bearing gap whose own text asserted something false about the artifact,
        # and a difficulty of "high" for a fully specified model.
        species_unit, species_normalized = _resolve_unit(
            model, species.getSubstanceUnits() or model.getSubstanceUnits()
        )
        initial_conditions.append(
            Parameter(
                name=species.getId(),
                value=float(value),
                unit=species_unit,
                normalized_unit=species_normalized,
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
        stated, normalized = _resolve_unit(model, parameter.getUnits())
        extracted = Parameter(
            name=parameter.getId(),
            value=float(parameter.getValue()),
            unit=stated,
            normalized_unit=normalized,
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
        gaps=_unread_constructs(model)
        + _unstated_initial_values(tuple(unstated_ics))
        + _unresolved_symbols(
            model,
            equations=tuple(equations),
            declared=set(state_variables) | {p.name for p in parameters},
        )
        + _unstated_units(tuple(parameters) + tuple(initial_conditions)),
    )


def _resolve_unit(model: Any, unit_id: str) -> tuple[str, str | None]:
    """The unit as the source states it, and what it resolves to — or that it states none.

    SBML states a unit by reference: a parameter reads ``units="unit_0"`` and the meaning lives in
    a ``unitDefinition`` elsewhere in the file. Recording the reference alone gave a dossier that
    named `unit_0`, `unit_2` and `substance` as *units*, which is not what they are — and the units
    gap counted only the values with no reference at all, so its "N of M extracted values state no
    unit" implied the remainder carried usable ones. On the shipped metformin model every one of
    the 34 that did resolve to a real unit (milligram, millilitre, nanomole), and none of them said
    so. An identifier that resolves to nothing is not a unit either, and is recorded as unstated.
    """
    if not unit_id:
        return UNSTATED_UNIT, None
    definition = model.getUnitDefinition(unit_id)
    if definition is not None:
        rendered = _render_unit_definition(definition)
        if rendered:
            return unit_id, (rendered if rendered != unit_id else None)
    if _libsbml().UnitKind_forName(unit_id) != _libsbml().UNIT_KIND_INVALID:
        return unit_id, None  # already a base kind: `litre` means litre
    return UNSTATED_UNIT, None


def _render_unit_definition(definition: Any) -> str:
    """A ``unitDefinition`` as a readable product of base kinds, scales and exponents."""
    libsbml = _libsbml()
    factors = []
    for i in range(definition.getNumUnits()):
        unit = definition.getUnit(i)
        kind = libsbml.UnitKind_toString(unit.getKind())
        exponent, scale, multiplier = unit.getExponent(), unit.getScale(), unit.getMultiplier()
        head = ""
        if multiplier != 1.0:
            head += f"{multiplier:g}*"
        if scale != 0:
            head += f"10^{scale} "
        factors.append(f"{head}{kind}" + (f"^{exponent}" if exponent != 1 else ""))
    return " * ".join(factors)


def _unresolved_symbols(
    model: Any, *, equations: tuple[Equation, ...], declared: set[str]
) -> tuple[Gap, ...]:
    """Record what the dossier's own equations refer to but the dossier does not carry.

    :func:`build_model_sbml` already refuses an equation targeting something undeclared — but only
    on the way *out*, and only for targets. On the way *in*, a species marked ``constant`` or
    ``boundaryCondition`` is skipped as "a fixed input", which is right for a true fixed input and
    wrong for the two shapes that look like one: a boundary species with its own rate rule (a state
    variable by any other name) and a constant species a rule reads (a stated value). Either way its
    value left the dossier with no gap behind it, so the gap report said nothing was missing, the
    difficulty estimate said "a valid shipped model and no gaps", and adopt-and-verify — which
    never rebuilds, so never reaches the way-out check — reported agreement over half a model.

    Compartments are left to the compartment gap in :func:`_unread_constructs` rather than reported
    twice; a compartment carrying its own dynamics is a rule *target*, which this still catches.
    """
    compartments = {model.getCompartment(i).getId() for i in range(model.getNumCompartments())}
    resolvable = declared | {e.target for e in equations} | compartments
    unresolved = {
        name
        for equation in equations
        for name in _rule_names_in(model, equation.target)
        if name not in resolvable
    }
    dynamics = {e.target for e in equations if e.kind is EquationKind.RATE} - declared
    missing = sorted(unresolved | dynamics)
    if not missing:
        return ()
    shown = ", ".join(missing[:5]) + (", …" if len(missing) > 5 else "")
    return (Gap(
        element="undeclared model elements",
        kind=GapKind.PARAMETER,
        detail=(
            f"{len(missing)} element(s) the model's own rules depend on are not carried by this "
            f"dossier ({shown}) — a species held constant or at the boundary, or a variable with "
            "an equation of motion but no declaration; a model rebuilt from this dossier is not "
            "the model in the artifact"
        ),
        load_bearing=True,
        # The artifact still holds them, so running the author's own file closes this — but the
        # dossier, the reconstruction, and anything read off them do not.
        carried_by_artifact=True,
    ),)


def _unstated_initial_values(names: tuple[str, ...]) -> tuple[Gap, ...]:
    """Record the dynamic species the artifact states no initial value for.

    Such a species is dropped from ``state_variables`` and ``initial_conditions`` rather than
    given a fabricated starting point, which is right — but it used to be dropped in silence, so
    the dossier could carry a rate rule for a variable it never declared and still report no gap
    at all. The value is missing from the artifact as well as the dossier, so adopting the
    author's file does not close it.
    """
    if not names:
        return ()
    shown = ", ".join(sorted(names)[:5]) + (", …" if len(names) > 5 else "")
    return (Gap(
        element="initial values",
        kind=GapKind.INITIAL_CONDITION,
        detail=(
            f"{len(names)} dynamic species state no initial amount or concentration in the "
            f"artifact ({shown}); they are not recorded as state variables here, and a model "
            "rebuilt from this dossier does not contain them"
        ),
        load_bearing=True,
        carried_by_artifact=False,
    ),)


def _unstated_units(values: tuple[Parameter, ...]) -> tuple[Gap, ...]:
    """One gap for every extracted value whose unit the source does not state.

    Load-bearing because `unit-mismatch` is a catalogued failure mode: a rate constant read in the
    wrong time base reproduces nothing, and a dossier that silently calls it dimensionless gives a
    reconstructor no reason to check. The artifact still runs as its author wrote it — this is
    about what the *dossier* can honestly claim to have extracted.
    """
    unstated = sorted({v.name for v in values if v.unit == UNSTATED_UNIT})
    if not unstated:
        return ()
    shown = ", ".join(unstated[:5]) + (", …" if len(unstated) > 5 else "")
    return (Gap(
        element="units",
        kind=GapKind.UNIT,
        detail=(
            f"{len(unstated)} of {len(values)} extracted values state no unit in the artifact "
            f"({shown}); their magnitudes are recorded, their units are not"
        ),
        load_bearing=True,
        # Not carried by the artifact — this gap exists *because* the artifact states no unit, so
        # adopting the author's file closes nothing. Flagged the other way it was discounted out of
        # the difficulty estimate entirely, and models whose every extracted unit is unknown scored
        # "a valid shipped model and no gaps" while unit-mismatch is a catalogued failure mode.
        carried_by_artifact=False,
    ),)


#: SBML L3 packages that carry model semantics this core path does not read. `layout` and `render`
#: are deliberately absent: they describe how to *draw* a model, so a dossier that ignores them
#: loses nothing about its dynamics, and recording them would be a gap that cries wolf — the
#: shipped metformin model declares `layout` and is otherwise fully read.
_SEMANTIC_PACKAGES = frozenset(
    {"fbc", "qual", "comp", "multi", "arrays", "distrib", "spatial", "groups", "req"}
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
    packages = sorted(
        {
            name
            for i in range(model.getNumPlugins())
            if (plugin := model.getPlugin(i)) is not None
            and (name := plugin.getPackageName()) in _SEMANTIC_PACKAGES
        }
    )
    if packages:
        # An SBML L3 package holds the model's actual content for the classes that use one, and
        # this core path reads none of it: the repository's own SBML-qual toggle switch ingested
        # to a completely empty dossier — no state variables, no equations, and no gaps — that
        # then rated as "a valid shipped model with nothing to assume". The fbc and qual ingesters
        # refuse a model that declares no package; this is the same statement in reverse.
        gaps.append(Gap(
            element="package content",
            kind=GapKind.EQUATION,
            detail=(
                f"the artifact declares the SBML L3 package(s) {', '.join(packages)}, "
                "whose content this dossier does not read; the class-specific ingester "
                "(ingest_fbc_sbml, ingest_qual_sbml) is the one that reads it"
            ),
            load_bearing=True,
            carried_by_artifact=True,
        ))
    algebraic = sum(
        1 for i in range(model.getNumRules())
        if not (model.getRule(i).isRate() or model.getRule(i).isAssignment())
    )
    if algebraic:
        gaps.append(Gap(
            element="algebraic rules",
            kind=GapKind.EQUATION,
            detail=(
                f"{algebraic} algebraicRule(s) constrain the system and produce no equation here; "
                "a model rebuilt from this dossier is unconstrained by them"
            ),
            load_bearing=True,
            carried_by_artifact=True,
        ))
    unsized = [
        c for c in (model.getCompartment(i) for i in range(model.getNumCompartments()))
        if not c.isSetSize()
    ]
    if unsized:
        # Reconstruction fills in 1.0 for a compartment with no stated size, which is a value the
        # artifact never gave. Only compartments with a stated non-unit size were being recorded.
        gaps.append(Gap(
            element="compartment sizes",
            kind=GapKind.OTHER,
            detail=(
                f"{len(unsized)} compartment(s) state no size ({', '.join(c.getId() for c in unsized[:5])}); "
                "a model rebuilt from this dossier gives them size 1, a value the artifact never states"
            ),
            load_bearing=True,
            carried_by_artifact=False,
        ))
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
            carried_by_artifact=True,
        ))
    volumes = [
        model.getCompartment(i) for i in range(model.getNumCompartments())
    ]
    sized = [c for c in volumes if c.isSetSize() and c.getSize() != 1.0]
    if sized:
        # Reconstruction builds one compartment of size 1, so a model whose species live in
        # compartments of other sizes cannot be rebuilt as itself: every concentration is out by
        # that volume, and `simulate` reads concentrations. A concentration-stated species in such
        # a compartment is refused outright at intake; an amount-stated one is representable, and
        # this is what the dossier does not carry about it.
        named = ", ".join(f"{c.getId()}={c.getSize():g}" for c in sized[:5])
        gaps.append(Gap(
            element="compartment volumes",
            kind=GapKind.OTHER,
            detail=(
                f"{len(sized)} of {len(volumes)} compartment(s) are not unit-sized ({named}); the "
                "dossier records no compartment, and a model rebuilt from it places every species "
                "in a single compartment of size 1"
            ),
            load_bearing=True,
            carried_by_artifact=True,
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
            carried_by_artifact=True,
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
            carried_by_artifact=True,
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
            carried_by_artifact=True,
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
            carried_by_artifact=True,
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
                carried_by_artifact=True,
            ))
            break
    return tuple(gaps)


__all__ = ["ingest_sbml"]
