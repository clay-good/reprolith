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
from typing import Any

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Equation, Gap, GapKind, ModelArtifact
from .model import Assumption, Certificate, ClaimAssessment, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    ComparisonMethod,
    ReferenceKind,
    assess_match,
    undetermined_shortfall,
)
from .pins import algorithm_revision

# A network state as node values in sorted-node order, so states hash and sort deterministically.
State = tuple[int, ...]

Rule = Callable[[Mapping[str, int]], int]

#: The largest network this exact oracle enumerates. Fixed-point and attractor analysis here walk
#: the whole 2ⁿ state space, so cost doubles with every node; 2²⁰ ≈ 1M states is minutes of pure
#: Python, while a real signalling model of 60–80 nodes (e.g. CANA's BREAST_CANCER, LEUKEMIA)
#: is astronomically beyond exhaustive enumeration. Above this the oracle refuses fast and clearly
#: rather than hang or exhaust memory — the honest scale boundary of an exact method.
MAX_ENUMERABLE_NODES = 20

#: The most fixed points the scalable SAT path will enumerate before refusing. A well-posed model
#: has a handful; a network dominated by free input nodes has 2^(#inputs) of them, which is a
#: combinatorial blow-up no downstream verdict can use — so the solver stops and says so.
MAX_SAT_FIXED_POINTS = 100_000


