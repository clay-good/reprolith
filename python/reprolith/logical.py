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
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import product
from typing import Any

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Equation, Gap, GapKind, ModelArtifact
from .enums import Verdict
from .model import Assumption, Certificate, ClaimAssessment, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    ComparisonMethod,
    ReferenceKind,
    Tolerance,
    assess_match,
    judge_scalar,
    not_evaluable,
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

#: The largest network whose *asynchronous reachability* this module measures. Reachability needs
#: the state graph's edges rather than one successor per state, so it holds n·2ⁿ of them where an
#: enumeration holds 2ⁿ: at :data:`MAX_ENUMERABLE_NODES` that is twenty million edges to answer one
#: sensitivity question. Above this the measurement says it is out of reach rather than being
#: attempted — the same honesty as the enumeration ceiling, at the size this computation actually
#: costs rather than at the one its neighbour costs.
MAX_REACHABILITY_NODES = 16

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
        none) and the ``sat`` extra (z3); without either, a too-large network still raises
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
        return [size for _, size in self._sync_basins()]

    def _sync_basins(self) -> list[tuple[tuple[State, ...], int]]:
        """Each synchronous attractor paired with the size of its basin, in :meth:`attractors` order.

        The computation :meth:`basin_sizes` publishes half of. A caller that needs to know *which*
        attractor a basin belongs to — judging a reported basin does — would otherwise call
        :meth:`attractors` and :meth:`basin_sizes` and walk the 2ⁿ space twice to line them up.
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
        return list(zip(attractors, sizes))

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
class ReportedBasin:
    """A published **basin of attraction**: which attractor, and how much of the space reaches it.

    The class's third reproduction target, and the one that is about the *state space* rather than
    about the attractors in it. It is what Boolean-model papers report when they argue a network is
    biologically robust — Li et al. 2004's yeast cell-cycle network reaches its G1 steady state from
    1764 of 2048 initial states, which is the sentence that paper is remembered for — and two
    networks can agree on every attractor while disagreeing entirely on how much of the space
    reaches each one. :meth:`BooleanNetwork.basin_sizes` has computed it since the class was
    written; nothing could certify it.

    ``attractor`` is the attractor the basin belongs to, given as its cycle (one state for a fixed
    point) and identified the way :func:`judge_attractor_set` identifies one — by its set of states,
    not by where the cycle starts.

    The basin itself is reported one of two ways, and which one it is decides how it is judged:

    ``states``
        the count a paper prints (1764). Judged **exactly**: a basin is a number of states in a
        finite space, so there is no numerical error for a tolerance to absorb, and a band here
        would pass a network that reaches its attractor from eighty states fewer.
    ``fraction``
        the share a paper prints as a percentage (86%). Judged by relative error, because a printed
        percentage is a rounded number.

    Both are read against **this** network's state space, whose size the protocol line records: a
    paper that fixed its input nodes before counting has a smaller space than the one Reprolith
    enumerates, and a fraction compared across two different denominators is not a comparison. The
    count is the safer of the two to publish for exactly that reason — it disagrees loudly where a
    fraction would quietly be judged against the wrong whole.
    """

    attractor: Sequence[Mapping[str, int]]
    states: int | None = None
    fraction: float | None = None
    #: A paper-stated or reviewer-set band for a reported ``fraction``. Refused beside ``states``
    #: rather than ignored, since an exact comparison has no band.
    tolerance: Tolerance | None = None

    def __post_init__(self) -> None:
        if not self.attractor:
            raise ValueError("a reported basin must name the attractor whose basin it is")
        if (self.states is None) == (self.fraction is None):
            raise ValueError(
                "a reported basin is either a count of states or a share of the state space; "
                "give exactly one of states= and fraction="
            )
        if self.states is not None and self.states < 1:
            # An attractor's own states are in its basin, so a basin of zero states is not a small
            # basin: it says the attractor is not there. That is a claim about the attractor set,
            # and judging it here would compare a count against an attractor nothing identified.
            raise ValueError(
                f"a basin of {self.states} states says the attractor is not one of this network's "
                "at all, which is a claim about its attractor set rather than about a basin; "
                "report it as an attractor-set claim"
            )
        if self.states is not None and self.tolerance is not None:
            raise ValueError(
                "a basin reported as a count of states is judged exactly — a count in a finite "
                "state space has no numerical error for a tolerance to absorb; report the "
                "paper's rounded share as fraction= to have it judged in a band"
            )
        if self.fraction is not None and not 0.0 < self.fraction <= 1.0:
            raise ValueError(
                f"a basin is a share of the state space above zero, so {self.fraction!r} is not "
                "one (86% is given as 0.86; a basin of none of it says the attractor is absent, "
                "which is an attractor-set claim)"
            )


def _attractor_label(cycle: Sequence[Mapping[str, int]]) -> str:
    """How a certificate line names the attractor a basin belongs to.

    The nodes that are *on* in its first state, which is how these papers name a phenotype, plus
    the cycle's length where it has one — an all-zero attractor would otherwise render as an empty
    brace and read like a missing value.
    """
    # The cycle's smallest state, not the one the claim happened to start at: an attractor is
    # identified by its set of states, so two claims about the same 2-cycle must not render two
    # different names for it.
    first = dict(min(tuple(sorted(state.items())) for state in cycle))
    on = [node for node, value in first.items() if value]
    named = "+".join(on) if on else "all nodes off"
    return named if len(cycle) == 1 else f"{named} (a {len(cycle)}-state cycle)"


def _async_reachable_states(network: BooleanNetwork, target: frozenset[State]) -> int:
    """How many states can reach ``target`` under asynchronous updating — the async counterpart.

    A synchronous basin is a partition: every state has one successor, so it flows to exactly one
    attractor. Asynchronously it has one successor per unstable node, so "the basin of X" can only
    mean the states from which X is *reachable*, and those sets overlap. This counts that, by
    walking the async state graph backwards from the attractor.

    Only ever asked of networks within :data:`MAX_REACHABILITY_NODES`, since it holds the graph's
    edges rather than one successor per state.
    """
    predecessors: dict[State, list[State]] = {}
    for state in network._states():
        for successor in network._async_successors(state):
            predecessors.setdefault(successor, []).append(state)
    seen = set(target)
    frontier = list(target)
    while frontier:
        state = frontier.pop()
        for previous in predecessors.get(state, ()):
            if previous not in seen:
                seen.add(previous)
                frontier.append(previous)
    return len(seen)


def judge_basin_size(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: ReportedBasin,
    network: BooleanNetwork,
    scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a reported basin of attraction against the basin this network actually has.

    Three ways this abstains rather than answering, and each is a different fact about the run:

    * the claim is judged under **asynchronous** updating, where a basin is not defined — a state
      can reach several attractors, the sets overlap, and nothing partitions the space. Answering
      with the synchronous number would publish a number the claim did not ask for;
    * the network is past :data:`MAX_ENUMERABLE_NODES`, so the space cannot be walked at all;
    * neither of those, and the comparison happens.

    A reported attractor this network does not have is **not** an abstention: no state flows to an
    attractor that is not there, so the observed basin is zero and the claim fails, with the
    discrepancy saying which of the two is the disagreement. Abstaining there would hide the
    strongest kind of non-reproduction this class can find behind "could not be judged".

    A non-match requires an ``attribution``.
    """
    if scheme is UpdateScheme.ASYNCHRONOUS:
        return not_evaluable(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reason=(
                "this claim is judged under asynchronous updating, where a basin of attraction is "
                "not defined: a state has one successor per unstable node, so it can reach several "
                "attractors and the basins overlap rather than partitioning the state space. The "
                "synchronous count exists and is a different quantity, so it is not reported here"
            ),
            reference_kind=ReferenceKind.NUMERIC,
        )
    try:
        basins = network._sync_basins()
    except NetworkTooLarge as exc:
        return not_evaluable(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reason=(
                f"a basin is counted by walking the whole state space, and {exc}. The claim is "
                "unjudged rather than judged on a sample: a basin counted over part of the space "
                "is a different number, not an approximate one"
            ),
            reference_kind=ReferenceKind.NUMERIC,
        )
    target = frozenset(network._as_tuple(state) for state in reported.attractor)
    total = 2 ** len(network.nodes)
    observed = next((size for cycle, size in basins if frozenset(cycle) == target), None)
    absent = (
        None
        if observed is not None
        else (
            f"the reported attractor is not one of this network's {len(basins)} synchronous "
            "attractors, so no state flows to it"
        )
    )
    counted = 0 if observed is None else observed
    protocol = (
        f"basin of {_attractor_label(reported.attractor)}: {counted} of "
        f"2^{len(network.nodes)} = {total} states"
    )
    if reported.states is not None:
        assessment = assess_match(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            matched=observed == reported.states,
            method=ComparisonMethod.BASIN_SIZE_MATCH,
            exact_on="the number of states in the basin",
            discrepancy=absent
            or (
                f"{counted} state{'' if counted == 1 else 's'} flow"
                f"{'s' if counted == 1 else ''} to it against the reported {reported.states}"
            ),
            reference_kind=ReferenceKind.NUMERIC,
            attribution=attribution,
            assumption_qualified=assumption_qualified,
        )
    else:
        assessment = judge_scalar(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            # A reported basin is above zero by construction (a zero one is refused as an
            # attractor-set claim), so the relative error always has a magnitude to normalize by
            # and there is no scale to supply. It is the *observed* side that can be zero here,
            # which needs none.
            reported=reported.fraction or 0.0,
            predicted=counted / total,
            tolerance=reported.tolerance,
            reference_kind=ReferenceKind.NUMERIC,
            attribution=attribution,
            assumption_qualified=assumption_qualified,
        )
        if absent is not None and assessment.discrepancy is not None:
            assessment = replace(
                assessment, discrepancy=f"{assessment.discrepancy} — {absent}"
            )
    # The size of the space this basin was counted in, on the line that records what a verdict
    # rests on. It is the per-claim degree of freedom that moves the number: a paper that fixed its
    # inputs before counting has a smaller denominator than the one enumerated here, and without it
    # a reader cannot see that two percentages were taken of different wholes.
    return replace(assessment, protocol=protocol)


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
    #: A reported **attractor set** — each attractor a sequence of its cycle's states — where the
    #: paper reports one rather than a single steady state. With it the claim is judged by
    #: :func:`judge_attractor_set` and ``reported`` is not read; without it, by
    #: :func:`judge_steady_state`. This is where the update scheme starts to matter: fixed points
    #: are the same under both schemes, and cyclic attractors are not.
    attractors: Sequence[Sequence[Mapping[str, int]]] | None = None
    #: The update scheme the claim's source states, when it states one. ``None`` means it does not
    #: — the run then uses synchronous updating, and where that choice can change the verdict the
    #: certificate carries a load-bearing assumption saying so, with the difference measured. The
    #: class spec has called an unstated scheme load-bearing since the dossier was written; until
    #: this field existed, a *stated* one had no way to reach the run.
    scheme: UpdateScheme | None = None
    #: A reported **basin of attraction** — how much of the state space reaches one attractor —
    #: where the paper reports one. With it the claim is judged by :func:`judge_basin_size` and
    #: neither ``reported`` nor ``attractors`` is read.
    basin: ReportedBasin | None = None
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)

    def __post_init__(self) -> None:
        if self.basin is not None and self.attractors is not None:
            raise ValueError(
                f"claim {self.claim_id!r} reports both an attractor set and a basin size. They are "
                "two claims about one network and one assessment carries one verdict, so judging "
                "them together would publish the basin's verdict over the set's quantity; certify "
                "them as two claims"
            )

    @property
    def update_scheme(self) -> UpdateScheme:
        """The scheme this claim is actually judged under — its own, or this engine's default."""
        return self.scheme or UpdateScheme.SYNCHRONOUS

    @property
    def scheme_is_reprolith_s(self) -> bool:
        """Whether the scheme was Reprolith's choice rather than something the source stated."""
        return self.scheme is None


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


