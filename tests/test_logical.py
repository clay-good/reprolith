"""The logical / Boolean-network model class oracle (spec: logical-class; roadmap #9).

The third distinct oracle: discrete attractor analysis, no continuous trajectory, no
optimization, and — because Boolean-network analysis is exact — no deferred simulator. These
tests use small networks whose fixed points and cycles are known by hand.
"""

from __future__ import annotations

import pytest
from reprolith import (
    Attribution,
    BooleanNetwork,
    FailureMode,
    Fault,
    Verdict,
    compile_boolean_rule,
    judge_attractor_set,
    judge_steady_state,
    lint_steady_state,
    parse_boolean_network,
)

# A toggle switch: two mutually repressing nodes. Synchronous dynamics have two fixed points —
# (A=1,B=0) and (A=0,B=1) — and a 2-cycle between (0,0) and (1,1).
_TOGGLE = BooleanNetwork({"A": lambda s: 1 - s["B"], "B": lambda s: 1 - s["A"]})

# A single self-activating node: two fixed points, (X=0) and (X=1).
_SELF = BooleanNetwork({"X": lambda s: s["X"]})

_SHORTFALL = Attribution(
    mode=FailureMode.AMBIGUOUS_LOGIC_RULE,
    implicated="node B update rule (paper states 'B off' without the input)",
    fault=Fault.MANUSCRIPT,
)


# --- attractor computation ---------------------------------------------------------


def test_fixed_points_of_the_toggle_switch() -> None:
    fps = _TOGGLE.fixed_points()
    assert {tuple(sorted(fp.items())) for fp in fps} == {
        (("A", 0), ("B", 1)),
        (("A", 1), ("B", 0)),
    }


def test_attractors_include_the_two_cycle() -> None:
    attractors = _TOGGLE.attractors()
    sizes = sorted(len(cycle) for cycle in attractors)
    assert sizes == [1, 1, 2]  # two fixed points and one 2-cycle
    two_cycle = next(cycle for cycle in attractors if len(cycle) == 2)
    states = {tuple(sorted(s.items())) for s in two_cycle}
    assert states == {(("A", 0), ("B", 0)), (("A", 1), ("B", 1))}


def test_step_is_synchronous() -> None:
    assert _TOGGLE.step({"A": 0, "B": 0}) == {"A": 1, "B": 1}
    assert _TOGGLE.step({"A": 1, "B": 0}) == {"A": 1, "B": 0}  # a fixed point holds


def test_attractor_computation_is_deterministic() -> None:
    assert _TOGGLE.attractors() == _TOGGLE.attractors()


def test_state_must_assign_every_node() -> None:
    with pytest.raises(ValueError):
        _TOGGLE.step({"A": 1})  # missing B


# --- steady-state (fixed-point) reproduction ---------------------------------------


def test_reported_steady_state_that_is_a_fixed_point_reproduces() -> None:
    a = judge_steady_state(
        claim_id="ss", quantity="steady state", source_location="Fig 3",
        reported={"A": 1, "B": 0}, network=_TOGGLE,
    )
    assert a.verdict is Verdict.REPRODUCED
    assert a.method == "attractor-set-match"
    assert "is a fixed point" in a.discrepancy


def test_reported_steady_state_that_is_not_a_fixed_point_fails() -> None:
    a = judge_steady_state(
        claim_id="ss", quantity="steady state", source_location="Fig 3",
        reported={"A": 1, "B": 1}, network=_TOGGLE, attribution=_SHORTFALL,
    )
    assert a.verdict is Verdict.FAILED
    assert a.root_cause == "ambiguous-or-missing-logic-rule"


def test_steady_state_non_pass_requires_attribution() -> None:
    with pytest.raises(ValueError):
        judge_steady_state(
            claim_id="ss", quantity="steady state", source_location="Fig 3",
            reported={"A": 1, "B": 1}, network=_TOGGLE,  # not a fixed point, no attribution
        )


# --- attractor-set reproduction ----------------------------------------------------


