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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import product

from .model import ClaimAssessment
from .oracle import Attribution, ComparisonMethod, ReferenceKind, assess_match

# A network state as node values in sorted-node order, so states hash and sort deterministically.
State = tuple[int, ...]


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


__all__ = [
    "BooleanNetwork",
    "State",
    "judge_attractor_set",
    "judge_steady_state",
]