#: Why a fixed-point verdict does not depend on the update scheme, in the words both surfaces use.
#:
#: The engine has always *acted* on this — an unstated scheme is qualified only where it could
#: change the answer, and a fixed point is never that case — and only the inline linter ever said
#: it. A reader of a logical certificate saw a pin naming synchronous updating over a verdict about
#: a network whose paper may update asynchronously, with nothing on the page to tell them the two
#: agree here. The linter's caller was told; the certificate's reader had to know.
SCHEME_INDEPENDENT = (
    "a fixed point is a fixed point under every scheme, so this verdict does not rest on the "
    "synchronous updating the pin names"
)


def search_protocol(nodes: int) -> str:
    """How much of the state space a logical verdict rests on.

    The update scheme and the solver are already on the pin; this is the size of the space and
    whether it was walked exhaustively or searched. A reader can tell from it which of the two
    paths produced the number, and how much of the network the check actually saw.
    """
    if nodes <= MAX_ENUMERABLE_NODES:
        return f"{nodes} nodes, exhaustive enumeration of all 2^{nodes} states"
    return f"{nodes} nodes, SAT search (2^{nodes} states is beyond exhaustive enumeration)"


def solver_pin_for(
    *, nodes: int, scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS
) -> EnginePin:
    """The pin for a network of this size — which path ran is a fact, not a caller's choice.

    :func:`solver_pin` takes ``sat`` from the caller, and a caller who passes the wrong one
    publishes a certificate whose pin contradicts its own protocol line: "every one of 2^25 states
    was walked" over a space z3 searched, with z3's version nowhere on it. The node count already
    decides the path (:data:`MAX_ENUMERABLE_NODES`), so read it from the network rather than asking.
    """
    return solver_pin(scheme=scheme, sat=nodes > MAX_ENUMERABLE_NODES)


