"""The logical / Boolean-network model class oracle (spec: ``logical-class``; roadmap #9).

Reprolith's third *distinct* oracle. A logical model has no continuous trajectory and no
optimization; its reproducible result is a discrete-dynamics claim — a steady state (fixed
point) or the set of attractors a network settles into. Judging it by exact attractor analysis,
alongside curve-matching and linear programming, is a second proof that the engine is
oracle-agnostic: the same dossier → reconstruction → oracle → certificate contracts carry a class
whose comparison shares nothing with the other two.

Boolean-network attractor analysis is exact and dependency-free, so — unlike the ODE and
constraint-based classes, whose simulators live behind optional engine extras — this class carries
no deferred half. The oracle here *computes* the attractors it judges (synchronous updating),
purely and deterministically, and the judge maps a match to the shared :class:`ClaimAssessment`
contract so a logical verdict carries the same tolerance provenance and attribution as any other.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from itertools import product

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Equation, Gap, GapKind, ModelArtifact
from .model import Assumption, Certificate, ClaimAssessment, EnginePin, PaperIdentity
from .oracle import Attribution, ComparisonMethod, ReferenceKind, assess_match

# A network state as node values in sorted-node order, so states hash and sort deterministically.
State = tuple[int, ...]

Rule = Callable[[Mapping[str, int]], int]


class UpdateScheme(str, Enum):
    """How a Boolean network advances — a load-bearing modelling choice.

    Under **synchronous** updating every node advances at once, so the dynamics are deterministic
    and an attractor is a simple cycle. Under **asynchronous** updating any single unstable node
    may flip, so a state can have several successors and an attractor is a terminal strongly
    connected set of states. The two schemes share the same fixed points but can differ on cyclic
    attractors, which is exactly why an unstated scheme is a first-class gap for this class
    (spec: logical-class — "Update scheme is load-bearing").
    """

    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


@dataclass(frozen=True, eq=False)
class BooleanNetwork:
    """A Boolean network: each node's update rule as a function of the current state.

    ``rules`` maps every node name to a callable taking the current state (a mapping of node ->
    0/1) and returning that node's next value (0 or 1). Nodes are the sorted rule keys, so every
    state is a canonical tuple in that order. A fixed input node is expressed as a rule that
    returns its own current value.
    """

    rules: Mapping[str, Callable[[Mapping[str, int]], int]]

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(sorted(self.rules))

    def _as_tuple(self, state: Mapping[str, int]) -> State:
        if set(state) != set(self.rules):
            raise ValueError("a state must assign exactly the network's nodes")
        return tuple(1 if state[n] else 0 for n in self.nodes)

    def _as_dict(self, state: State) -> dict[str, int]:
        return dict(zip(self.nodes, state))

    def _step_tuple(self, state: State) -> State:
        current = self._as_dict(state)
        return tuple(1 if self.rules[n](current) else 0 for n in self.nodes)

    def step(self, state: Mapping[str, int]) -> dict[str, int]:
        """One synchronous update: every node advances simultaneously."""
        return self._as_dict(self._step_tuple(self._as_tuple(state)))

    def _states(self) -> list[State]:
        return [tuple(bits) for bits in product((0, 1), repeat=len(self.nodes))]

    def fixed_points(self) -> list[dict[str, int]]:
        """Every steady state: a state the synchronous update maps to itself, sorted."""
        fixed = [s for s in self._states() if self._step_tuple(s) == s]
        return [self._as_dict(s) for s in sorted(fixed)]

    def attractors(
        self, scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS
    ) -> list[tuple[dict[str, int], ...]]:
        """Every attractor (fixed points and cyclic attractors) under ``scheme``, ordered.

        Synchronous attractors are simple cycles, each rotated to start at the lexicographically
        smallest state; asynchronous attractors are terminal strongly connected sets of states,
        returned sorted. A fixed point is a single-state attractor either way. In both cases the
        list is sorted by the attractor's smallest state, so the output is deterministic.
        """
        if scheme is UpdateScheme.ASYNCHRONOUS:
            cycles = self._async_attractors()
        else:
            cycles = self._sync_attractors()
        return [tuple(self._as_dict(s) for s in cycle) for cycle in cycles]

    def _sync_attractors(self) -> list[tuple[State, ...]]:
        found: dict[frozenset[State], tuple[State, ...]] = {}
        for start in self._states():
            index: dict[State, int] = {}
            trail: list[State] = []
            s = start
            while s not in index:
                index[s] = len(trail)
                trail.append(s)
                s = self._step_tuple(s)
            cycle = trail[index[s] :]  # from the first repeated state onward
            canon = frozenset(cycle)
            if canon not in found:
                pivot = cycle.index(min(cycle))
                found[canon] = tuple(cycle[pivot:] + cycle[:pivot])
        return [found[k] for k in sorted(found, key=min)]

    def _async_successors(self, s: State) -> list[State]:
        """The asynchronous successors of ``s``: flip each single node that is unstable.

        A node is unstable when its current value differs from its update rule's value; flipping
        one such node is one asynchronous transition. A state with no unstable node is a fixed
        point and has no successors.
        """
        target = self._step_tuple(s)
        successors = []
        for i in range(len(s)):
            if s[i] != target[i]:
                flipped = list(s)
                flipped[i] = target[i]
                successors.append(tuple(flipped))
        return successors

    def _async_attractors(self) -> list[tuple[State, ...]]:
        """Asynchronous attractors: the terminal strongly connected components of the async graph.

        A set of states is an attractor when the dynamics, once inside, cannot leave — it is a
        strongly connected component with no edge to any other component. Found with an iterative
        Tarjan SCC pass (linear in the graph, so it scales past the per-state reachability approach)
        followed by a terminal-component filter. Iterative rather than recursive so a large state
        space cannot overflow the call stack.
        """
        index: dict[State, int] = {}
        lowlink: dict[State, int] = {}
        on_stack: set[State] = set()
        scc_stack: list[State] = []
        component_of: dict[State, int] = {}
        components: list[list[State]] = []
        counter = 0

        for root in self._states():
            if root in index:
                continue
            work: list[tuple[State, list[State], int]] = [(root, self._async_successors(root), 0)]
            index[root] = lowlink[root] = counter
            counter += 1
            scc_stack.append(root)
            on_stack.add(root)
            while work:
                node, successors, i = work[-1]
                recursed = False
                while i < len(successors):
                    child = successors[i]
                    i += 1
                    if child not in index:
                        work[-1] = (node, successors, i)
                        index[child] = lowlink[child] = counter
                        counter += 1
                        scc_stack.append(child)
                        on_stack.add(child)
                        work.append((child, self._async_successors(child), 0))
                        recursed = True
                        break
                    if child in on_stack:
                        lowlink[node] = min(lowlink[node], index[child])
                if recursed:
                    continue
                work[-1] = (node, successors, i)
                if lowlink[node] == index[node]:
                    component: list[State] = []
                    while True:
                        member = scc_stack.pop()
                        on_stack.discard(member)
                        component_of[member] = len(components)
                        component.append(member)
                        if member == node:
                            break
                    components.append(component)
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

        terminal: list[tuple[State, ...]] = []
        for cid, component in enumerate(components):
            if all(
                component_of[succ] == cid
                for state in component
                for succ in self._async_successors(state)
            ):
                terminal.append(tuple(sorted(component)))
        return sorted(terminal, key=min)


def _compile_ast(node: ast.AST, nodes: Container[str]) -> Rule:
    """Compile an allow-listed Boolean-expression AST node into a state -> 0/1 callable.

    Only Boolean structure is permitted — ``and``/``or``/``not`` and their bitwise spellings
    ``&``/``|``/``^``/``~``, node names, and the constants 0/1 — so a rule string can never
    execute arbitrary code. Anything outside that grammar (a call, an attribute, an unknown
    node) raises, surfacing the problem rather than evaluating it.
    """
    if isinstance(node, ast.Expression):
        return _compile_ast(node.body, nodes)
    if isinstance(node, ast.BoolOp):
        subs = [_compile_ast(v, nodes) for v in node.values]
        if isinstance(node.op, ast.And):
            return lambda s: 1 if all(f(s) for f in subs) else 0
        if isinstance(node.op, ast.Or):
            return lambda s: 1 if any(f(s) for f in subs) else 0
        raise ValueError("unsupported boolean operator")
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, (ast.Not, ast.Invert)):
            operand = _compile_ast(node.operand, nodes)
            return lambda s: 1 - operand(s)
        raise ValueError("unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left, right = _compile_ast(node.left, nodes), _compile_ast(node.right, nodes)
        if isinstance(node.op, ast.BitAnd):
            return lambda s: 1 if left(s) and right(s) else 0
        if isinstance(node.op, ast.BitOr):
            return lambda s: 1 if left(s) or right(s) else 0
        if isinstance(node.op, ast.BitXor):
            return lambda s: left(s) ^ right(s)
        raise ValueError("unsupported binary operator")
    if isinstance(node, ast.Name):
        name = node.id
        if name not in nodes:
            raise ValueError(f"rule references unknown node {name!r}")
        return lambda s: 1 if s[name] else 0
    if isinstance(node, ast.Constant):
        if node.value in (0, 1, True, False):
            value = int(bool(node.value))
            return lambda s: value
        raise ValueError(f"unsupported constant {node.value!r} (only 0/1)")
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def compile_boolean_rule(expr: str, nodes: Container[str]) -> Rule:
    """Compile a Boolean rule expression (e.g. ``"A & !B"``) into a state -> 0/1 callable.

    Accepts ``and``/``or``/``not`` and the bitwise ``&``/``|``/``^``/``~`` spellings, the ``!``
    negation common in the literature, node names, parentheses, and the constants 0/1. Parsing is
    safe: the expression is compiled from an allow-listed AST, never ``eval``-ed.
    """
    # ``!`` is the field's usual negation but not Python syntax; normalize it to the unary ``~``,
    # which the AST allow-list already handles with the same 1 - operand semantics.
    normalized = expr.replace("!", "~")
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid Boolean rule {expr!r}: {exc}") from exc
    return _compile_ast(tree, nodes)


def parse_boolean_network(rules: Mapping[str, str]) -> BooleanNetwork:
    """Build a :class:`BooleanNetwork` from rule *expressions*, one per node.

    ``rules`` maps each node to a Boolean expression over the other nodes; a rule naming a node
    the network does not declare raises, so a typo is surfaced rather than silently treated as a
    constant. This is the JSON-friendly network form an agent or an ingester supplies.
    """
    node_names = set(rules)
    compiled = {name: compile_boolean_rule(expr, node_names) for name, expr in rules.items()}
    return BooleanNetwork(compiled)


def _attractor_ids(
    network: BooleanNetwork, scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS
) -> set[frozenset[State]]:
    return {
        frozenset(network._as_tuple(state) for state in cycle)
        for cycle in network.attractors(scheme)
    }


def judge_steady_state(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: Mapping[str, int],
    network: BooleanNetwork,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a reported steady state: is it a fixed point of the network?

    ``reported`` assigns every node a 0/1 value; the claim reproduces when that exact state is
    among the network's synchronous fixed points. A non-match requires an ``attribution``.
    """
    target = network._as_tuple(reported)
    fixed = {network._as_tuple(fp) for fp in network.fixed_points()}
    matched = target in fixed
    discrepancy = (
        "reported steady state is a fixed point"
        if matched
        else f"reported state is not a fixed point (network has {len(fixed)} fixed point(s))"
    )
    return assess_match(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        matched=matched,
        method=ComparisonMethod.ATTRACTOR_SET_MATCH,
        discrepancy=discrepancy,
        reference_kind=ReferenceKind.NUMERIC,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def judge_attractor_set(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: Sequence[Sequence[Mapping[str, int]]],
    network: BooleanNetwork,
    scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a reported set of attractors against the network's computed attractors.

    ``reported`` is a sequence of attractors, each a sequence of states (its cycle). The claim
    reproduces when the reported set equals the set the network produces under ``scheme`` — the
    update scheme matters, since a cyclic attractor under synchronous updating may not survive
    asynchronous updating. A reported attractor absent from the computed set, or an unexpected
    extra one, makes it fail and is named in the discrepancy. A non-match requires an
    ``attribution``.
    """
    reported_ids = {
        frozenset(network._as_tuple(state) for state in cycle) for cycle in reported
    }
    computed_ids = _attractor_ids(network, scheme)
    matched = reported_ids == computed_ids
    missing = len(reported_ids - computed_ids)
    extra = len(computed_ids - reported_ids)
    discrepancy = (
        f"reproduced {len(computed_ids)} attractor(s), all reported"
        if matched
        else f"{missing} reported attractor(s) not found, {extra} unexpected"
    )
    return assess_match(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        matched=matched,
        method=ComparisonMethod.ATTRACTOR_SET_MATCH,
        discrepancy=discrepancy,
        reference_kind=ReferenceKind.NUMERIC,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


@dataclass(frozen=True)
class LogicalClaim:
    """A published logical steady-state claim to reproduce: a network and a reported fixed point.

    ``rules`` is the JSON-friendly network form — each node mapped to a Boolean rule expression
    over the others (e.g. ``{"A": "!B", "B": "!A"}``). ``reported`` is the steady state the paper
    claims the network holds. ``shortfall`` supplies the root cause a non-pass verdict requires.
    """

    claim_id: str
    quantity: str
    rules: Mapping[str, str]
    reported: Mapping[str, int]
    source_location: str
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)


def validate_logical(dossier: Dossier) -> list[str]:
    """Structural problems that make a logical dossier ill-formed; empty when well-formed.

    On top of the shared checks, the rule expressions (carried as the dossier's equations) must
    parse and reference only declared nodes, and the update scheme's load-bearing status must be
    honest — an unstated scheme is a load-bearing gap, because synchronous and asynchronous updating
    can yield different attractors (spec: logical-class — "Update scheme is load-bearing").
    """
    problems = dossier.validate()
    nodes = {expr.target for expr in dossier.equations}
    rules = {expr.target: expr.expression for expr in dossier.equations}
    for target, expression in rules.items():
        try:
            compile_boolean_rule(expression, nodes)
        except ValueError as exc:
            problems.append(f"rule for node {target!r}: {exc}")
    scheme_gaps = [g for g in dossier.gaps if g.kind is GapKind.UPDATE_SCHEME]
    for gap in scheme_gaps:
        if not gap.load_bearing:
            problems.append("an unstated update scheme must be recorded as a load-bearing gap")
    return problems


def logical_dossier(
    entry: str,
    *,
    rules: Mapping[str, str],
    source_location: str,
    claims: Sequence[DossierClaim] = (),
    update_scheme: UpdateScheme | None = None,
    model: ModelArtifact | None = None,
) -> Dossier:
    """Assemble a well-formed logical dossier, or raise if it is ill-formed.

    ``rules`` maps each node to its Boolean update rule (recorded as the dossier's equations, each
    citing ``source_location``); the nodes become the dossier's state variables. ``update_scheme``
    is the stated synchronous/asynchronous scheme — when ``None`` it is recorded as a load-bearing
    :class:`~reprolith.dossier.Gap`, because the scheme changes the attractors. ``model`` is the
    optional adopted SBML-qual artifact. Validated by :func:`validate_logical`; a structural problem
    is an error, never a silently-accepted dossier.
    """
    equations = tuple(
        Equation(target=node, expression=expr, source_location=source_location)
        for node, expr in sorted(rules.items())
    )
    gaps: tuple[Gap, ...] = ()
    if update_scheme is None:
        gaps = (Gap(
            element="update scheme",
            kind=GapKind.UPDATE_SCHEME,
            detail="the paper does not state synchronous vs asynchronous updating",
            load_bearing=True,
        ),)
    dossier = Dossier(
        entry=entry,
        state_variables=tuple(sorted(rules)),
        equations=equations,
        claims=tuple(claims),
        gaps=gaps,
        artifacts=(model,) if model is not None else (),
    )
    problems = validate_logical(dossier)
    if problems:
        raise ValueError("ill-formed logical dossier: " + "; ".join(problems))
    return dossier


def certify_logical(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[LogicalClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Assemble a certificate of logical steady-state verdicts through the shared builder.

    The logical counterpart of ``certify_constraint_based``: each claim's network is parsed and its
    reported steady state judged with :func:`judge_steady_state`, and the certificate is built by
    the same rule and scope flag as every other class — demonstrating the shared contracts carry
    the logical class (spec: logical-class — "Shared contracts carry the new class"). Needs no
    engine extra; the attractor analysis is exact and pure.
    """
    assessments = [
        judge_steady_state(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.reported,
            network=parse_boolean_network(claim.rules),
            attribution=claim.shortfall,
            assumption_qualified=claim.assumption_qualified,
        )
        for claim in claims
    ]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


__all__ = [
    "BooleanNetwork",
    "LogicalClaim",
    "Rule",
    "State",
    "UpdateScheme",
    "certify_logical",
    "compile_boolean_rule",
    "judge_attractor_set",
    "judge_steady_state",
    "logical_dossier",
    "parse_boolean_network",
    "validate_logical",
]
