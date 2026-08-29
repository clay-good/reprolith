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
from math import factorial
from typing import Any

from .dossier import Dossier, EquationKind
from .engine import EngineUnavailable
from .fba import FbaModel
from .logical import BooleanNetwork, parse_boolean_network
from .spatial import SpatialModel
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
    a clear error names what is missing. Each equation is emitted as the kind of rule it was
    extracted as: a rate equation becomes a rate rule, an assignment equation becomes an
    assignment rule (``Y = 2X`` is not ``dY/dt = 2X``), and a parameter an equation determines
    is emitted non-constant, and an initial-assignment equation becomes an ``initialAssignment``
    whose target is declared constant, because a value set once at the start and one recomputed
    every step are different models. An equation targeting something the model does not declare is
    refused rather than dropped. Parameter units are carried in the dossier for provenance but
    are not yet emitted as SBML unit definitions (an MVP simplification).
    """
    libsbml = _libsbml()

    ics = {p.name: p for p in dossier.initial_conditions}
    # An initial assignment is not a governing equation: it fixes a starting value and says
    # nothing about how the target moves afterwards. Keeping it out of this map is what stops an
    # initial assignment on a species from satisfying the "every state variable has a rate
    # equation" check below, and from making its target non-constant further down.
    governing = {
        e.target: e for e in dossier.equations if e.kind is not EquationKind.INITIAL_ASSIGNMENT
    }
    initial_assignments = [
        e for e in dossier.equations if e.kind is EquationKind.INITIAL_ASSIGNMENT
    ]
    equations = governing
    missing_ics = [v for v in dossier.state_variables if v not in ics]
    missing_eqs = [v for v in dossier.state_variables if v not in governing]
    if missing_ics:
        raise ValueError(f"cannot build: state variables without an initial condition: {missing_ics}")
    if missing_eqs:
        raise ValueError(f"cannot build: state variables without a rate equation: {missing_eqs}")
    if not dossier.state_variables:
        raise ValueError("cannot build: the dossier declares no state variables")
    # An assignment equation declares its own target: the rule *is* the definition, and the target
    # carries no independent stated value to record (which is why ingestion no longer puts one in
    # `parameters`). A rate equation is different — its target is a state variable and still needs
    # an initial condition, which the check above enforces.
    assignment_targets = {e.target for e in dossier.equations if e.kind is EquationKind.ASSIGNMENT}
    # An initial-assignment target is in the same position: ingestion drops its stated value,
    # because SBML makes that value inert, so the equation is the only thing that declares it.
    initial_assignment_targets = {e.target for e in initial_assignments}
    declared = (
        set(dossier.state_variables)
        | {p.name for p in dossier.parameters}
        | assignment_targets
        | initial_assignment_targets
    )
    undeclared = sorted(
        target for target in {e.target for e in dossier.equations} if target not in declared
    )
    if undeclared:
        raise ValueError(
            "cannot build: equations for variables the dossier does not declare: "
            f"{undeclared}"
        )

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
        # A parameter an equation determines varies over the run; emitting it constant would
        # drop that equation and freeze it at its initial value.
        sbml_parameter.setConstant(parameter.name not in equations)

    # …and the assignment targets that carry no stated value of their own get a value-less,
    # non-constant declaration for their rule to fill, which is what SBML asks for.
    for target in sorted(assignment_targets - {p.name for p in dossier.parameters}):
        if target in set(dossier.state_variables):
            continue
        sbml_parameter = model.createParameter()
        sbml_parameter.setId(target)
        sbml_parameter.setConstant(False)

    # An initial-assignment target is declared value-less too, but *constant*: the assignment sets
    # it once at the start and nothing recomputes it, which is a different model from an
    # assignment rule and has to emit as one.
    already = {p.name for p in dossier.parameters} | assignment_targets
    for target in sorted(initial_assignment_targets - already):
        if target in set(dossier.state_variables):
            continue
        sbml_parameter = model.createParameter()
        sbml_parameter.setId(target)
        sbml_parameter.setConstant(True)

    # State variables first, in their declared order, so a dossier whose equations only govern
    # state variables emits byte-identical SBML to before equations carried a kind.
    ordered = [governing[name] for name in dossier.state_variables] + [
        e for e in dossier.equations
        if e.target not in set(dossier.state_variables)
        and e.kind is not EquationKind.INITIAL_ASSIGNMENT
    ]
    for equation in ordered:
        math = libsbml.parseL3Formula(equation.expression)
        if math is None:
            raise ValueError(
                f"could not parse the rate expression for {equation.target!r}: "
                f"{equation.expression!r}"
            )
        rule = (
            model.createAssignmentRule()
            if equation.kind is EquationKind.ASSIGNMENT
            else model.createRateRule()
        )
        rule.setVariable(equation.target)
        rule.setMath(math)

    for equation in initial_assignments:
        math = libsbml.parseL3Formula(equation.expression)
        if math is None:
            raise ValueError(
                f"could not parse the initial assignment for {equation.target!r}: "
                f"{equation.expression!r}"
            )
        assignment = model.createInitialAssignment()
        assignment.setSymbol(equation.target)
        assignment.setMath(math)

    errors = _fatal_errors(document, libsbml)
    if errors:
        raise ValueError("the built model is not valid SBML: " + "; ".join(errors))
    return str(libsbml.writeSBMLToString(document))


def _rule_names_in(model: Any, target: str) -> set[str]:
    """Every plain identifier a rule's math refers to (not `time`, not function names)."""
    libsbml = _libsbml()
    names: set[str] = set()
    for i in range(model.getNumRules()):
        rule = model.getRule(i)
        if rule.getVariable() != target or rule.getMath() is None:
            continue
        stack = [rule.getMath()]
        while stack:
            node = stack.pop()
            if node.getType() == libsbml.AST_NAME:
                names.add(node.getName())
            stack.extend(node.getChild(k) for k in range(node.getNumChildren()))
    return names