def _pin_names_sat(engine_pin: EnginePin) -> bool:
    """Whether a pin says the SAT path produced the number, by the token :func:`solver_pin` writes.

    A pin with no algorithm names no path, so it does not name this one — and for a network that
    needs z3 that silence is itself the overclaim the caller is refused for.
    """
    return "sat-fixed-points" in (engine_pin.algorithm or "")


def _pin_names_enumeration(engine_pin: EnginePin) -> bool:
    """Whether a pin says the exhaustive enumerator produced the number."""
    return "exhaustive-state-enumeration" in (engine_pin.algorithm or "")


def require_pin_matches_path(engine_pin: EnginePin, *, node_counts: Iterable[int]) -> None:
    """Refuse a pin that does not name the path the networks actually took.

    The protocol line on each assessment says which of the two paths ran; the pin says which
    software ran. Nothing made them agree, so a hand-built pin could announce exhaustive
    enumeration of a state space z3 searched — the stronger claim, and the false one. Raises rather
    than correcting, because the pin also carries a version this module must not invent.
    """
    counts = tuple(node_counts)
    if not counts:
        return
    needs_sat = tuple(n > MAX_ENUMERABLE_NODES for n in counts)
    if len(set(needs_sat)) > 1:
        raise ValueError(
            "these claims span both the enumeration and the SAT path, and one pin cannot name "
            "both; certify them separately, each under its own solver_pin_for(nodes=...)"
        )
    # Positively naming the path, not merely not-naming the wrong one — the same rule the
    # certificate builder and the load path apply to the protocol these claims will carry. A pin
    # that names neither used to satisfy this and then be refused two layers down, which is two
    # guards disagreeing about one certificate.
    from .persistence import require_pin_names_protocol_path

    # The certificate-level rule, applied to the protocol these claims will carry, so this
    # front-end cannot answer differently from the builder and the load path — three
    # implementations of one rule gave two answers about the same certificate.
    require_pin_names_protocol_path(search_protocol(counts[0]), engine_pin.algorithm)
    if needs_sat[0] and not _pin_names_sat(engine_pin):
        raise ValueError(
            f"a network past {MAX_ENUMERABLE_NODES} nodes is solved by z3, not by enumeration, "
            f"but the pin says {engine_pin.algorithm!r}; use solver_pin_for(nodes=...)"
        )
    if not needs_sat[0] and not _pin_names_enumeration(engine_pin):
        raise ValueError(
            f"every network here is within {MAX_ENUMERABLE_NODES} nodes and was enumerated "
            f"exhaustively, which the pin ({engine_pin.algorithm!r}) does not say; "
            "use solver_pin_for(nodes=...)"
        )


