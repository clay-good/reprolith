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

import operator
from collections.abc import Callable, Container, Mapping
from typing import Any

from .dossier import Dossier
from .engine import EngineUnavailable
from .fba import FbaModel
from .logical import BooleanNetwork, parse_boolean_network
from .stochastic import Reaction


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

    Reads the stoichiometry, the active objective (which must be a ``maximize`` objective — a
    ``minimize`` objective is refused rather than solved with the wrong sign), and the per-reaction
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
    _refuse_unreadable_document(document)
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
    # A parameter with no value reads as NaN, which becomes a NaN flux bound and surfaces much
    # later as an unbounded LP blamed on the model rather than on the bound nobody set.
    params = {}
    for i in range(model.getNumParameters()):
        parameter = model.getParameter(i)
        if not parameter.isSetValue():
            continue
        params[parameter.getId()] = parameter.getValue()

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
        for bound_id in (plugin.getLowerFluxBound(), plugin.getUpperFluxBound()):
            if bound_id not in params:
                raise ValueError(
                    f"reaction {reaction.getId()} names flux bound parameter {bound_id!r}, "
                    "which the model does not declare"
                )
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
    objective_type = active.getType()
    if objective_type != "maximize":
        # Only a maximization objective is supported end-to-end. Merely negating the objective
        # vector makes the *flux distribution* an equivalent maximization, but the optimal value
        # the oracle returns is then also negated — so it would be judged against the paper's
        # (un-negated) reported optimum and a reproducible model would certify as FAILED. The
        # essentiality and robustness fingerprints likewise assume a positive maximization
        # optimum. Rather than emit a wrong verdict, refuse, as we do for other unsupported
        # constructs. (The FROG/biomass models this targets all maximize.)
        raise ValueError(
            f"unsupported fbc objective type {objective_type!r}: only 'maximize' is supported"
        )
    unknown = sorted(set(coefficients) - set(reactions))
    if unknown:
        # Dropping the term would leave an all-zero (or partial) objective that optimizes to zero
        # and matches a reported zero exactly — a clean "reproduced" for a model whose objective
        # was never read. A misspelled or stale reaction id is the likely cause, and it is exactly
        # what the caller needs told.
        raise ValueError(
            f"the active objective names reaction(s) the model does not contain: {unknown}"
        )
    objective = [coefficients.get(rid, 0.0) for rid in reactions]

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


_QUAL_RELATIONS: dict[str, Callable[[float, float], bool]] = {
    "eq": operator.eq, "neq": operator.ne, "geq": operator.ge,
    "leq": operator.le, "gt": operator.gt, "lt": operator.lt,
}


def _qual_operand(node: Any, libsbml: Any, nodes: Container[str]) -> str:
    """One side of a qual level comparison, as a node name or the literal ``"0"``/``"1"``."""
    kind = node.getType()
    if kind == libsbml.AST_NAME:
        name = node.getName()
        if name not in nodes:
            raise ValueError(f"transition math references unknown species {name!r}")
        return str(name)
    if kind in (libsbml.AST_INTEGER, libsbml.AST_REAL, libsbml.AST_REAL_E, libsbml.AST_RATIONAL):
        value = float(node.getValue())
        if value not in (0.0, 1.0):
            raise ValueError(
                f"transition math compares against level {value:g}; the Boolean oracle supports "
                "only two-level (0/1) logical models"
            )
        return "1" if value == 1.0 else "0"
    raise ValueError(f"unsupported qual math operand (AST type {kind})")


def _comparison_expression(relation: Callable[[float, float], bool], left: str, right: str) -> str:
    """A level comparison between two 0/1 operands, as a Boolean rule expression.

    Both sides are levels of a two-level model, so the comparison is a function of at most two
    Boolean variables: enumerate the cases it holds in and write them down as a disjunction. Built
    from the same relation the closure evaluates, so the expression and the closure cannot drift.
    """
    def value(operand: str, assignment: int) -> float:
        return float(operand) if operand in ("0", "1") else float(assignment)

    variables = [operand for operand in dict.fromkeys((left, right)) if operand not in ("0", "1")]
    satisfying: list[str] = []
    for case in range(2 ** len(variables)):
        bits = {name: (case >> i) & 1 for i, name in enumerate(variables)}
        if not relation(value(left, bits.get(left, 0)), value(right, bits.get(right, 0))):
            continue
        if not variables:
            return "True"
        satisfying.append(
            "(" + " & ".join(name if bits[name] else f"!{name}" for name in variables) + ")"
        )
    if not satisfying:
        return "False"
    if len(satisfying) == 2 ** len(variables):
        return "True"
    return "(" + " | ".join(satisfying) + ")"


