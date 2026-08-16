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

from .dossier import Dossier, Equation, ExtractionConfidence, ModelArtifact, Parameter
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


def ingest_sbml(sbml: str, *, entry: str, source_label: str = "SBML model file") -> Dossier:
    """Parse a shipped SBML model into a dossier of its structure.

    ``entry`` is the catalog-entry key the dossier belongs to; ``source_label`` names the file
    for provenance. Dynamic (non-constant, non-boundary) species become state variables with
    their initial conditions; valued parameters become parameters; rate and assignment rules
    become equations. Units come from the SBML where stated, and fall back to ``dimensionless``.
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
        value = (
            species.getInitialAmount()
            if species.isSetInitialAmount()
            else species.getInitialConcentration()
        )
        if value is None or (not species.isSetInitialAmount() and not species.isSetInitialConcentration()):
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
    )


__all__ = ["ingest_sbml"]
