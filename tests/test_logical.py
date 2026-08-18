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
    UpdateScheme,
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


def test_basin_sizes_of_the_toggle_switch() -> None:
    # The toggle's synchronous state space (4 states) splits into three basins: the two fixed
    # points 01 and 10 each attract only themselves, and the spurious 00<->11 two-cycle attracts
    # both its own states — so the basins are 1, 1, 2 and tile the whole space.
    attractors = _TOGGLE.attractors()
    sizes = _TOGGLE.basin_sizes()
    basin_of = {
        frozenset(tuple(sorted(s.items())) for s in cycle): size
        for cycle, size in zip(attractors, sizes)
    }
    assert basin_of[frozenset({(("A", 0), ("B", 1))})] == 1  # fixed point 01
    assert basin_of[frozenset({(("A", 1), ("B", 0))})] == 1  # fixed point 10
    assert basin_of[
        frozenset({(("A", 0), ("B", 0)), (("A", 1), ("B", 1))})
    ] == 2  # the 00<->11 two-cycle
    assert sum(sizes) == 4


def test_asynchronous_updating_drops_the_synchronous_two_cycle() -> None:
    # The toggle's (0,0)<->(1,1) 2-cycle exists only under synchronous updating; asynchronously,
    # (0,0) and (1,1) are transient and only the two fixed points remain. Fixed points are
    # scheme-invariant, so this is the sharpest demonstration that the scheme is load-bearing.
    sync = _TOGGLE.attractors(UpdateScheme.SYNCHRONOUS)
    async_ = _TOGGLE.attractors(UpdateScheme.ASYNCHRONOUS)
    assert sorted(len(c) for c in sync) == [1, 1, 2]
    assert sorted(len(c) for c in async_) == [1, 1]  # the 2-cycle is gone
    async_states = {tuple(sorted(s.items())) for cycle in async_ for s in cycle}
    assert async_states == {(("A", 0), ("B", 1)), (("A", 1), ("B", 0))}  # the fixed points


def test_fixed_points_are_scheme_invariant() -> None:
    # Every synchronous fixed point is a single-state attractor under async too, and vice versa.
    sync_fps = {tuple(sorted(s.items())) for c in _TOGGLE.attractors(UpdateScheme.SYNCHRONOUS)
                for s in c if len(c) == 1}
    async_fps = {tuple(sorted(s.items())) for c in _TOGGLE.attractors(UpdateScheme.ASYNCHRONOUS)
                 for s in c if len(c) == 1}
    assert sync_fps == async_fps


def test_judge_attractor_set_under_the_asynchronous_scheme() -> None:
    # Reporting only the two fixed points reproduces under async (no 2-cycle), but fails under sync.
    reported = [[{"A": 1, "B": 0}], [{"A": 0, "B": 1}]]
    good = judge_attractor_set(
        claim_id="att", quantity="attractors", source_location="Table 1",
        reported=reported, network=_TOGGLE, scheme=UpdateScheme.ASYNCHRONOUS,
    )
    assert good.verdict is Verdict.REPRODUCED


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


def test_reproduces_thomas_rules_positive_and_negative_feedback_circuits() -> None:
    # Thomas' rules, the foundational theorems of logical modeling: a *positive* feedback circuit
    # (even number of negative interactions) is necessary for multistationarity, and a *negative*
    # circuit (odd number) is necessary for sustained oscillation. Reproduced here on the two
    # canonical minimal circuits. Non-circular: the ground truth is Thomas' theorems, not this engine.

    # Positive circuit — the toggle switch (double-negative loop, two negatives → positive): it must
    # be MULTISTATIONARY (two stable steady states) and must NOT oscillate.
    positive = parse_boolean_network({"A": "not B", "B": "not A"})
    assert positive.fixed_points() == [{"A": 0, "B": 1}, {"A": 1, "B": 0}]  # bistable
    async_positive = positive.attractors(UpdateScheme.ASYNCHRONOUS)
    assert all(len(attractor) == 1 for attractor in async_positive)  # every attractor is a point
    assert len(async_positive) == 2  # exactly the two steady states — no cyclic attractor

    # Negative circuit — the 3-node repressilator (three repressions, odd → negative): it must have
    # NO steady state and must OSCILLATE (a single cyclic attractor).
    negative = parse_boolean_network({"A": "not C", "B": "not A", "C": "not B"})
    assert negative.fixed_points() == []  # a negative circuit admits no fixed point
    async_negative = negative.attractors(UpdateScheme.ASYNCHRONOUS)
    assert len(async_negative) == 1
    assert len(async_negative[0]) > 1  # a genuine cycle: sustained oscillation, not a steady state


def test_synchronous_update_creates_a_spurious_cycle_that_async_resolves() -> None:
    # The canonical caveat of Boolean modeling and the reason both update schemes exist: the
    # *synchronous* scheme (every node updates at once) can manufacture a spurious limit cycle where
    # the biology has none, because it forbids the intermediate states an asynchronous update passes
    # through. The toggle switch is the textbook case — synchronous dynamics add a (0,0)↔(1,1)
    # 2-cycle on top of the two real steady states, which asynchronous dynamics correctly omit.
    toggle = parse_boolean_network({"A": "not B", "B": "not A"})

    fixed = [{"A": 0, "B": 1}, {"A": 1, "B": 0}]
    sync = toggle.attractors(UpdateScheme.SYNCHRONOUS)
    async_ = toggle.attractors(UpdateScheme.ASYNCHRONOUS)

    # Both schemes agree on the two genuine steady states.
    assert [a[0] for a in sync if len(a) == 1] == fixed
    assert [a[0] for a in async_ if len(a) == 1] == fixed

    # Synchronous update alone carries a spurious cyclic attractor; asynchronous has none.
    sync_cycles = [a for a in sync if len(a) > 1]
    assert sync_cycles == [({"A": 0, "B": 0}, {"A": 1, "B": 1})]
    assert [a for a in async_ if len(a) > 1] == []


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