def _qual_condition_expression(node: Any, libsbml: Any, nodes: Container[str]) -> str:
    """An SBML-qual functionTerm condition as a Boolean rule expression.

    Carrying the expression is what lets an ingested network above the enumeration
    ceiling take the scalable SAT path instead of refusing — a real signalling model of sixty to
    eighty nodes is exactly the case SBML-qual files describe.
    """
    kind = node.getType()
    if kind == libsbml.AST_CONSTANT_TRUE:
        return "True"
    if kind == libsbml.AST_CONSTANT_FALSE:
        return "False"
    if kind == libsbml.AST_LOGICAL_NOT:
        return f"(!{_qual_condition_expression(node.getChild(0), libsbml, nodes)})"
    if kind in (libsbml.AST_LOGICAL_AND, libsbml.AST_LOGICAL_OR, libsbml.AST_LOGICAL_XOR):
        parts = [
            _qual_condition_expression(node.getChild(i), libsbml, nodes)
            for i in range(node.getNumChildren())
        ]
        joiner = {
            libsbml.AST_LOGICAL_AND: " & ", libsbml.AST_LOGICAL_OR: " | ",
            libsbml.AST_LOGICAL_XOR: " ^ ",
        }[kind]
        return "(" + joiner.join(parts) + ")" if parts else "True"
    relation_name = _relation_name(node, libsbml)
    relation = _QUAL_RELATIONS.get(relation_name) if relation_name is not None else None
    if relation is not None:
        return _comparison_expression(
            relation,
            _qual_operand(node.getChild(0), libsbml, nodes),
            _qual_operand(node.getChild(1), libsbml, nodes),
        )
    raise ValueError(f"unsupported qual math condition (AST type {kind})")


def _qual_rule_expression(conditions: list[tuple[str, int]], default_level: int) -> str:
    """A node's whole update rule as one expression: the first satisfied term's level.

    Function terms are ordered, so term *i* only decides the level when every earlier term missed.
    Written out, the node is 1 exactly when some level-1 term holds and no earlier term did — or,
    when the default level is 1, when no term holds at all.
    """
    disjuncts: list[str] = []
    earlier: list[str] = []
    for condition, level in conditions:
        if level == 1:
            disjuncts.append("(" + " & ".join([*(f"!{e}" for e in earlier), condition]) + ")")
        earlier.append(condition)
    if default_level == 1:
        disjuncts.append(
            "(" + " & ".join(f"!{e}" for e in earlier) + ")" if earlier else "True"
        )
    return " | ".join(disjuncts) if disjuncts else "False"


def _relation_name(node: Any, libsbml: Any) -> str | None:
    kind = node.getType()
    return {
        libsbml.AST_RELATIONAL_EQ: "eq", libsbml.AST_RELATIONAL_NEQ: "neq",
        libsbml.AST_RELATIONAL_GEQ: "geq", libsbml.AST_RELATIONAL_LEQ: "leq",
        libsbml.AST_RELATIONAL_GT: "gt", libsbml.AST_RELATIONAL_LT: "lt",
    }.get(kind)