def _basin_scheme_sensitivity(claim: LogicalClaim) -> dict[str, Any]:
    """What an unstated update scheme costs a **basin** claim — measured, like its sibling.

    A basin presupposes the single successor synchronous updating gives every state: that is what
    makes the basins partition the space. Under asynchronous updating they do not, and the nearest
    comparable quantity is **reachability** — from how many states the attractor can be reached at
    all — which is what a paper reporting basins for an asynchronous model means. So an unstated
    scheme is a genuine ambiguity here, and it is settled by computing both rather than by
    qualifying every basin certificate on principle:

    * the two counts **agree**: every state that can reach this attractor also flows to it, so the
      reading cannot move the number and no assumption is minted;
    * they **differ**: the verdict rests on this engine's reading and the basis carries both
      counts;
    * the network is past a ceiling: out of reach, which is not the same as agreement.

    Two ceilings apply, and they are different sizes because the two computations are: the basin
    needs one successor per state (:data:`MAX_ENUMERABLE_NODES`), and the reachability needs the
    async graph's edges (:data:`MAX_REACHABILITY_NODES`).
    """
    assert claim.basin is not None  # only called for a basin claim
    network = parse_boolean_network(claim.rules)
    nodes = len(network.nodes)
    if nodes > MAX_REACHABILITY_NODES:
        return {
            "comparable": False,
            "basis": (
                "the claim's source names no update scheme, so this run counted the states whose "
                "synchronous trajectory ends in this attractor. Under asynchronous updating a "
                "basin does not partition the state space and the comparable quantity is "
                f"reachability, which this network's {nodes} nodes put past the "
                f"{MAX_REACHABILITY_NODES} that measurement can walk — so unlike a smaller "
                "network, this one cannot be shown to give the same answer either way"
            ),
        }
    target = frozenset(network._as_tuple(state) for state in claim.basin.attractor)
    synchronous = next(
        (size for cycle, size in network._sync_basins() if frozenset(cycle) == target), 0
    )
    if synchronous == 0:
        # The reported attractor is not one of this network's synchronous attractors, so the claim
        # has already failed on the attractor rather than on the count. Whether the scheme is what
        # that failure rests on is a real question with a computable answer: an attractor absent
        # synchronously can exist asynchronously, and then the disagreement may be the reading.
        if target in _attractor_ids(network, UpdateScheme.ASYNCHRONOUS):
            return {
                "comparable": True,
                "agree": False,
                "basis": (
                    "the claim's source names no update scheme, so this run used synchronous "
                    "updating — under which the reported attractor does not exist, which is why "
                    "no state flows to it. It *is* an attractor under asynchronous updating, so "
                    "this verdict may rest on the reading rather than on the network"
                ),
            }
        return {
            "comparable": True,
            "agree": True,
            "why": (
                "the reported attractor is not one of this network's attractors under either "
                "scheme, so no reading of 'basin' produces the reported number and the scheme is "
                "not what this verdict rests on"
            ),
        }
    reachable = _async_reachable_states(network, target)
    if synchronous == reachable:
        return {
            "comparable": True,
            "agree": True,
            "why": (
                f"every one of the {reachable} states that can reach this attractor under "
                "asynchronous updating also flows to it synchronously, so the two readings of "
                "'basin' give the same number here"
            ),
        }
    return {
        "comparable": True,
        "agree": False,
        "basis": (
            "the claim's source names no update scheme, so this run counted the "
            f"{synchronous} states whose synchronous trajectory ends in this attractor. A basin "
            "means something else under asynchronous updating — the basins overlap rather than "
            "partitioning the space, and the comparable quantity is reachability, which holds "
            f"{reachable} states here. The number this verdict rests on depends on which of the "
            "two the source meant"
        ),
    }


