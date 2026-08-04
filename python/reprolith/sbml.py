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
from .fba import FbaModel


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


def compare_sbml_to_dossier(sbml: str, dossier: Dossier, *, rel_tol: float = 1e-9) -> list[str]:
    """Report where an adopted SBML model disagrees with the dossier's stated values.

    When reconstruction adopts a shipped model, it must still confirm the model matches the
    manuscript rather than silently trusting the artifact over the paper (spec:
    ``model-reconstruction`` — "Shipped model does not match the dossier"). This parses the
    model's parameters and initial amounts and reports each value that disagrees with the
    dossier beyond ``rel_tol``. An empty list means no disagreement was found.
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the adopted artifact is not readable SBML")

    sbml_params = {
        model.getParameter(i).getId(): model.getParameter(i).getValue()
        for i in range(model.getNumParameters())
    }
    sbml_ics = {
        model.getSpecies(i).getId(): model.getSpecies(i).getInitialAmount()
        for i in range(model.getNumSpecies())
    }

    mismatches: list[str] = []
    for parameter in dossier.parameters:
        if parameter.name in sbml_params and _differs(
            parameter.value, sbml_params[parameter.name], rel_tol
        ):
            mismatches.append(
                f"parameter {parameter.name}: dossier {parameter.value} != model "
                f"{sbml_params[parameter.name]}"
            )
    for ic in dossier.initial_conditions:
        if ic.name in sbml_ics and _differs(ic.value, sbml_ics[ic.name], rel_tol):
            mismatches.append(
                f"initial condition {ic.name}: dossier {ic.value} != model {sbml_ics[ic.name]}"
            )
    return mismatches


def ingest_fbc_sbml(sbml: str) -> FbaModel:
    """Parse an SBML-fbc constraint-based model into the matrices the FBA oracle solves.

    Reads the stoichiometry, the active objective (sign-corrected so a ``minimize`` objective is
    returned as an equivalent maximization, since the oracle maximizes), and the per-reaction
    flux bounds from the fbc reaction plugin. Boundary-condition species are excluded from the
    steady-state balance: they stand for the model's exchange with its surroundings and are not
    mass-balanced. This is the bridge from a published constraint-based model to
    :func:`reprolith.solve_objective` and the FBA judges. Needs the ``engine`` extra
    (python-libsbml with the fbc package).
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the artifact is not readable SBML")
    fbc = model.getPlugin("fbc")
    if fbc is None:
        raise ValueError("the model declares no fbc (constraint-based) package")

    species = [
        model.getSpecies(i).getId()
        for i in range(model.getNumSpecies())
        if not model.getSpecies(i).getBoundaryCondition()
    ]
    row_of = {sid: i for i, sid in enumerate(species)}
    reactions = [model.getReaction(i).getId() for i in range(model.getNumReactions())]
    params = {
        model.getParameter(i).getId(): model.getParameter(i).getValue()
        for i in range(model.getNumParameters())
    }

    stoich = [[0.0] * len(reactions) for _ in species]
    lower: list[float] = []
    upper: list[float | None] = []
    for j in range(model.getNumReactions()):
        reaction = model.getReaction(j)
        for k in range(reaction.getNumReactants()):
            ref = reaction.getReactant(k)
            if ref.getSpecies() in row_of:
                stoich[row_of[ref.getSpecies()]][j] -= ref.getStoichiometry()
        for k in range(reaction.getNumProducts()):
            ref = reaction.getProduct(k)
            if ref.getSpecies() in row_of:
                stoich[row_of[ref.getSpecies()]][j] += ref.getStoichiometry()
        plugin = reaction.getPlugin("fbc")
        if plugin is None or not plugin.isSetLowerFluxBound() or not plugin.isSetUpperFluxBound():
            raise ValueError(f"reaction {reaction.getId()} is missing an fbc flux bound")
        low_value = params[plugin.getLowerFluxBound()]
        high_value = params[plugin.getUpperFluxBound()]
        lower.append(low_value)
        upper.append(None if high_value == float("inf") else high_value)

    active = fbc.getObjective(fbc.getActiveObjectiveId())
    if active is None:
        raise ValueError("the model declares no active fbc objective")
    coefficients = {
        active.getFluxObjective(i).getReaction(): active.getFluxObjective(i).getCoefficient()
        for i in range(active.getNumFluxObjectives())
    }
    sign = 1.0 if active.getType() == "maximize" else -1.0
    objective = [sign * coefficients.get(rid, 0.0) for rid in reactions]

    gene_labels = {
        fbc.getGeneProduct(i).getId(): fbc.getGeneProduct(i).getLabel()
        for i in range(fbc.getNumGeneProducts())
    }
    gene_associations = []
    for j in range(model.getNumReactions()):
        plugin = model.getReaction(j).getPlugin("fbc")
        gpa = plugin.getGeneProductAssociation() if plugin is not None else None
        rule = _parse_gpr(gpa.getAssociation(), gene_labels, libsbml) if gpa is not None else None
        if rule is not None:
            gene_associations.append((reactions[j], rule))

    return FbaModel(
        species_ids=tuple(species),
        reaction_ids=tuple(reactions),
        stoichiometry=tuple(tuple(row) for row in stoich),
        objective=tuple(objective),
        lower=tuple(lower),
        upper=tuple(upper),
        gene_associations=tuple(gene_associations),
    )


def _parse_gpr(association: Any, gene_labels: dict[str, str], libsbml: Any) -> Any:
    """Convert an SBML-fbc gene-product association into the plain-tuple GPR the oracle evaluates.

    A gene-product reference becomes the gene's label; an ``and``/``or`` node becomes a
    ``("and"|"or", (child, ...))`` tuple over its converted children. Returns ``None`` for an
    empty or unrecognized association, so a reaction with no usable rule simply carries none.
    """
    if association is None:
        return None
    type_code = association.getTypeCode()
    if type_code == libsbml.SBML_FBC_GENEPRODUCTREF:
        return gene_labels.get(association.getGeneProduct(), association.getGeneProduct())
    if type_code in (libsbml.SBML_FBC_AND, libsbml.SBML_FBC_OR):
        operator = "and" if type_code == libsbml.SBML_FBC_AND else "or"
        children = tuple(
            child
            for i in range(association.getNumAssociations())
            if (child := _parse_gpr(association.getAssociation(i), gene_labels, libsbml)) is not None
        )
        return (operator, children) if children else None
    return None


def _differs(a: float, b: float, rel_tol: float) -> bool:
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) / scale > rel_tol


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


__all__ = ["build_model_sbml", "compare_sbml_to_dossier", "ingest_fbc_sbml"]