def ingest_qual_sbml(sbml: str) -> BooleanNetwork:
    """Parse an SBML-qual logical model into the :class:`BooleanNetwork` the logical oracle judges.

    The logical-class counterpart of :func:`ingest_fbc_sbml`: it reads the qualitative species and
    each transition's function terms, compiling every functionTerm condition into a pure-Python
    closure so the returned network retains nothing libsbml owns. Each species that is the output of
    a transition gets that transition's update rule (the first satisfied term's result level, else
    the default term's); a species with no transition is a constant input that holds its value.

    Restricted to two-level (Boolean) models: a qualitative species with ``maxLevel > 1`` raises,
    because the Boolean oracle judges 0/1 states, not multi-valued logic. Needs the ``engine`` extra
    (python-libsbml, which bundles the qual package).
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the artifact is not readable SBML")
    _refuse_unreadable_document(document)
    qual = model.getPlugin("qual")
    if qual is None:
        raise ValueError("the model declares no qual (logical) package")

    node_names: set[str] = set()
    for i in range(qual.getNumQualitativeSpecies()):
        qs = qual.getQualitativeSpecies(i)
        max_level = qs.getMaxLevel() if qs.isSetMaxLevel() else 1
        initial_level = qs.getInitialLevel() if qs.isSetInitialLevel() else 0
        # maxLevel is optional, so its absence is not evidence the model is Boolean. An initial
        # level above 1 says the species is multi-valued just as plainly, and reading it as Boolean
        # would discard the model's real dynamics while still producing a verdict.
        if max_level > 1 or initial_level > 1:
            raise ValueError(
                f"species {qs.getId()!r} is multi-valued (maxLevel {max_level}, initial level "
                f"{initial_level}); the Boolean oracle supports only two-level (0/1) logical models"
            )
        node_names.add(qs.getId())

    rules: dict[str, str] = {}  # node -> its update rule as an expression the SAT path can encode
    for i in range(qual.getNumTransitions()):
        transition = qual.getTransition(i)
        if transition.getNumOutputs() != 1:
            raise ValueError(f"transition {transition.getId()!r} must have exactly one output")
        output = transition.getOutput(0)
        target = output.getQualitativeSpecies()
        if target not in node_names:
            raise ValueError(f"transition {transition.getId()!r} outputs unknown species {target!r}")
        if target in rules:
            raise ValueError(f"species {target!r} is the output of more than one transition")
        if (
            output.isSetTransitionEffect()
            and output.getTransitionEffect() != libsbml.OUTPUT_TRANSITION_EFFECT_ASSIGNMENT_LEVEL
        ):
            # "production" adds the result level to the current one; the oracle assigns it. Running
            # an additive transition as an assignment is a different model, so refuse it.
            raise ValueError(
                f"transition {transition.getId()!r} produces rather than assigns its output level; "
                "only assignment transitions are supported"
            )
        for k in range(transition.getNumInputs()):
            model_input = transition.getInput(k)
            if (
                model_input.isSetTransitionEffect()
                and model_input.getTransitionEffect() == libsbml.INPUT_TRANSITION_EFFECT_CONSUMPTION
            ):
                raise ValueError(
                    f"transition {transition.getId()!r} consumes input "
                    f"{model_input.getQualitativeSpecies()!r}; consumption is not Boolean logic"
                )
            if model_input.isSetThresholdLevel() and model_input.getThresholdLevel() > 1:
                raise ValueError(
                    f"transition {transition.getId()!r} sets a threshold level "
                    f"{model_input.getThresholdLevel()} above 1; the Boolean oracle supports only "
                    "two-level (0/1) logical models"
                )
        default_term = transition.getDefaultTerm()
        if default_term is None:
            # SBML-qual requires it, and taking the missing one as 0 invents the behaviour of every
            # state no function term covers.
            raise ValueError(f"transition {transition.getId()!r} has no default term")
        default_level = default_term.getResultLevel()
        conditions: list[tuple[str, int]] = []
        for k in range(transition.getNumFunctionTerms()):
            function_term = transition.getFunctionTerm(k)
            level = function_term.getResultLevel()
            math = function_term.getMath()
            if math is None:
                raise ValueError(f"a function term of transition {transition.getId()!r} has no math")
            if level not in (0, 1):
                raise ValueError(f"result level {level} is not Boolean in transition {transition.getId()!r}")
            conditions.append((_qual_condition_expression(math, libsbml, node_names), level))
        if default_level not in (0, 1):
            raise ValueError(f"default result level {default_level} is not Boolean in transition {transition.getId()!r}")
        rules[target] = _qual_rule_expression(conditions, default_level)

    for name in sorted(node_names - set(rules)):  # inputs with no transition hold their value
        rules[name] = name

    return parse_boolean_network(rules)


def _factor_powers(node: Any, libsbml: Any) -> dict[str, int] | None:
    """Decompose a kinetic-law expression into ``{name: integer power}`` if it is a pure product.

    Walks the MathML AST accepting only a product of variables raised to non-negative integer
    powers — the shape a mass-action rate law takes (``k``, ``k·A``, ``k·A·B``, ``k·A^2``). A bare
    variable is power 1; nested ``times`` flattens. Anything else — a sum, a quotient, a numeric
    coefficient, a call, a non-integer or symbolic exponent — means the law is *not* mass action, so
    the function returns ``None`` rather than a partial reading. This is the structural check that
    lets :func:`_mass_action_rate` honor its contract: a law it cannot prove is mass action is
    refused, never silently reinterpreted as one.
    """
    powers: dict[str, int] = {}

    def walk(n: Any, multiplier: int) -> bool:
        node_type = n.getType()
        if node_type == libsbml.AST_TIMES:
            return all(walk(n.getChild(i), multiplier) for i in range(n.getNumChildren()))
        if node_type == libsbml.AST_NAME:
            powers[n.getName()] = powers.get(n.getName(), 0) + multiplier
            return True
        if node_type in (libsbml.AST_POWER, libsbml.AST_FUNCTION_POWER):
            if n.getNumChildren() != 2:
                return False
            base, exponent = n.getChild(0), n.getChild(1)
            if base.getType() != libsbml.AST_NAME or exponent.getType() != libsbml.AST_INTEGER:
                return False
            power = exponent.getInteger()
            if power < 0:
                return False
            powers[base.getName()] = powers.get(base.getName(), 0) + multiplier * power
            return True
        return False

    return powers if walk(node, 1) else None


def _mass_action_rate(kinetic_law: Any, reactant_powers: Mapping[str, int]) -> float:
    """The mass-action rate constant of a reaction whose law is ``k · ∏ reactantᵢ^stoichᵢ``.

    Scoped to mass-action laws with a single rate parameter, so the constant is read directly. The
    rate is a single kinetic-law local parameter (SBML L3) or a single legacy law parameter (SBML
    L2); any other shape — no parameter, or several — is ambiguous and raises rather than guessing.

    Reading the parameter is not enough: a single-parameter law can still be non-mass-action (a
    constant flux where a reactant is consumed, a saturating or inhibitory rate). So the law's
    expression is checked structurally against the reaction's own reactant stoichiometry
    (``reactant_powers``); unless it is exactly ``rate · ∏ reactantᵢ^stoichᵢ`` — a zeroth-order law
    being just ``rate`` when there are no reactants — the law is refused. Without this the SSA would
    run a fabricated mass-action propensity for a law that says something else entirely, certifying a
    model the artifact never described.
    """
    if kinetic_law is None:
        raise ValueError("a stochastic reaction needs a mass-action kinetic law with a rate constant")
    n_local = kinetic_law.getNumLocalParameters()
    n_legacy = kinetic_law.getNumParameters()
    if n_local == 1:
        rate_param = kinetic_law.getLocalParameter(0)
    elif n_local == 0 and n_legacy == 1:
        rate_param = kinetic_law.getParameter(0)
    else:
        raise ValueError(
            "expected exactly one mass-action rate parameter in the kinetic law; "
            f"found {n_local} local and {n_legacy} legacy — only single-parameter mass action is supported"
        )

    math = kinetic_law.getMath()
    if math is None:
        raise ValueError("the kinetic law has no rate expression to verify as mass action")
    factors = _factor_powers(math, _libsbml())
    expected = {rate_param.getId(): 1, **dict(reactant_powers)}
    if factors != expected:
        raise ValueError(
            "the kinetic law is not mass action: expected the rate constant times each reactant "
            f"raised to its stoichiometry ({expected}), but the expression is {factors}; a "
            "non-mass-action law is refused rather than reinterpreted as mass action"
        )
    return float(rate_param.getValue())


def ingest_stochastic_sbml(sbml: str) -> tuple[list[str], list[Reaction], list[int]]:
    """Parse an SBML reaction network into the species, reactions, and initial counts the SSA runs.

    The stochastic counterpart of :func:`ingest_fbc_sbml`: a stochastic model *is* an SBML
    reaction network read discretely. Reads each species' initial molecule count and each reaction's
    reactant/product stoichiometry structurally, and its mass-action rate constant from the kinetic
    law (see :func:`_mass_action_rate`), building the :class:`~reprolith.stochastic.Reaction` list the
    Gillespie SSA consumes. Returns the ordered species names, the reactions, and the initial counts.

    Scoped to mass-action kinetics with integer initial amounts — the discrete-molecule regime the
    SSA models; a non-integer initial amount or a non-mass-action law raises rather than being
    silently coerced. Needs the ``engine`` extra (python-libsbml).
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the artifact is not readable SBML")

    _refuse_unreadable_document(document)
    _refuse_unrepresentable_constructs(model, kind="a stochastic reaction network")

    species = [model.getSpecies(i).getId() for i in range(model.getNumSpecies())]
    index_of = {sid: i for i, sid in enumerate(species)}
    initial: list[int] = []
    for i in range(model.getNumSpecies()):
        spec = model.getSpecies(i)
        # A boundary species is held fixed by SBML's own semantics; this SSA has one state vector,
        # so a reaction consuming it would deplete a pool the artifact says never depletes — a
        # different model, silently. Refusing keeps the promise this module already makes about
        # rate laws: reinterpretation is never silent.
        if spec.getBoundaryCondition() or spec.getConstant():
            raise ValueError(
                f"species {spec.getId()!r} is a boundary or constant species, which this SSA "
                "cannot hold fixed while reactions reference it; the run would deplete a pool the "
                "model says is held constant"
            )
        if not spec.getHasOnlySubstanceUnits():
            raise ValueError(
                f"species {spec.getId()!r} is specified in concentration units "
                "(hasOnlySubstanceUnits is false); the SSA needs molecule counts, and reading its "
                "amount verbatim would misread every rate law that scales with volume"
            )
        amount = spec.getInitialAmount()
        rounded = round(amount)
        if abs(amount - rounded) > 1e-9:
            raise ValueError(
                f"species {species[i]!r} has non-integer initial amount {amount}; the SSA needs "
                "discrete molecule counts"
            )
        initial.append(int(rounded))

    reactions: list[Reaction] = []
    for j in range(model.getNumReactions()):
        rxn = model.getReaction(j)
        # SBML lets one species appear as several reactant references (``X + X -> Y``) or as a
        # single reference with stoichiometry 2; the two encodings mean the same reaction. Sum the
        # references per species FIRST and build the reaction from that sum, so both encodings give
        # the same order. Reading the references one by one would run k·n·n where stochastic mass
        # action calls for k·n(n-1)/2 — while the mass-action check below, which aggregates, still
        # passed the model as consistent.
        reactant_powers: dict[str, int] = {}
        for k in range(rxn.getNumReactants()):
            ref = rxn.getReactant(k)
            reactant_powers[ref.getSpecies()] = reactant_powers.get(ref.getSpecies(), 0) + int(
                round(ref.getStoichiometry())
            )
        reactants = tuple((index_of[sid], stoich) for sid, stoich in reactant_powers.items())
        product_powers: dict[str, int] = {}
        for k in range(rxn.getNumProducts()):
            ref = rxn.getProduct(k)
            product_powers[ref.getSpecies()] = product_powers.get(ref.getSpecies(), 0) + int(
                round(ref.getStoichiometry())
            )
        products = tuple((index_of[sid], stoich) for sid, stoich in product_powers.items())
        rate = _mass_action_rate(rxn.getKineticLaw(), reactant_powers)
        reactions.append(Reaction(rate=rate, reactants=reactants, products=products))

    return species, reactions, initial