def scheme_sensitivity(claim: LogicalClaim) -> dict[str, Any] | None:
    """What this claim's update scheme costs it: the same network's attractors under the other one.

    ``None`` where the claim states its own scheme — nothing was assumed, so there is nothing to
    measure the cost of.

    The measurement is **exact**, which makes it unlike every other sensitivity in this package:
    attractors are enumerated rather than sampled or integrated, so "the two schemes agree" is a
    proof and not a bound. Two outcomes matter and they are different findings:

    ``the schemes agree``
        the scheme is not load-bearing *for this claim*, whatever the spec says about the class.
        Every fixed-point claim is in this case by construction — a fixed point is a fixed point
        under either scheme — and so is any network whose synchronous attractors are all fixed
        points. Minting an assumption there would qualify a verdict that cannot move.

        The comparison is therefore of **what the claim was judged on**, not of attractor sets in
        general: this compared attractor sets for every claim at first, and reported the toggle
        switch's spurious synchronous 2-cycle as grounds to qualify a *steady-state* verdict that
        the 2-cycle cannot touch.
    ``the schemes differ``
        the verdict rests on a choice this engine made, and the difference is reported as a count
        rather than asserted: the toggle switch's spurious synchronous 2-cycle is exactly this.

    A network past :data:`MAX_ENUMERABLE_NODES` cannot have its attractors enumerated at all, so
    the comparison is out of reach and says so rather than reading as agreement.
    """
    if not claim.scheme_is_reprolith_s:
        return None
    if claim.basin is not None:
        # A basin claim must not reach the shortcut below, which would read "this claim reports no
        # attractor set, so it is judged on a fixed point, so the schemes agree" — true of neither
        # half. What the scheme costs a basin is a different question with a different answer.
        return _basin_scheme_sensitivity(claim)
    if claim.attractors is None:
        # The claim is judged on a *fixed point*, and a fixed point is one under either scheme: a
        # state whose synchronous successor is itself has no unstable node to flip. So the answer
        # is available without running anything, and it is a proof rather than a measurement.
        # Comparing attractor *sets* here instead — which this function did first — reported the
        # toggle switch's spurious synchronous 2-cycle as a reason to qualify a steady-state
        # verdict that cannot move, which is measuring the wrong quantity and would have
        # downgraded every fixed-point certificate this class publishes.
        return {
            "comparable": True,
            "agree": True,
            "why": (
                "this claim is judged on a fixed point, and a fixed point is one under either "
                "scheme — a state whose synchronous successor is itself has no unstable node to "
                "flip, so no run is needed to know the schemes agree here"
            ),
        }
    network = parse_boolean_network(claim.rules)
    if len(network.nodes) > MAX_ENUMERABLE_NODES:
        return {
            "comparable": False,
            "why": (
                f"this network has {len(network.nodes)} nodes, past the {MAX_ENUMERABLE_NODES} "
                "an attractor enumeration can reach, so what the other scheme would produce "
                "cannot be computed here"
            ),
        }
    under = {
        scheme: _attractor_ids(network, scheme)
        for scheme in (UpdateScheme.SYNCHRONOUS, UpdateScheme.ASYNCHRONOUS)
    }
    judged = under[claim.update_scheme]
    other = next(scheme for scheme in under if scheme is not claim.update_scheme)
    return {
        "comparable": True,
        "agree": judged == under[other],
        "scheme": claim.update_scheme.value,
        "other_scheme": other.value,
        "attractors": len(judged),
        "other_attractors": len(under[other]),
        "only_under_judged": len(judged - under[other]),
        "only_under_other": len(under[other] - judged),
    }


