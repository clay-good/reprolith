"""The scalable SAT fixed-point path is correct and handles real large Boolean networks.

Above `MAX_ENUMERABLE_NODES` the logical oracle cannot walk the 2ⁿ state space, so `fixed_points()`
switches to a SAT encoding (`xᵢ ⟺ ruleᵢ(x)`) solved by z3. This test pins three things:

1. **Correctness vs the trusted method** — on small networks the SAT path returns exactly what the
   exhaustive enumerator does, over many random networks. Two independent algorithms agreeing is a
   non-circular check of the encoding.
2. **A real large model** — the 60-node T-LGL leukemia signalling network's 71 fixed points, which
   2ⁿ enumeration could never reach, reproduced against an independent tool (sympy generated the
   committed reference; z3 here reproduces its exact set, verified by SHA-256) with every state
   re-checked to be a genuine fixed point.
3. **The blow-up guard** — an input-dominated network refuses fast rather than enumerating 2^(#inputs).

Needs the `sat` extra (z3); skips without it. The large-model reference needs no CANA or sympy at
test time — only the committed data.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

pytest.importorskip("z3", reason="the 'sat' extra (z3-solver) is not installed")

from reprolith import (  # noqa: E402
    MAX_SAT_FIXED_POINTS,
    NetworkTooLarge,
    parse_boolean_network,
)

_REF = json.loads(
    (Path(__file__).parent.parent / "datasets" / "logical" / "cross_validation"
     / "scalable_fixed_points.json").read_text(encoding="utf-8")
)


def _random_rules(n: int, k: int, seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    names = [f"n{i}" for i in range(n)]
    rules: dict[str, str] = {}
    for name in names:
        inputs = rng.sample(names, k)
        terms = []
        for _ in range(rng.randint(1, 3)):
            lits = [
                (f"!{x}" if rng.random() < 0.5 else x)
                for x in rng.sample(inputs, rng.randint(1, k))
            ]
            terms.append("(" + " & ".join(lits) + ")")
        rules[name] = " | ".join(terms)
    return rules


@pytest.mark.parametrize("seed", range(30))
def test_sat_fixed_points_match_exhaustive_enumeration(seed: int) -> None:
    # The SAT encoding must return exactly the enumerator's fixed points — a non-circular check of
    # two independent algorithms on 12-node networks small enough to enumerate in full.
    network = parse_boolean_network(_random_rules(12, 3, seed))
    assert network._fixed_points_sat() == network.fixed_points()


def test_reproduces_the_leukemia_fixed_points_at_scale() -> None:
    # 60 nodes: 2⁶⁰ states, impossible to enumerate. The SAT path reproduces the independent
    # (sympy) reference's exact fixed-point set — checked by count and SHA-256 — and every returned
    # state is verified to be a genuine fixed point.
    entry = _REF["models"]["leukemia"]
    network = parse_boolean_network(entry["rules"])
    assert len(network.nodes) == entry["n_nodes"]

    fixed = network.fixed_points()
    assert len(fixed) == entry["n_fixed_points"]
    for state in fixed:
        assert network.step(state) == state  # genuinely a steady state

    names = network.nodes
    encoded = sorted("".join(str(state[n]) for n in names) for state in fixed)
    digest = hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()
    assert digest == entry["fixed_points_sha256"]


def test_input_dominated_network_refuses_the_combinatorial_blow_up() -> None:
    # A network of many free self-inputs has 2^(#inputs) fixed points; the solver must refuse fast,
    # not grind through the blocking-clause enumeration.
    n = MAX_SAT_FIXED_POINTS.bit_length() + 5  # 2^n comfortably exceeds the cap
    rules = {f"n{i}": f"n{i}" for i in range(n)}
    with pytest.raises(NetworkTooLarge, match="free input nodes"):
        parse_boolean_network(rules).fixed_points()