def _refuse_unrepresentable_constructs(model: Any, *, kind: str) -> None:
    """Refuse an artifact carrying model constructs this ingester does not read.

    Each of these changes what the model *does* — an initial assignment overrides the initial
    value, a rule gives a variable dynamics of its own, an event doses at a moment in time, a
    conversion factor rescales every amount, a non-constant stoichiometry varies as the run
    proceeds. Ingesting the reactions and dropping the rest produces a model the artifact never
    described, and nothing downstream can tell. The rule this module already applies to rate laws
    applies here too: what cannot be represented is refused, not quietly left out.
    """
    unsupported: list[str] = []
    if model.getNumInitialAssignments():
        unsupported.append("initialAssignment (it overrides the stated initial values)")
    if model.getNumRules():
        unsupported.append("rules (they give a variable dynamics of its own)")
    if model.getNumEvents():
        unsupported.append("events (they change the state at a moment in time — dosing, most often)")
    if model.isSetConversionFactor():
        unsupported.append("a model conversionFactor (it rescales every amount)")
    for j in range(model.getNumReactions()):
        rxn = model.getReaction(j)
        refs = [rxn.getReactant(k) for k in range(rxn.getNumReactants())]
        refs += [rxn.getProduct(k) for k in range(rxn.getNumProducts())]
        if any(ref.isSetConstant() and not ref.getConstant() for ref in refs):
            unsupported.append(f"a non-constant stoichiometry in reaction {rxn.getId()!r}")
            break
    if unsupported:
        raise ValueError(
            f"this artifact cannot be ingested as {kind}: it uses "
            + "; ".join(unsupported)
            + ". Reprolith refuses rather than running a model the artifact does not describe."
        )


def _refuse_unreadable_document(document: Any) -> None:
    """Refuse a document libSBML reports as fatally invalid, rather than running it anyway.

    Fatal severity only. Real-world SBML routinely carries warnings and non-fatal errors and still
    describes exactly one model — refusing those would block artifacts the field actually ships. A
    fatal error means libSBML could not make sense of the document's structure, so whatever the
    ingester reads out of it afterwards is not the artifact's model.
    """
    fatal = [
        document.getError(i)
        for i in range(document.getNumErrors())
        if document.getError(i).getSeverity() >= 3  # LIBSBML_SEV_FATAL
    ]
    if fatal:
        raise ValueError(
            f"the artifact is not valid SBML ({len(fatal)} error(s)); the first is: "
            f"{fatal[0].getMessage().strip()}"
        )


__all__ = [
    "build_model_sbml",
    "compare_sbml_to_dossier",
    "ingest_fbc_sbml",
    "ingest_qual_sbml",
    "ingest_stochastic_sbml",
]