def test_reported_attractor_set_matching_all_reproduces() -> None:
    reported = [
        [{"A": 1, "B": 0}],
        [{"A": 0, "B": 1}],
        [{"A": 0, "B": 0}, {"A": 1, "B": 1}],
    ]
    a = judge_attractor_set(
        claim_id="att", quantity="attractors", source_location="Table 1",
        reported=reported, network=_TOGGLE,
    )
    assert a.verdict is Verdict.REPRODUCED
    assert "all reported" in a.discrepancy


def test_missing_attractor_is_surfaced_as_failure() -> None:
    # Report only the two fixed points, omitting the 2-cycle: the extra computed attractor fails it.
    reported = [[{"A": 1, "B": 0}], [{"A": 0, "B": 1}]]
    a = judge_attractor_set(
        claim_id="att", quantity="attractors", source_location="Table 1",
        reported=reported, network=_TOGGLE,
        attribution=Attribution(
            mode=FailureMode.UNSPECIFIED_UPDATE_SCHEME,
            implicated="update scheme (async would drop the 2-cycle)", fault=Fault.MANUSCRIPT,
        ),
    )
    assert a.verdict is Verdict.FAILED
    assert "1 unexpected" in a.discrepancy
    assert a.root_cause == "unspecified-update-scheme"


def test_self_activating_node_has_two_fixed_points() -> None:
    a = judge_attractor_set(
        claim_id="att", quantity="attractors", source_location="Fig 1",
        reported=[[{"X": 0}], [{"X": 1}]], network=_SELF,
    )
    assert a.verdict is Verdict.REPRODUCED


def test_repeated_judgment_is_identical() -> None:
    def run():
        return judge_steady_state(
            claim_id="ss", quantity="steady state", source_location="Fig 3",
            reported={"A": 0, "B": 1}, network=_TOGGLE,
        )

    assert run() == run()


# --- Boolean-rule parsing (the JSON-friendly network form) -------------------------


def test_parse_boolean_network_matches_the_callable_toggle() -> None:
    parsed = parse_boolean_network({"A": "not B", "B": "not A"})
    assert parsed.fixed_points() == _TOGGLE.fixed_points()
    assert parsed.attractors() == _TOGGLE.attractors()


def test_rule_parser_supports_both_spellings_and_operators() -> None:
    rule = compile_boolean_rule("(A & !B) | (C ^ 1)", {"A", "B", "C"})
    assert rule({"A": 1, "B": 0, "C": 0}) == 1  # A and not B
    assert rule({"A": 0, "B": 1, "C": 0}) == 1  # C xor 1 == 1
    assert rule({"A": 0, "B": 1, "C": 1}) == 0


def test_rule_referencing_an_unknown_node_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown node"):
        parse_boolean_network({"A": "not Z"})  # Z is not a declared node


def test_rule_with_a_function_call_is_rejected() -> None:
    # The parser allow-lists Boolean structure only, so a rule can never execute arbitrary code.
    with pytest.raises(ValueError, match="unsupported"):
        compile_boolean_rule("__import__('os')", {"A"})


def test_invalid_rule_syntax_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid Boolean rule"):
        compile_boolean_rule("A &", {"A"})


# --- inline linter -----------------------------------------------------------------


def test_lint_steady_state_passes_a_fixed_point() -> None:
    result = lint_steady_state({"A": "!B", "B": "!A"}, {"A": 1, "B": 0})
    assert result.verdict is Verdict.REPRODUCED
    assert result.method == "attractor-set-match"
    assert result.scope.machine  # the scope flag travels with the verdict


def test_lint_steady_state_fails_a_non_fixed_point() -> None:
    result = lint_steady_state({"A": "!B", "B": "!A"}, {"A": 1, "B": 1})
    assert result.verdict is Verdict.FAILED


def test_lint_steady_state_requires_a_full_state() -> None:
    with pytest.raises(ValueError, match="exactly the network's nodes"):
        lint_steady_state({"A": "!B", "B": "!A"}, {"A": 1})  # missing B


def test_lint_steady_state_is_deterministic() -> None:
    a = lint_steady_state({"X": "X"}, {"X": 1})
    b = lint_steady_state({"X": "X"}, {"X": 1})
    assert a == b