def compare_sbml_to_dossier(sbml: str, dossier: Dossier, *, rel_tol: float = 1e-9) -> list[str]:
    """Report where an adopted SBML model disagrees with the dossier's stated values.

    When reconstruction adopts a shipped model, it must still confirm the model matches the
    manuscript rather than silently trusting the artifact over the paper (spec:
    ``model-reconstruction`` — "Shipped model does not match the dossier"). This parses the
    model's parameters and initial values and reports each value that disagrees with the
    dossier beyond ``rel_tol``. An empty list means no disagreement was found.

    "No disagreement" has to mean the values were compared. A model that carries its rate
    constants as local parameters inside each kinetic law — the common SBML Level 2 idiom —
    declares no global parameters at all, so reading only those compared nothing and returned
    the same empty list as a model that agrees. Local parameters are read too, and a dossier
    value with no counterpart anywhere in the model is itself reported: the manuscript states
    something the artifact does not have, which is exactly the disagreement this check exists
    to surface.

    A species' initial value is read in the convention the model states it in: a model stating
    concentrations sets no initial *amount*, and reading the unset field instead reports every
    species as a mismatch against 0 (or, in Level 3, compares against NaN and so can never
    report a real one). A species stating neither is not compared at all, since there is no
    stated value to disagree with.
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the adopted artifact is not readable SBML")

    # A parameter a rule determines has no stated value to compare against: SBML makes its
    # `value` attribute inert, and the dossier no longer records one. Comparing the dossier's
    # number against that same inert attribute reported agreement on a value neither side had
    # checked — "no disagreement" has to mean the values were compared, which is the rule this
    # function's own docstring already states for local parameters.
    # Assignment rules only. A *rate* rule's target keeps a meaningful `value`: it is the initial
    # condition, and "a parameter plus a rate rule" is the PK/PD idiom this ingester supports on
    # purpose — excluding those undid the fix four lines below, which exists because comparing
    # against species alone read a hundred-fold disagreement in a dose as agreement.
    rule_determined = {
        model.getRule(i).getVariable()
        for i in range(model.getNumRules())
        if model.getRule(i).isAssignment()
    }
    # An initial assignment makes the same attribute inert, and was not in this set: measured on
    # the metformin model, 32 of the dossier's values — every compartment volume among them — were
    # compared against numbers the model computes over rather than reads, and the comparison
    # reported no disagreement. That is this function's own definition of the defect, one construct
    # to the left. Kept separate so the line it produces names the construct that is really there.
    assignment_determined = {
        model.getInitialAssignment(i).getSymbol()
        for i in range(model.getNumInitialAssignments())
    } - rule_determined
    determined = rule_determined | assignment_determined

    def _no_stated_value(kind: str, name: str, value: float) -> str:
        """The line for a dossier element the model's own math determines, naming which construct."""
        construct = "a rule" if name in rule_determined else "an initial assignment"
        return (
            f"{kind} {name}: stated by the dossier ({value}) but {construct} determines it in the "
            "model, so there is no stated value to compare"
        )

    # Every model parameter is *known* — dropping the rule-determined ones from this dict removed
    # them from `known` and `comparable_ics` too, so a faithfully ingested dossier reported its own
    # source file as "not present in the model". What has no stated value to compare is a narrower
    # thing than what the model does not contain.
    all_params = {
        model.getParameter(i).getId(): model.getParameter(i).getValue()
        for i in range(model.getNumParameters())
    }
    sbml_params = {
        name: value for name, value in all_params.items() if name not in determined
    }
    local_values: dict[str, list[float]] = {}
    for i in range(model.getNumReactions()):
        law = model.getReaction(i).getKineticLaw()
        if law is None:
            continue
        for j in range(law.getNumParameters()):
            local = law.getParameter(j)
            if local.isSetValue():
                # A local name shadows nothing global in SBML scoping terms, but for the
                # manuscript's purposes 'k1' is 'k1'. Every value seen under a name is kept, not
                # just the first: L2 models routinely reuse `k1`/`Km`/`Vmax` across reactions with
                # different values, and keeping the first meant a dossier stating the *second* was
                # reported as agreeing with the first — "no disagreement" decided by reaction order.
                local_values.setdefault(local.getId(), []).append(local.getValue())
    sbml_ics: dict[str, float] = {}
    for i in range(model.getNumSpecies()):
        species = model.getSpecies(i)
        if species.isSetInitialAmount():
            sbml_ics[species.getId()] = float(species.getInitialAmount())
        elif species.isSetInitialConcentration():
            compartment = model.getCompartment(species.getCompartment())
            if compartment is None or not compartment.isSetSize():
                continue  # the amount this concentration stands for is unknown; nothing to compare
            sbml_ics[species.getId()] = float(
                species.getInitialConcentration() * compartment.getSize()
            )

    # A compartment's size is a value the dossier can state (a volume of distribution is the most
    # common PK dossier parameter), so it belongs beside the parameters rather than only in the
    # set of names that exist: matching one used to silence the "not present" branch without ever
    # reaching a value comparison, and a dossier volume disagreeing with the model's was reported
    # as agreement.
    sbml_sizes: dict[str, float] = {}
    for i in range(model.getNumCompartments()):
        compartment = model.getCompartment(i)
        if compartment.isSetSize():
            sbml_sizes[compartment.getId()] = float(compartment.getSize())

    # An initial condition can be held as a parameter plus a rate rule — the PK/PD idiom this
    # ingester supports on purpose — so a dossier IC has to be looked for among the parameters too.
    # Comparing against species alone meant a hundred-fold disagreement in a dose read as agreement.
    # One representative per local name for the value lookups, and the full set kept beside it so
    # a name the model holds two values under is reported rather than silently resolved to one.
    for name, values in local_values.items():
        sbml_params.setdefault(name, values[0])
        all_params.setdefault(name, values[0])
    # Comparable values come from `sbml_params` — the rule-determined names are excluded, because
    # their `value` attribute is inert. Building this from `all_params` put those inert numbers
    # back in the comparison, so a dossier stating one agreed with it and the check fell silent
    # exactly where the previous round had made it speak.
    comparable_ics = {**sbml_params, **sbml_sizes, **sbml_ics}

    known = {model.getSpecies(i).getId() for i in range(model.getNumSpecies())}
    known |= {model.getCompartment(i).getId() for i in range(model.getNumCompartments())}
    known |= set(all_params)

    mismatches: list[str] = []
    for parameter in dossier.parameters:
        if parameter.name not in known:
            mismatches.append(
                f"parameter {parameter.name}: stated by the dossier ({parameter.value}) but "
                "not present in the model"
            )
        elif parameter.name in determined:
            # Present in the model, but with no stated value to compare: the model's own math
            # computes it. Said plainly rather than passed over — "no disagreement" has to mean the
            # values were compared, and falling through to nothing here is the silence this check
            # exists to break. It is not the "not present in the model" the branch above reports.
            mismatches.append(_no_stated_value("parameter", parameter.name, parameter.value))
        else:
            # Every value the model holds under this name, the global included: reading only the
            # locals published "model 9.0" for a model whose global is 5.0 — the dossier's own
            # number, and the live value in another reaction — so the mismatch named a value the
            # model does not hold and the several-values wording never fired.
            held = list(local_values.get(parameter.name, ()))
            if parameter.name in all_params and parameter.name not in determined:
                held.append(all_params[parameter.name])
            if held and any(_differs(parameter.value, value, rel_tol) for value in held):
                distinct = sorted(set(held))
                mismatches.append(
                    f"parameter {parameter.name}: dossier {parameter.value} != model "
                    + (
                        f"{distinct[0]}"
                        if len(distinct) == 1
                        else f"{distinct} (the model holds it at several values)"
                    )
                )
                continue
            stated = {**sbml_params, **sbml_sizes}.get(parameter.name)
            if not held and stated is not None and _differs(parameter.value, stated, rel_tol):
                mismatches.append(
                    f"parameter {parameter.name}: dossier {parameter.value} != model {stated}"
                )
    for ic in dossier.initial_conditions:
        if ic.name in determined:
            # The same three cases the parameter branch above distinguishes: the model's own math
            # determines this one, so it IS in the model and has no stated value to compare
            # against. Reported as "not present in the model", which is false about the artifact.
            mismatches.append(_no_stated_value("initial condition", ic.name, ic.value))
        elif ic.name not in comparable_ics:
            # "No disagreement" has to mean the values were compared, so a dossier initial
            # condition with no counterpart anywhere in the model is reported rather than passed
            # over — the parameter branch above already reports its own version of this.
            mismatches.append(
                f"initial condition {ic.name}: stated by the dossier ({ic.value}) but not "
                "present in the model"
            )
        elif _differs(ic.value, comparable_ics[ic.name], rel_tol):
            mismatches.append(
                f"initial condition {ic.name}: dossier {ic.value} != model "
                f"{comparable_ics[ic.name]}"
            )
    # …and the other direction, for the model's *state*. Every check above walks dossier -> model,
    # so a species present in the model and absent from the dossier was never looked at: a dossier
    # missing half a model's state returned no mismatch at all, which
    # `ReconstructionBundle.mismatches` publishes as "checked and agreed". The way in was guarded
    # and the way out was not.
    #
    # Scoped to species, and only for a model this ingester reads as rules. Parameters are excluded
    # because a curated model's local reaction parameters number in the hundreds and a rules-only
    # dossier is not claiming to carry them; a model built from *reactions* is excluded outright
    # because its dossier already carries the `reaction network` gap saying so. Reporting either
    # here would bury the one thing this sweep is for under 119 lines of wolf-crying.
    if model.getNumReactions():
        return mismatches
    stated_by_dossier = (
        {p.name for p in dossier.parameters}
        | {ic.name for ic in dossier.initial_conditions}
        | set(dossier.state_variables)
        # An *assignment* target is a derived observable — fully determined by the other values,
        # so a stored initial amount for it is redundant and reporting it would cry wolf. A *rate*
        # target is not: it needs an initial value, and a rate target the dossier carries no value
        # for is exactly the state variable that went missing.
        | {e.target for e in dossier.equations if e.kind is EquationKind.ASSIGNMENT}
    )
    # Restricted to species the dossier's own rules depend on. `ingest_sbml` skips a `constant` or
    # `boundaryCondition` species on purpose, so reporting every one of them made a rules-only model
    # with an unread fixed input — an ordinary PK/PD shape — permanently unable to return "no
    # disagreement". What matters is a value the equations *need* and the dossier does not carry.
    # Read off the *model*, not off the dossier's surviving equations. Sourcing it from the
    # dossier made the check blind in exactly the case it exists for: a state variable the dossier
    # lost entirely takes its equation with it, so its name was never in `needed` and the sweep
    # reported nothing — "checked and agreed" over a dossier carrying half a model, again.
    # An algebraic rule has no variable, so `getVariable()` returns "" — and `_rule_names_in("")`
    # then matched every one of them and pulled their math in, reporting a species the dossier
    # already declares an `algebraic rules` gap for.
    model_rule_targets = {
        target
        for i in range(model.getNumRules())
        if (target := model.getRule(i).getVariable())
    }
    needed = set(model_rule_targets)
    for target in model_rule_targets:
        needed |= _rule_names_in(model, target)
    # Species *and* the parameter-plus-rateRule idiom this ingester supports on purpose: a
    # PK/PD model that ships no species holds its whole state that way, so sweeping species alone
    # left the class with the most state to lose entirely unchecked.
    # Only *rate* targets, and only parameters the model actually sets. libSBML hands back a
    # default for an unset parameter — 0.0 in L2, NaN in L3 — so an unset parameter whose value
    # comes from an `initialAssignment` was reported as "a value the model gives (nan)" on a
    # faithful dossier.
    rate_targets = {
        target
        for i in range(model.getNumRules())
        if model.getRule(i).isRate() and (target := model.getRule(i).getVariable())
    }
    set_parameters = {
        model.getParameter(i).getId(): float(model.getParameter(i).getValue())
        for i in range(model.getNumParameters())
        if model.getParameter(i).isSetValue()
    }
    stated_values = {
        **sbml_ics,
        **{k: v for k, v in set_parameters.items() if k in rate_targets},
    }
    for name, value in sorted(stated_values.items()):
        if name in needed and name not in stated_by_dossier:
            kind = "a species" if name in sbml_ics else "a rule-driven parameter"
            mismatches.append(
                f"{name}: {kind} the model gives an initial value ({value}) but the dossier "
                "does not state"
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

    # An LP is a steady-state snapshot: a rule, an event, or an initial assignment that moves a
    # flux bound during (or before) the run changes the feasible space this solves over, and
    # reading past them solves a different program than the artifact describes.
    _refuse_unrepresentable_constructs(model, kind="a constraint-based model")

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
        value = parameter.getValue()
        if value != value:  # NaN: set, but not a number
            # The skip above catches an *unset* parameter; a parameter whose value is NaN passes
            # straight through into the bounds, and the LP solver quietly ignores a NaN bound —
            # so the constraint the artifact states simply vanishes and the optimum is judged
            # against a model with one fewer capacity limit.
            raise ValueError(
                f"parameter {parameter.getId()!r} has a NaN value; a flux bound that is not a "
                "number is dropped by the solver, which silently removes the constraint"
            )
        params[parameter.getId()] = value

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
        product = association.getGeneProduct()
        if product not in gene_labels:
            # Falling back to the raw id invents a gene: it enters `model.genes()` and the FROG
            # gene-deletion fingerprint as though the artifact declared it, and an essentiality
            # result is then reported for a gene that does not exist in the model.
            raise ValueError(
                f"a gene-product association references {product!r}, which the model does not "
                "declare as a gene product; the rule names a gene this artifact does not define"
            )
        return gene_labels[product]
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
    # The artifact states a *deterministic* mass-action constant: the law k·∏Aᵢ^sᵢ just verified
    # above. The SSA's propensity is the stochastic form, k·∏(Aᵢ choose sᵢ)·sᵢ! — for a
    # dimerization, n(n−1)/2 rather than n². The two agree only after multiplying by ∏sᵢ!, and
    # without it the sampler runs a reaction with a stoichiometry above one at a fraction of the
    # rate the law it verified prescribes: 2A → B ingested at k tracks dA/dt = −k·A² where the
    # artifact says −2k·A², so the ensemble reproduces a model the file never described.
    stoichiometric_factor = 1
    for power in reactant_powers.values():
        stoichiometric_factor *= factorial(power)
    return float(rate_param.getValue()) * stoichiometric_factor


def _stated_substance_units(model: Any, spec: Any) -> str:
    """The unit id a species' amount is stated in, following both levels' defaulting rules.

    Level 3 defaults a species that omits the attribute to the *model's* `substanceUnits`. Level 2
    has no such model attribute and defaults instead to the predefined `substance` unit — which a
    model may redefine, and four of the six committed Level 2 kinetic models do, as scaled moles
    (1e-9, 1e-9, 1e-3, 1e-6). Reading only the species attribute there returned '' and let a model
    whose amounts are nanomoles through the guard that exists to catch exactly that. `_resolve_unit`
    learned this same Level 2 rule one module over; this is its neighbour.

    An L2 model that neither states nor defines `substance` is left alone: the implicit default is
    `mole`, and refusing every such model would fail far more real work than it protects.
    """
    stated = spec.getSubstanceUnits()
    if stated:
        return str(stated)
    if model.getLevel() == 2:
        return "substance" if model.getUnitDefinition("substance") is not None else ""
    return str(model.getSubstanceUnits())


def _resolved_substance_units(model: Any, unit_id: str) -> str:
    """A species' substance units, following a `unitDefinition` reference to what it means.

    Returns the base kind when the definition is a single unscaled, unmultiplied unit of one — the
    only shape that can be read as a molecule count — and the identifier itself otherwise, so an
    unresolvable or compound unit still reaches the refusal below with its own name in the message.
    """
    if not unit_id:
        return ""
    definition = model.getUnitDefinition(unit_id)
    if definition is None or definition.getNumUnits() != 1:
        return unit_id
    unit = definition.getUnit(0)
    if (
        unit.getExponentAsDouble() != 1.0
        or unit.getScale() != 0
        or unit.getMultiplier() != 1.0
    ):
        return unit_id
    return str(_libsbml().UnitKind_toString(unit.getKind()))


def ingest_spatial_sbml(sbml: str) -> SpatialModel:
    """Parse an SBML Level 3 **spatial** model into what the reaction-diffusion solver runs.

    The last of the six classes to get an ingester, and the roadmap said it was blocked on there
    being no standard single-file format for a reaction-diffusion model. There is one: the SBML
    L3 ``spatial`` package, which the pinned libSBML reads. What it expresses is far wider than
    this class solves, so this reads the intersection and refuses the rest by name:

    * the geometry must be **Cartesian**, in one or two coordinate components, each with a stated
      ``boundaryMin``/``boundaryMax`` — that extent is the domain the grid spans;
    * each spatial species must carry exactly one **isotropic** diffusion coefficient (an
      anisotropic or single-coordinate one is a different equation from ``D ∇²c``);
    * a species must state a uniform initial concentration that nothing else overrides — a
      field-valued initial condition is geometry this does not read, and an initial assignment or a
      rule makes the stated attribute inert, so reading it would carry a profile the model
      replaces. A spatial species SBML holds fixed (a boundary or constant species) is refused for
      the mirror reason: this solver evolves every field it is given;
    * a stated boundary condition must be **zero-flux** — this solver's boundaries are Neumann and
      nothing else, and running a Dirichlet model under them is a different model, quietly;
    * an **advection** coefficient, or a parameter standing for a coordinate, is refused: the first
      is a drift term this scheme does not step, the second a quantity that varies with position,
      and dropping either produces a profile from a model nobody wrote;
    * a **reaction** is read only where it is the first-order decay of one spatial species — the
      one reaction term this solver takes as a number, and the morphogen-gradient case. Any other
      reaction is refused, because a reaction read and dropped is the same silent substitution;
    * the geometry must describe **one domain** and must not state its *shape*: this reader spans
      the coordinate components' extent as an interval or a rectangle, and a stated shape read as
      its bounding box is a region the file does not describe.

    Needs the ``engine`` extra (python-libsbml, which bundles the spatial package).

    No published spatial model is in this repository's corpus and none can be fetched here, so what
    this is validated against is the spec's own reference implementation writing the files it reads
    (``tests/test_spatial_ingest.py`` builds them through libSBML's spatial API, not by hand) —
    not a file from the field. That is a weaker claim than the other five ingesters can make.
    """
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("the artifact is not readable SBML")
    _refuse_unreadable_document(document)

    plugin = model.getPlugin("spatial")
    if plugin is None or not plugin.isSetGeometry():
        raise ValueError(
            "the artifact declares no spatial geometry; a reaction-diffusion model is read from "
            "the SBML L3 spatial package, and without a geometry nothing says what it spans"
        )
    geometry = plugin.getGeometry()
    if geometry.getCoordinateSystem() != libsbml.SPATIAL_GEOMETRYKIND_CARTESIAN:
        raise ValueError(
            "the geometry is not Cartesian; this solver steps a uniform Cartesian grid, and "
            "reading another coordinate system onto it would solve a different equation"
        )
    axes = [
        geometry.getCoordinateComponent(i) for i in range(geometry.getNumCoordinateComponents())
    ]
    if not 1 <= len(axes) <= 2:
        raise ValueError(
            f"the geometry has {len(axes)} coordinate components; this class solves in one or two "
            "dimensions"
        )
    extent: list[float] = []
    for axis in axes:
        if not (axis.isSetBoundaryMin() and axis.isSetBoundaryMax()):
            raise ValueError(
                f"coordinate component {axis.getId()!r} states no boundaryMin/boundaryMax, so the "
                "domain it spans is not stated"
            )
        low, high = axis.getBoundaryMin().getValue(), axis.getBoundaryMax().getValue()
        if not high > low:
            raise ValueError(
                f"coordinate component {axis.getId()!r} spans {low} to {high}, which is not a domain"
            )
        extent.append(float(high - low))

    diffusivities: dict[str, float] = {}
    for i in range(model.getNumParameters()):
        parameter = model.getParameter(i)
        parameter_plugin = parameter.getPlugin("spatial")
        if parameter_plugin is None:
            continue
        if parameter_plugin.isSetAdvectionCoefficient():
            # ∂c/∂t = D∇²c − v·∇c is not the equation this solver steps. Reading the file and
            # ignoring the drift term produces a pure-diffusion profile from a model that drifts,
            # which is the substitution this whole ingester exists to refuse — measured: a
            # velocity of 2.0 read as if it were not there.
            raise ValueError(
                f"parameter {parameter.getId()!r} declares an advection coefficient for "
                f"{parameter_plugin.getAdvectionCoefficient().getVariable()!r}; this solver steps "
                "diffusion with no drift term, and dropping it would run a different model"
            )
        if parameter_plugin.isSetSpatialSymbolReference():
            # A parameter that *is* a coordinate is how a file writes a rate that varies with
            # position. This solver's reaction term is local and space-independent, so the
            # variation would silently vanish.
            raise ValueError(
                f"parameter {parameter.getId()!r} stands for a spatial coordinate "
                f"({parameter_plugin.getSpatialSymbolReference().getSpatialRef()!r}); a quantity "
                "that varies with position is beyond what this solver evaluates"
            )
        if parameter_plugin.isSetBoundaryCondition():
            condition = parameter_plugin.getBoundaryCondition()
            kind = condition.getType()
            # Zero-flux is what this solver imposes. A Dirichlet wall, or a flux that is not zero,
            # is a different problem — and one that would run here without complaint.
            zero_flux = (
                kind == libsbml.SPATIAL_BOUNDARYKIND_NEUMANN
                and parameter.isSetValue()
                and parameter.getValue() == 0.0
            )
            if not zero_flux:
                raise ValueError(
                    f"parameter {parameter.getId()!r} states a boundary condition on "
                    f"{condition.getVariable()!r} that is not zero flux; this solver's boundaries "
                    "are zero-flux Neumann, and running another kind under them is a different "
                    "model with no sign that it happened"
                )
            continue
        if not parameter_plugin.isSetDiffusionCoefficient():
            continue
        coefficient = parameter_plugin.getDiffusionCoefficient()
        if coefficient.getType() != libsbml.SPATIAL_DIFFUSIONKIND_ISOTROPIC:
            raise ValueError(
                f"the diffusion coefficient for {coefficient.getVariable()!r} is not isotropic; "
                "this solver steps D∇²c with one D per species"
            )
        if not parameter.isSetValue():
            raise ValueError(
                f"the diffusion coefficient for {coefficient.getVariable()!r} states no value"
            )
        variable = coefficient.getVariable()
        if variable in diffusivities:
            raise ValueError(
                f"more than one diffusion coefficient is declared for {variable!r}; which one the "
                "model diffuses by is the artifact's to say"
            )
        diffusivities[variable] = float(parameter.getValue())

    # A value the model's own math sets makes the species' `initialConcentration` attribute inert,
    # and reading it anyway reports a starting profile the file overrides — measured: an
    # `initialAssignment` of 42 read as the attribute's 1.0. A rule on a spatial species is its own
    # dynamics running against the PDE. Both are named rather than quietly lost.
    overridden: dict[str, str] = {}
    for i in range(model.getNumInitialAssignments()):
        overridden[model.getInitialAssignment(i).getSymbol()] = "an initial assignment"
    for i in range(model.getNumRules()):
        rule = model.getRule(i)
        if rule.isAssignment() or rule.isRate():
            overridden[rule.getVariable()] = (
                "an assignment rule" if rule.isAssignment() else "a rate rule"
            )

    species: list[str] = []
    initial: dict[str, float] = {}
    for i in range(model.getNumSpecies()):
        entity = model.getSpecies(i)
        entity_plugin = entity.getPlugin("spatial")
        if entity_plugin is None or not entity_plugin.getIsSpatial():
            continue
        name = entity.getId()
        if entity.getBoundaryCondition() or entity.getConstant():
            raise ValueError(
                f"species {name!r} is spatial and is a boundary or constant species, which SBML "
                "holds fixed; this solver evolves every field it is given, so it would spread a "
                "quantity the model says does not move"
            )
        if name in overridden:
            raise ValueError(
                f"species {name!r} is set by {overridden[name]}, which makes its stated initial "
                "concentration inert; the profile this reader would carry is one the model "
                "overrides"
            )
        if name not in diffusivities:
            raise ValueError(
                f"species {name!r} is spatial and declares no diffusion coefficient; how fast it "
                "spreads is what this class solves for"
            )
        if not entity.isSetInitialConcentration():
            raise ValueError(
                f"species {name!r} states no uniform initial concentration; a field-valued initial "
                "condition is geometry this does not read"
            )
        species.append(name)
        initial[name] = float(entity.getInitialConcentration())

    if geometry.getNumDomains() > 1:
        raise ValueError(
            f"the geometry declares {geometry.getNumDomains()} domains; this solver steps one "
            "uniform region, and the interior boundaries between domains are not represented"
        )
    if geometry.getNumGeometryDefinitions() > 0:
        # A geometry definition is the file describing the domain's *shape* — an analytic region, a
        # sampled field, a CSG solid. This reader takes the coordinate components' extent and spans
        # it as an interval or a rectangle, so a stated shape would be quietly replaced by its
        # bounding box.
        raise ValueError(
            "the geometry defines the domain's shape, which this reader does not read; it spans "
            "the stated extent as an interval or a rectangle, and reading a shape as its bounding "
            "box would run the model over a region the file does not describe"
        )

    # The stranded-coefficient check comes first because it is the more specific reason: a model
    # whose only species is not spatial fails both, and "you declared a diffusivity for something
    # that does not diffuse" says which line to look at.
    unmatched = sorted(set(diffusivities) - set(species))
    if unmatched:
        raise ValueError(
            "diffusion coefficients are declared for "
            f"{', '.join(repr(name) for name in unmatched)}, which the model does not mark spatial"
        )
    if not species:
        raise ValueError(
            "no species is marked spatial; this reads a reaction-diffusion model, and a model "
            "where nothing diffuses is not one"
        )
    # A reaction is not decoration: a file whose species decays at 0.7 per unit time, read as pure
    # diffusion, gives a profile the model never produces. The one reaction term this class's
    # solver takes as a number is first-order decay, so that is what is read, and every other shape
    # is refused by name rather than dropped.
    decay: dict[str, float] = {}
    for i in range(model.getNumReactions()):
        reaction = model.getReaction(i)
        reactants = [reaction.getReactant(j) for j in range(reaction.getNumReactants())]
        products = reaction.getNumProducts()
        modifiers = reaction.getNumModifiers()
        decaying = reactants[0].getSpecies() if len(reactants) == 1 else ""
        if (
            len(reactants) != 1
            or products
            or modifiers
            or reactants[0].getStoichiometry() != 1.0
            or decaying not in species
        ):
            raise ValueError(
                f"reaction {reaction.getId()!r} is not the first-order decay of one spatial "
                "species, which is the only reaction term this solver takes as a number; a "
                "reaction read and dropped would give a profile this model never produces"
            )
        if decaying in decay:
            raise ValueError(
                f"more than one decay reaction is declared for {decaying!r}; which rate it decays "
                "at is the artifact's to say"
            )
        decay[decaying] = _mass_action_rate(reaction.getKineticLaw(), {decaying: 1})

    return SpatialModel(
        species=tuple(species),
        diffusivities=tuple(sorted(diffusivities.items())),
        initial=tuple(sorted(initial.items())),
        extent=tuple(extent),
        decay=tuple(sorted(decay.items())),
    )


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
        # Resolved, not compared raw: SBML states a unit by reference, so a species whose own
        # `unitDefinition` *is* `item` was refused under a reason that is false about the file —
        # the un-taught neighbour of `ingest._resolve_unit`, which learned this one level over.
        # The model's own `substanceUnits` is the default for every species that omits the
        # attribute, and libsbml returns '' for such a species — so a model declaring itself in
        # moles walked straight past the guard whose whole purpose is catching that. The sibling
        # ingester already reads the fallback (`ingest.ingest_sbml`, at its species loop); this is its
        # neighbour. (The name cited here was `ingest._read_species`, which has never existed — the
        # only dangling symbol reference among the eighty added today.)
        units = _resolved_substance_units(model, _stated_substance_units(model, spec))
        if units not in ("", "item", "dimensionless"):
            # The SSA counts molecules. A species declared in moles is read verbatim, so 100 mol
            # becomes 100 molecules and every noise statistic the class exists to reproduce — the
            # Fano factor, the CV, the extinction time — is computed for a different system.
            raise ValueError(
                f"species {spec.getId()!r} declares substance units {units!r}; the SSA counts "
                "molecules, so reading its amount verbatim would describe a different system "
                "(use item/dimensionless counts)"
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
            # Rounded silently, this deleted a "0.5 B" product from the network entirely and let a
            # negative stoichiometry drive counts to -297. The reactant side is already protected —
            # `_mass_action_rate` refuses a power that does not match the kinetic law — and this
            # ingester already refuses a non-integer *initial* amount for the same reason. Fractional
            # stoichiometry is ordinary in real models; the SSA cannot represent it, so it is
            # refused rather than rounded into a different network.
            stated = ref.getStoichiometry()
            if not (stated > 0 and abs(stated - round(stated)) <= 1e-9):
                raise ValueError(
                    f"reaction {rxn.getId()!r} produces {stated!r} of {ref.getSpecies()!r}: the "
                    "SSA needs discrete molecule counts, so a product stoichiometry must be a "
                    "positive whole number"
                )
            product_powers[ref.getSpecies()] = product_powers.get(ref.getSpecies(), 0) + int(
                round(stated)
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
    # …and a *species'* own conversion factor, which rescales that species' contribution to every
    # reaction's extent. Refusing only the model-level attribute implemented half of the reason
    # this check states: a species carrying `conversionFactor="cf"` with cf=10 produced 1000 under
    # libRoadRunner and 100 here, and the difference was published as the paper being wrong.
    if any(model.getSpecies(i).isSetConversionFactor() for i in range(model.getNumSpecies())):
        unsupported.append("a species conversionFactor (it rescales that species' amount)")
    for j in range(model.getNumReactions()):
        rxn = model.getReaction(j)
        refs = [rxn.getReactant(k) for k in range(rxn.getNumReactants())]
        refs += [rxn.getProduct(k) for k in range(rxn.getNumProducts())]
        # `constant` is a Level 3 attribute, so on a Level 2 file — which most of the curated
        # corpus is — it is never set and this guard never fired. Level 2 says the same thing with
        # `stoichiometryMath`, and a `A -> n B` with n=5 was read as one B: 500 molecules under
        # libRoadRunner against 100 here, with `reported_mean=500` published as `failed`.
        if any(
            (ref.isSetConstant() and not ref.getConstant())
            or (ref.isSetStoichiometryMath() if hasattr(ref, "isSetStoichiometryMath") else False)
            for ref in refs
        ):
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
    "ingest_spatial_sbml",
    "ingest_stochastic_sbml",
]
