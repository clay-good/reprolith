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
from itertools import product

from .certificate import build_certificate
from .model import Assumption, Certificate, ClaimAssessment, EnginePin, PaperIdentity
from .oracle import Attribution, ComparisonMethod, ReferenceKind, assess_match

# A network state as node values in sorted-node order, so states hash and sort deterministically.
State = tuple[int, ...]

Rule = Callable[[Mapping[str, int]], int]


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

    def attractors(self) -> list[tuple[dict[str, int], ...]]:
        """Every synchronous attractor (fixed points and limit cycles), deterministically ordered.

        Each attractor is returned as its cycle of states, rotated to start at the
        lexicographically smallest state so the same attractor always renders identically; the
        list is sorted by that starting state. A fixed point is a length-1 cycle.
        """
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
        ordered = sorted(found.values())
        return [tuple(self._as_dict(s) for s in cycle) for cycle in ordered]


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


def _attractor_ids(network: BooleanNetwork) -> set[frozenset[State]]:
    return {
        frozenset(network._as_tuple(state) for state in cycle) for cycle in network.attractors()
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
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a reported set of attractors against the network's computed attractors.

    ``reported`` is a sequence of attractors, each a sequence of states (its cycle). The claim
    reproduces when the reported set equals the computed set; a reported attractor absent from the
    computed set, or an unexpected extra one, makes it fail and is named in the discrepancy. A
    non-match requires an ``attribution``.
    """
    reported_ids = {
        frozenset(network._as_tuple(state) for state in cycle) for cycle in reported
    }
    computed_ids = _attractor_ids(network)
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
    "certify_logical",
    "compile_boolean_rule",
    "judge_attractor_set",
    "judge_steady_state",
    "parse_boolean_network",
]
