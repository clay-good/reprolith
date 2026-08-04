"""Building a standard-format SBML model from a dossier (bootstrap task 3.1).

Reconstruction emits a model in an open standard format so results are portable and
independently checkable (spec: ``model-reconstruction``). This builds SBML from the in-scope
ODE PK/PD content a dossier carries: each state variable becomes an amount-based species with
its initial condition, each parameter becomes an SBML parameter, and each governing equation
becomes a rate rule whose right-hand side is parsed from the dossier's expression. The result
is a valid SBML string that runs under the pinned engine (:mod:`reprolith.engine`), closing the
dossier -> model -> simulation loop.

Like the engine, SBML construction uses the optional ``engine`` extra (python-libsbml) and is
imported lazily, so the core package stays dependency-free.
"""

from __future__ import annotations

from typing import Any

from .dossier import Dossier
from .engine import EngineUnavailable


def _libsbml() -> Any:
    try:
        import libsbml
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise EngineUnavailable(
            "SBML construction needs the 'engine' extra (python-libsbml); "
            "install with pip install 'reprolith[engine]'"
        ) from exc
    return libsbml


def build_model_sbml(dossier: Dossier, *, level: int = 3, version: int = 2) -> str:
    """Compile a dossier's ODE PK/PD content into a valid SBML string.

    Requires that every state variable has an initial condition and a governing equation — a
    reconstruction that lacks either cannot be built and is blocked, not silently completed, so
    a clear error names what is missing. Parameter units are carried in the dossier for
    provenance but are not yet emitted as SBML unit definitions (an MVP simplification).
    """
    libsbml = _libsbml()

    ics = {p.name: p for p in dossier.initial_conditions}
    equations = {e.target: e for e in dossier.equations}
    missing_ics = [v for v in dossier.state_variables if v not in ics]
    missing_eqs = [v for v in dossier.state_variables if v not in equations]
    if missing_ics:
        raise ValueError(f"cannot build: state variables without an initial condition: {missing_ics}")
    if missing_eqs:
        raise ValueError(f"cannot build: state variables without a rate equation: {missing_eqs}")
    if not dossier.state_variables:
        raise ValueError("cannot build: the dossier declares no state variables")

    document = libsbml.SBMLDocument(level, version)
    model = document.createModel()
    model.setId(_sid(dossier.entry))

    compartment = model.createCompartment()
    compartment.setId("c")
    compartment.setConstant(True)
    compartment.setSize(1.0)

    for name in dossier.state_variables:
        species = model.createSpecies()
        species.setId(name)
        species.setCompartment("c")
        species.setInitialAmount(float(ics[name].value))
        species.setHasOnlySubstanceUnits(True)
        species.setBoundaryCondition(False)
        species.setConstant(False)

    for parameter in dossier.parameters:
        sbml_parameter = model.createParameter()
        sbml_parameter.setId(parameter.name)
        sbml_parameter.setValue(float(parameter.value))
        sbml_parameter.setConstant(True)

    for name in dossier.state_variables:
        equation = equations[name]
        math = libsbml.parseL3Formula(equation.expression)
        if math is None:
            raise ValueError(
                f"could not parse the rate expression for {name!r}: {equation.expression!r}"
            )
        rule = model.createRateRule()
        rule.setVariable(name)
        rule.setMath(math)

    errors = _fatal_errors(document, libsbml)
    if errors:
        raise ValueError("the built model is not valid SBML: " + "; ".join(errors))
    return str(libsbml.writeSBMLToString(document))


def _fatal_errors(document: Any, libsbml: Any) -> list[str]:
    document.checkConsistency()
    messages: list[str] = []
    for i in range(document.getNumErrors()):
        error = document.getError(i)
        if error.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
            messages.append(error.getMessage())
    return messages


def _sid(text: str) -> str:
    """A valid SBML SId derived from arbitrary text (ids must be C-identifier-like)."""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = "m_" + cleaned
    return cleaned


__all__ = ["build_model_sbml"]