class NetworkTooLarge(RuntimeError):
    """Raised when exact attractor analysis or fixed-point enumeration exceeds a tractable bound."""


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

    ``expressions`` optionally carries each node's rule as its source Boolean-expression string
    (what :func:`parse_boolean_network` was given). It is what makes the *scalable* fixed-point
    path possible: a large network's fixed points are found by encoding these expressions to a
    solver rather than enumerating 2ⁿ states. A network built directly from opaque callables has no
    ``expressions`` and so stays enumeration-bound.
    """

    rules: Mapping[str, Callable[[Mapping[str, int]], int]]
    expressions: Mapping[str, str] | None = None

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

    def _states(self) -> Iterable[State]:
        """Every state in the 2ⁿ space, streamed. Guards the exact oracle's scale boundary.

        Refuses a network too large to enumerate (see :data:`MAX_ENUMERABLE_NODES`) with a clear
        error, so a real 60–80-node signalling model fails fast here instead of hanging or
        exhausting memory. Yields lazily so the largest tractable networks never materialise all
        2ⁿ states at once. Stepping a single state (:meth:`step`) is unaffected — only the
        exhaustive fixed-point and attractor paths pass through here.
        """
        n = len(self.nodes)
        if n > MAX_ENUMERABLE_NODES:
            raise NetworkTooLarge(
                f"exhaustive attractor analysis enumerates all 2^{n} states, which is intractable "
                f"for {n} nodes; this exact oracle handles up to {MAX_ENUMERABLE_NODES}. Reduce the "
                f"network (fix or prune nodes) or use a scalable Boolean solver for a model this size"
            )
        for bits in product((0, 1), repeat=n):
            yield tuple(bits)

    def fixed_points(self) -> list[dict[str, int]]:
        """Every steady state: a state the synchronous update maps to itself, sorted.

        Small networks are solved by exact enumeration. A network larger than
        :data:`MAX_ENUMERABLE_NODES` is solved *scalably* — its rule expressions are encoded to a
        SAT solver and every satisfying fixed point enumerated — so real signalling models (60–80
        nodes) are handled in well under a second where 2ⁿ enumeration is impossible. The scalable
        path needs the network's symbolic ``expressions`` (a network built from raw callables has
        none) and the ``sat`` extra (sympy); without either, a too-large network still raises
        :class:`NetworkTooLarge` via the enumeration guard.
        """
        if len(self.nodes) > MAX_ENUMERABLE_NODES and self.expressions is not None:
            return self._fixed_points_sat()
        fixed = [s for s in self._states() if self._step_tuple(s) == s]
        return [self._as_dict(s) for s in sorted(fixed)]

    def _fixed_points_sat(self) -> list[dict[str, int]]:
        """Fixed points via SAT: enumerate every state that satisfies ``xᵢ ⟺ ruleᵢ(x)`` for all i.

        The fixed-point condition is a Boolean formula over the node variables; its satisfying
        assignments are exactly the steady states. Solving it (z3, with a blocking clause added per
        solution so the search is exhaustive over the solution space, not the 2ⁿ state space) is what
        makes large networks tractable. Each solution is a *completed* model and is verified to be a
        genuine fixed point (``step(s) == s``) before it is kept, so a solver-encoding error can
        never pass silently. If the network has more than :data:`MAX_SAT_FIXED_POINTS` fixed points
        (a degenerate network dominated by free inputs), it refuses rather than enumerate a
        combinatorial blow-up. Needs the network's ``expressions`` and the ``sat`` extra (z3).
        """
        z3 = _z3()
        assert self.expressions is not None  # guarded by the caller
        names = self.nodes
        # A free self-input (rule is exactly the node itself, e.g. an input/source node held fixed)
        # is unconstrained at every fixed point, multiplying the count by two. Catch that blow-up up
        # front — instantly — rather than let the blocking-clause loop grind through 2^(#inputs).
        def _identity(expr: str, node_name: str) -> bool:
            return expr.replace("(", "").replace(")", "").replace(" ", "").replace("!", "~") == node_name

        free_inputs = sum(1 for name in names if _identity(self.expressions[name], name))
        if free_inputs and 2**free_inputs > MAX_SAT_FIXED_POINTS:
            raise NetworkTooLarge(
                f"network has {free_inputs} free input nodes, so every fixed point of the rest of "
                f"the network comes in 2^{free_inputs} copies — a combinatorial blow-up past "
                f"{MAX_SAT_FIXED_POINTS}; fix the input nodes to specific values to make the "
                f"steady states well-posed"
            )
        variables = {name: z3.Bool(name) for name in names}
        ops = {
            "and_": lambda xs: z3.And(*xs),
            "or_": lambda xs: z3.Or(*xs),
            "not_": z3.Not,
            "xor_": z3.Xor,
            "const_": z3.BoolVal,
        }
        solver = z3.Solver()
        for name in names:
            solver.add(variables[name] == _translate_rule(self.expressions[name], variables, ops))
        fixed: list[State] = []
        while solver.check() == z3.sat:
            model = solver.model()
            state = tuple(
                1 if z3.is_true(model.eval(variables[name], model_completion=True)) else 0
                for name in names
            )
            if self._step_tuple(state) != state:  # never trust the encoding; re-check definitionally
                raise ValueError("SAT returned a state that is not a fixed point")
            fixed.append(state)
            if len(fixed) > MAX_SAT_FIXED_POINTS:
                raise NetworkTooLarge(
                    f"network has more than {MAX_SAT_FIXED_POINTS} fixed points; refusing to "
                    f"enumerate a combinatorial blow-up (it is dominated by free input nodes)"
                )
            # Block this exact state so the next solve returns a different fixed point.
            solver.add(z3.Or([variables[name] != bool(bit) for name, bit in zip(names, state)]))
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

    def basin_sizes(self) -> list[int]:
        """The size of each synchronous attractor's basin — how many states flow into it.

        Aligned with :meth:`attractors` in :attr:`UpdateScheme.SYNCHRONOUS` order: entry *i* is the
        number of states whose forward synchronous trajectory ends in attractor *i* (its own cycle
        states included). Under synchronous update every state has exactly one successor, so the
        basins partition the state space and the sizes sum to exactly 2ⁿ — the honest answer to
        "which attractor dominates" (e.g. what fraction of initial conditions reach a given
        phenotype). Asynchronous basins are ill-defined (a state can reach several attractors under
        nondeterministic order), so this is synchronous-only.

        Exact and enumeration-bound, like :meth:`attractors`: a network past
        :data:`MAX_ENUMERABLE_NODES` raises :class:`NetworkTooLarge`. Runs in one pass over the state
        space by memoizing each trajectory onto the attractor it reaches.
        """
        attractors = self._sync_attractors()
        resolved: dict[State, int] = {
            state: index for index, cycle in enumerate(attractors) for state in cycle
        }
        for start in self._states():
            path: list[State] = []
            s = start
            while s not in resolved:
                path.append(s)
                s = self._step_tuple(s)
            index = resolved[s]
            for state in path:
                resolved[state] = index
        sizes = [0] * len(attractors)
        for index in resolved.values():
            sizes[index] += 1
        return sizes

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


def _z3() -> Any:
    try:
        import z3
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise NetworkTooLarge(
            "the scalable fixed-point solver for a large network needs the 'sat' extra (z3); "
            "install with pip install 'reprolith[sat]'"
        ) from exc
    return z3


def solver_pin(*, scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS, sat: bool = False) -> EnginePin:
    """The pin naming what actually computed a logical result, and under which update scheme.

    Two things a logical certificate needs and could not previously state. The update scheme is a
    load-bearing modelling choice this module already treats as a first-class gap — the same
    network has different cyclic attractors under synchronous and asynchronous updating, so a
    certificate that omits it names a number a third party cannot reproduce. And a network past
    :data:`MAX_ENUMERABLE_NODES` is not solved by this module's enumeration at all but by z3, whose
    version belongs on the certificate for the same reason the FBA class reads its scipy version:
    a published certificate names the software that solved it.
    """
    from . import __version__  # local: the package imports this module while initializing

    algorithm = f"{scheme.value}-update, "
    if sat:
        z3 = _z3()
        algorithm += f"sat-fixed-points (z3 {z3.get_version_string()})"
    else:
        algorithm += "exhaustive-state-enumeration"
    # The enumerator, the rule compiler, and the attractor comparison are this package, and the
    # package version has never moved — so before this, fixing any of them left every certificate
    # the fix invalidates comparing equal to the current pin and reading as fresh. On the SAT path
    # z3's version moves, but the translation into z3 and the verdict rule still do not.
    algorithm += f" (rev {algorithm_revision('logical', 'oracle', 'certificate')})"
    return EnginePin(engine="reprolith-logical", version=__version__, algorithm=algorithm)


def _translate_boolean_ast(node: ast.AST, symbols: Mapping[str, Any], ops: Mapping[str, Any]) -> Any:
    """Translate an allow-listed Boolean AST into a backend expression via ``ops``.

    The same rule grammar as :func:`_compile_ast`, but emitting whatever a backend builds — a z3
    formula for the SAT path here, and reusable for any other symbolic backend — so the scalable
    path can never diverge from the exact evaluator's grammar. Anything outside the grammar raises.
    ``ops`` supplies ``and_``/``or_``/``not_``/``xor_`` (each taking operands) and ``const_``.
    """
    if isinstance(node, ast.Expression):
        return _translate_boolean_ast(node.body, symbols, ops)
    if isinstance(node, ast.BoolOp):
        subs = [_translate_boolean_ast(v, symbols, ops) for v in node.values]
        if isinstance(node.op, ast.And):
            return ops["and_"](subs)
        if isinstance(node.op, ast.Or):
            return ops["or_"](subs)
        raise ValueError("unsupported boolean operator")
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, (ast.Not, ast.Invert)):
            return ops["not_"](_translate_boolean_ast(node.operand, symbols, ops))
        raise ValueError("unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left = _translate_boolean_ast(node.left, symbols, ops)
        right = _translate_boolean_ast(node.right, symbols, ops)
        if isinstance(node.op, ast.BitAnd):
            return ops["and_"]([left, right])
        if isinstance(node.op, ast.BitOr):
            return ops["or_"]([left, right])
        if isinstance(node.op, ast.BitXor):
            return ops["xor_"](left, right)
        raise ValueError("unsupported binary operator")
    if isinstance(node, ast.Name):
        if node.id not in symbols:
            raise ValueError(f"rule references unknown node {node.id!r}")
        return symbols[node.id]
    if isinstance(node, ast.Constant):
        if node.value in (0, 1, True, False):
            return ops["const_"](bool(node.value))
        raise ValueError(f"unsupported constant {node.value!r} (only 0/1)")
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def _translate_rule(expr: str, symbols: Mapping[str, Any], ops: Mapping[str, Any]) -> Any:
    """Parse a Boolean rule string to a backend expression, via the same safe AST as compilation."""
    try:
        tree = ast.parse(expr.replace("!", "~"), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid Boolean rule {expr!r}: {exc}") from exc
    return _translate_boolean_ast(tree, symbols, ops)


def parse_boolean_network(rules: Mapping[str, str]) -> BooleanNetwork:
    """Build a :class:`BooleanNetwork` from rule *expressions*, one per node.

    ``rules`` maps each node to a Boolean expression over the other nodes; a rule naming a node
    the network does not declare raises, so a typo is surfaced rather than silently treated as a
    constant. This is the JSON-friendly network form an agent or an ingester supplies. The source
    expressions are retained on the network so a large one can take the scalable fixed-point path.
    """
    node_names = set(rules)
    compiled = {name: compile_boolean_rule(expr, node_names) for name, expr in rules.items()}
    return BooleanNetwork(compiled, expressions=dict(rules))


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
            # A miss the caller did not categorize is published as uncategorized rather
            # than raised, so this front-end can say a network did not reproduce.
            attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
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
    "MAX_ENUMERABLE_NODES",
    "MAX_SAT_FIXED_POINTS",
    "BooleanNetwork",
    "LogicalClaim",
    "NetworkTooLarge",
    "Rule",
    "State",
    "UpdateScheme",
    "certify_logical",
    "compile_boolean_rule",
    "judge_attractor_set",
    "judge_steady_state",
    "logical_dossier",
    "parse_boolean_network",
    "solver_pin",
    "validate_logical",
]