# --- certificate integration (shared contracts carry the class) --------------------


def test_certify_logical_builds_a_certificate_through_the_shared_builder() -> None:
    from reprolith import (
        EnginePin,
        LogicalClaim,
        OverallVerdict,
        PaperIdentity,
        certify_logical,
    )

    cert = certify_logical(
        paper=PaperIdentity(title="A Boolean signaling model", doi="10.9/log"),
        engine_pin=EnginePin(engine="reprolith-logical", version="0.0.1"),
        claims=[
            LogicalClaim(
                claim_id="ss1", quantity="ON steady state", rules={"A": "!B", "B": "!A"},
                reported={"A": 1, "B": 0}, source_location="Fig 2",
            ),
            LogicalClaim(
                claim_id="ss2", quantity="OFF steady state", rules={"A": "!B", "B": "!A"},
                reported={"A": 0, "B": 1}, source_location="Fig 2",
            ),
        ],
    )
    assert cert.overall is OverallVerdict.REPRODUCED  # both reported states are fixed points
    assert {a.method for a in cert.assessments} == {"attractor-set-match"}
    assert cert.scope.machine  # the scope flag travels with a logical certificate too


def test_certify_logical_emits_an_honest_not_reproduced_certificate() -> None:
    from reprolith import EnginePin, LogicalClaim, OverallVerdict, PaperIdentity, certify_logical

    cert = certify_logical(
        paper=PaperIdentity(title="A Boolean signaling model", doi="10.9/log"),
        engine_pin=EnginePin(engine="reprolith-logical", version="0.0.1"),
        claims=[
            LogicalClaim(
                claim_id="bad", quantity="claimed steady state", rules={"A": "!B", "B": "!A"},
                reported={"A": 1, "B": 1}, source_location="Fig 2",  # not a fixed point
                shortfall=Attribution(
                    mode=FailureMode.UNSPECIFIED_UPDATE_SCHEME, implicated="update scheme",
                    fault=Fault.MANUSCRIPT,
                ),
            ),
        ],
    )
    assert cert.overall is OverallVerdict.NOT_REPRODUCED


# --- dossier shape (spec: Logical dossier shape) -----------------------------------


def test_logical_dossier_records_nodes_rules_and_scheme() -> None:
    from reprolith import DossierClaim, logical_dossier

    dossier = logical_dossier(
        "toggle", rules={"A": "!B", "B": "!A"}, source_location="Fig 1",
        update_scheme=UpdateScheme.SYNCHRONOUS,
        claims=[DossierClaim(id="ss", quantity="ON steady state", conditions="", source_location="Fig 1")],
    )
    assert dossier.state_variables == ("A", "B")
    assert {e.target for e in dossier.equations} == {"A", "B"}
    assert dossier.gaps == ()  # the scheme is stated, so no gap
    assert dossier.targetable_claims()[0].id == "ss"


def test_unstated_update_scheme_is_a_load_bearing_gap() -> None:
    from reprolith import GapKind, logical_dossier

    dossier = logical_dossier(
        "toggle", rules={"A": "!B", "B": "!A"}, source_location="Fig 1", update_scheme=None
    )
    assert len(dossier.load_bearing_gaps()) == 1
    assert dossier.load_bearing_gaps()[0].kind is GapKind.UPDATE_SCHEME


def test_logical_dossier_rejects_a_rule_referencing_an_unknown_node() -> None:
    from reprolith import logical_dossier

    with pytest.raises(ValueError, match="unknown node"):
        logical_dossier("bad", rules={"A": "!Z"}, source_location="Fig 1",
                        update_scheme=UpdateScheme.SYNCHRONOUS)


def test_certify_logical_accepts_a_generator_of_claims() -> None:
    """The claims are iterated twice; a generator used to be exhausted by the first pass.

    The second pass attaches the search protocol, so it silently emptied the assessment list and
    published an earned `not-reproduced` as a blocked certificate that had evaluated nothing.
    """
    from reprolith import EnginePin, OverallVerdict, PaperIdentity
    from reprolith.logical import LogicalClaim, certify_logical

    claims = [
        LogicalClaim(claim_id="ss", quantity="steady state", rules={"A": "!B", "B": "!A"},
                     reported={"A": 1, "B": 1}, source_location="Fig 1"),
    ]
    pin = EnginePin(engine="reprolith-logical", version="0.0.1", algorithm="synchronous-update")
    paper = PaperIdentity(title="toggle", doi="10.0/t")
    from_list = certify_logical(paper=paper, engine_pin=pin, claims=claims)
    from_generator = certify_logical(paper=paper, engine_pin=pin, claims=iter(claims))
    assert from_generator.overall is from_list.overall is OverallVerdict.NOT_REPRODUCED
    assert len(from_generator.assessments) == len(from_list.assessments) == 1