def require_pin_matches_scheme(engine_pin: EnginePin, *, schemes: Iterable[UpdateScheme]) -> None:
    """Refuse a pin that does not name the update scheme the claims were actually judged under.

    The sibling of :func:`require_pin_matches_path`, and the same defect it exists to prevent:
    :func:`solver_pin` takes a scheme from the caller and nothing made it agree with what was
    computed, so a certificate could announce asynchronous updating over a synchronous
    enumeration. On the one class whose own specification says the scheme changes which attractors
    exist, that is a certificate carrying two accounts of how its number was produced with the
    stronger one false.

    One pin cannot name two schemes, so claims judged under different ones are refused rather than
    silently certified under whichever the pin happens to say.
    """
    wanted = set(schemes)
    if not wanted:
        return
    if len(wanted) > 1:
        raise ValueError(
            "these claims are judged under both update schemes and one pin cannot name both; "
            "certify them separately, each under its own solver_pin(scheme=...)"
        )
    scheme = wanted.pop()
    algorithm = engine_pin.algorithm or ""
    if f"{scheme.value}-update" not in algorithm:
        raise ValueError(
            f"these claims were judged under {scheme.value} updating and the pin says "
            f"{algorithm!r}; use solver_pin(scheme=UpdateScheme.{scheme.name}) or "
            "solver_pin_for(nodes=..., scheme=...)"
        )


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
    # Materialized before use: the claims are iterated twice below (once to judge, once to attach
    # the protocol), and a generator is exhausted by the first pass — the zip then yielded nothing
    # and an earned not-reproduced was published as an empty, blocked certificate.
    claims = tuple(claims)
    # The pin has to name the path these networks actually take before any of them is judged: the
    # protocol line below says which path ran, and a pin that disagrees with it publishes two
    # contradictory accounts of how one number was computed.
    require_pin_matches_path(engine_pin, node_counts=[len(claim.rules) for claim in claims])
    # …and the scheme, for exactly the same reason. The pin can name one (`solver_pin(scheme=)`)
    # and nothing made it agree with what was judged, so a certificate could announce asynchronous
    # updating over a synchronous enumeration — the stronger claim, and the false one, on the class
    # whose own spec says the scheme changes which attractors exist.
    require_pin_matches_scheme(engine_pin, schemes=[claim.update_scheme for claim in claims])
    assessments = [
        _judge_logical_claim(claim)
        for claim in claims
    ]
    # What was actually searched. The update scheme and the solver are on the pin already; the
    # size of the state space and whether it was enumerated or solved are what tell a reader
    # which of the two the number came from, and how much of the network the check saw.
    assessments = [
        replace(
            a,
            protocol=" — ".join(
                # The judge's own clause, where it has one, is appended rather than overwritten: a
                # basin is counted in a state space whose size only the judge knows, and dropping
                # it leaves two percentages taken of different wholes looking comparable.
                part for part in (
                    search_protocol(len(claim.rules)),
                    a.protocol,
                    # Only for a claim judged as a fixed point. A cyclic attractor is *not*
                    # scheme-independent — it is the case the assumption below exists for — and
                    # printing this beside one would say the opposite of what that assumption says
                    # three lines down.
                    SCHEME_INDEPENDENT
                    if claim.attractors is None and claim.basin is None
                    else "",
                ) if part
            ),
        )
        for a, claim in zip(assessments, claims)
    ]
    # The counterpart of the spatial class's boundary assumption, and selective in the way that one
    # is not: an unstated scheme is only load-bearing where it could change the answer, and whether
    # it could is *computable* here. A fixed-point claim is never in that case — a fixed point is
    # one under either scheme — so qualifying it would downgrade a verdict that cannot move.
    scheme_assumptions = tuple(
        assumption
        for claim, assessment in zip(claims, assessments)
        if (assumption := _scheme_assumption(claim, assessment)) is not None
    )
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=(*assumptions, *scheme_assumptions),
    )


def _judge_logical_claim(claim: LogicalClaim) -> ClaimAssessment:
    """Judge one claim by what it reports: an attractor set, or a single steady state.

    ``judge_attractor_set`` has been the class's answer to a reported attractor set since the class
    was written, and no front-end could reach it — the milestone script re-implemented the
    comparison rather than calling it, so the one place the update scheme changes an answer was
    reachable from tests alone.
    """
    network = parse_boolean_network(claim.rules)
    # A miss the caller did not categorize is published as uncategorized rather than raised, so
    # this front-end can say a network did not reproduce.
    attribution = claim.shortfall or undetermined_shortfall(claim.quantity)
    if claim.basin is not None:
        return judge_basin_size(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.basin,
            network=network,
            scheme=claim.update_scheme,
            attribution=attribution,
            assumption_qualified=claim.assumption_qualified,
        )
    if claim.attractors is not None:
        return judge_attractor_set(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.attractors,
            network=network,
            scheme=claim.update_scheme,
            attribution=attribution,
            assumption_qualified=claim.assumption_qualified,
        )
    return judge_steady_state(
        claim_id=claim.claim_id,
        quantity=claim.quantity,
        source_location=claim.source_location,
        reported=claim.reported,
        network=network,
        attribution=attribution,
        assumption_qualified=claim.assumption_qualified,
    )


def _scheme_assumption(claim: LogicalClaim, assessment: ClaimAssessment) -> Assumption | None:
    """The load-bearing assumption an unstated update scheme earns — where it earns one.

    Three cases, and the distinction between the first two is the whole point of measuring rather
    than asserting:

    * the claim states its scheme, or the two schemes produce the same attractors: **no
      assumption**. Nothing was assumed in the first case, and in the second the choice provably
      cannot move this verdict;
    * they differ: a load-bearing assumption whose basis carries the difference as a count;
    * the network is past the enumeration ceiling: a load-bearing assumption saying the comparison
      is out of reach, which is not the same as saying the schemes agree.

    Attached only where a verdict was drawn — an assumption on an abstention would describe a
    judgment nobody made, and being load-bearing it would downgrade the certificate on that
    claim's behalf.
    """
    if assessment.verdict is Verdict.NOT_EVALUABLE:
        return None
    sensitivity = scheme_sensitivity(claim)
    if sensitivity is None or sensitivity.get("agree"):
        return None
    if (stated := sensitivity.get("basis")) is not None:
        # A sensitivity that knows why it is load-bearing states it. The two sentences below are
        # about attractor *sets*, and neither is true of a basin: it is not a count of attractors,
        # and its out-of-reach case is a different ceiling from the enumeration one.
        basis = stated
    elif sensitivity["comparable"]:
        basis = (
            "the claim's source names no update scheme, so this run used synchronous updating — "
            "and on this network the choice is not free: it has "
            f"{sensitivity['attractors']} attractor(s) under {sensitivity['scheme']} updating "
            f"against {sensitivity['other_attractors']} under {sensitivity['other_scheme']}, with "
            f"{sensitivity['only_under_judged']} that exist only under the one judged. A "
            "synchronous limit cycle need not survive asynchronous updating"
        )
    else:
        basis = (
            "the claim's source names no update scheme, so this run used synchronous updating. "
            f"{sensitivity['why']} — so unlike a smaller network, this one cannot be shown to give "
            "the same answer either way"
        )
    judged = (
        "the basin judged here was"
        if claim.basin is not None
        else "the attractors judged here were"
    )
    return Assumption(
        id=f"logical-scheme-{claim.claim_id}",
        description=(
            f"{judged} computed under synchronous updating; the claim's source states no scheme"
        ),
        chosen="synchronous updating",
        basis=basis,
        load_bearing=True,
        alternatives=("asynchronous updating (terminal strongly connected sets)",),
        # A scheme is something a paper states, so an author *can* close this one — unlike the
        # spatial wall, which is a limit of the solver. The queue ranks the two differently for
        # exactly that reason.
        author_can_close=True,
    )


__all__ = [
    "MAX_ENUMERABLE_NODES",
    "search_protocol",
    "MAX_SAT_FIXED_POINTS",
    "BooleanNetwork",
    "LogicalClaim",
    "MAX_REACHABILITY_NODES",
    "ReportedBasin",
    "NetworkTooLarge",
    "Rule",
    "State",
    "UpdateScheme",
    "certify_logical",
    "compile_boolean_rule",
    "judge_attractor_set",
    "judge_basin_size",
    "require_pin_matches_scheme",
    "scheme_sensitivity",
    "judge_steady_state",
    "logical_dossier",
    "parse_boolean_network",
    "require_pin_matches_path",
    "solver_pin",
    "solver_pin_for",
    "validate_logical",
]
