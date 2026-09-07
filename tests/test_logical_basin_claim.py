"""A reported basin of attraction can be certified, and it knows which scheme it presupposes.

`BooleanNetwork.basin_sizes` has answered "how much of the state space reaches this attractor"
since the class was written, and it is checked against an independent count over ~1,800 random
networks in `test_logical_properties.py`. No claim could reach it. So the quantity Boolean-model
papers report when they argue a network is robust — Li et al. 2004's yeast cell-cycle network
reaches its G1 steady state from 1764 of 2048 initial states — was implemented and unreachable, the
same shape as `judge_attractor_set` and the Turing wavelength before it.

The ground truth at the bottom of this file is a **paper's own published numbers**, not a second
tool's: the committed CANA rules, restricted the way the paper's network is, reproduce all seven of
Li et al. 2004's basins exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    LogicalClaim,
    PaperIdentity,
    ReportedBasin,
    UpdateScheme,
    certify_logical,
    parse_boolean_network,
)
from reprolith.enums import OverallVerdict, Verdict
from reprolith.logical import judge_basin_size, scheme_sensitivity, solver_pin_for
from reprolith.oracle import ComparisonMethod, Tolerance, ToleranceSource

# A bistable switch: two self-activating nodes with mutual repression, plus a free node that does
# nothing but double the state space. Its two fixed points split the space evenly.
TOGGLE = {"A": "!B", "B": "!A"}
A_ON = [{"A": 1, "B": 0}]
B_ON = [{"A": 0, "B": 1}]
CYCLE = [{"A": 0, "B": 0}, {"A": 1, "B": 1}]


def _claim(basin: ReportedBasin, **kw) -> LogicalClaim:
    base = dict(
        claim_id="toggle-basin",
        quantity="fraction of initial states reaching the A-on steady state",
        rules=TOGGLE,
        reported={},
        source_location="Fig 2",
        basin=basin,
        scheme=UpdateScheme.SYNCHRONOUS,
    )
    base.update(kw)
    return LogicalClaim(**base)


def _certify(claim: LogicalClaim):
    return certify_logical(
        paper=PaperIdentity(title="a toggle switch"),
        engine_pin=solver_pin_for(nodes=len(claim.rules), scheme=claim.update_scheme),
        claims=[claim],
    )


# --- the count, judged exactly ------------------------------------------------------------------


def test_a_reported_state_count_reproduces() -> None:
    # The toggle's four states: each fixed point attracts only itself, and the 2-cycle holds the
    # other two. So the A-on basin is exactly one state.
    certificate = _certify(_claim(ReportedBasin(attractor=A_ON, states=1)))
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert certificate.assessments[0].verdict is Verdict.REPRODUCED
    assert certificate.assessments[0].method == ComparisonMethod.BASIN_SIZE_MATCH.value


def test_a_count_is_judged_exactly_not_in_a_band() -> None:
    # One state out of four is a 25% error, which a scalar tolerance would call a partial match.
    # A basin is a count of states in a finite space: 2 is not 1.
    certificate = _certify(_claim(ReportedBasin(attractor=CYCLE, states=1)))
    assert certificate.assessments[0].verdict is Verdict.FAILED
    assert "2 states flow to it against the reported 1" in certificate.assessments[0].discrepancy


def test_a_count_refuses_a_tolerance_rather_than_ignoring_it() -> None:
    with pytest.raises(ValueError, match="judged exactly"):
        ReportedBasin(
            attractor=A_ON,
            states=1,
            tolerance=Tolerance(0.1, 0.2, ToleranceSource.PAPER_STATED, "the paper states 10%"),
        )


# --- the fraction, judged in a band -------------------------------------------------------------


def test_a_reported_fraction_is_judged_by_relative_error() -> None:
    certificate = _certify(_claim(ReportedBasin(attractor=CYCLE, fraction=0.5)))
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert certificate.assessments[0].method == ComparisonMethod.SCALAR_RELATIVE_ERROR.value


def test_a_rounded_fraction_still_reproduces() -> None:
    # A paper prints 51%, the network gives exactly 50%: a 2% relative error, inside the scalar
    # default. This is why a fraction is not judged exactly and a count is.
    certificate = _certify(_claim(ReportedBasin(attractor=CYCLE, fraction=0.51)))
    assert certificate.assessments[0].verdict is Verdict.REPRODUCED


def test_a_reported_fraction_outside_zero_and_one_is_refused() -> None:
    with pytest.raises(ValueError, match="share of the state space"):
        ReportedBasin(attractor=A_ON, fraction=86.0)


def test_a_basin_of_no_states_is_refused_as_an_attractor_set_claim() -> None:
    # An attractor's own states are in its basin, so zero is not a small basin: it says the
    # attractor is not there, which is a claim about the attractor set. Judged here it would
    # compare a count against an attractor nothing identified.
    with pytest.raises(ValueError, match="attractor-set claim"):
        ReportedBasin(attractor=A_ON, states=0)
    with pytest.raises(ValueError, match="attractor-set claim"):
        ReportedBasin(attractor=A_ON, fraction=0.0)


# --- the state space the basin was counted in is on the record ----------------------------------


def test_the_protocol_records_the_denominator() -> None:
    # A paper that fixed its inputs before counting has a smaller space than the one enumerated
    # here, and two percentages taken of different wholes are not comparable. The size of this
    # network's space is on the line that says what the verdict rests on.
    certificate = _certify(_claim(ReportedBasin(attractor=A_ON, states=1)))
    protocol = certificate.assessments[0].protocol
    assert "basin of A: 1 of 2^2 = 4 states" in protocol
    # …and it is appended to the class's own protocol line, not written over it: the pin check on
    # the load path reads that line to see which path produced the number.
    assert "exhaustive enumeration of all 2^2 states" in protocol


# --- the ways it abstains, and the one way it does not ------------------------------------------


def test_an_attractor_this_network_does_not_have_fails_rather_than_abstaining() -> None:
    # The strongest non-reproduction this class can find: the paper's attractor is not there at
    # all. Abstaining would file it as "could not be judged".
    absent = [{"A": 1, "B": 1}]
    certificate = _certify(_claim(ReportedBasin(attractor=absent, states=4)))
    assert certificate.assessments[0].verdict is Verdict.FAILED
    assert "not one of this network's 3 synchronous attractors" in (
        certificate.assessments[0].discrepancy
    )


def test_an_asynchronous_claim_abstains_rather_than_answering_with_the_other_number() -> None:
    # Asynchronously a state has one successor per unstable node, so it can reach several
    # attractors and the basins overlap. The synchronous count exists; it answers a different
    # question, and publishing it here would answer a question the claim did not ask.
    certificate = _certify(_claim(ReportedBasin(attractor=A_ON, states=1),
                                  scheme=UpdateScheme.ASYNCHRONOUS))
    assessment = certificate.assessments[0]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "not defined" in assessment.root_cause


def test_a_network_past_the_ceiling_abstains() -> None:
    network = parse_boolean_network({f"n{i}": f"!n{(i + 1) % 25}" for i in range(25)})
    assessment = judge_basin_size(
        claim_id="big", quantity="basin", source_location="Fig 1",
        reported=ReportedBasin(attractor=[{f"n{i}": 0 for i in range(25)}], states=1),
        network=network,
    )
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "walking the whole state space" in assessment.root_cause


# --- what an unstated scheme costs a basin, measured --------------------------------------------


def test_an_unstated_scheme_is_not_waved_through_as_a_fixed_point() -> None:
    # The trap this branch exists for: a basin claim carries no attractor set, and the sibling
    # measurement reads "no attractor set, so it is judged on a fixed point, so the schemes agree".
    # A basin is neither.
    sensitivity = scheme_sensitivity(_claim(ReportedBasin(attractor=A_ON, states=1), scheme=None))
    assert sensitivity is not None
    assert "reachability" in (sensitivity.get("basis") or sensitivity.get("why") or "")


def test_an_unstated_scheme_that_changes_the_number_is_qualified_for() -> None:
    # Under asynchronous updating, both of the 2-cycle's states leave it and the whole space can
    # reach A-on; synchronously one state flows there. The reading moves the number, so the
    # certificate says the number rests on this engine's choice.
    certificate = _certify(_claim(ReportedBasin(attractor=A_ON, states=1), scheme=None))
    assert certificate.overall is not OverallVerdict.REPRODUCED
    assumption = certificate.assumptions[0]
    assert assumption.load_bearing and assumption.author_can_close
    assert "reachability" in assumption.basis


def test_a_stated_scheme_needs_no_assumption() -> None:
    certificate = _certify(_claim(ReportedBasin(attractor=A_ON, states=1)))
    assert certificate.assumptions == ()


def test_an_unstated_scheme_whose_two_readings_agree_earns_no_assumption() -> None:
    # A network with one attractor everything reaches under either reading: the choice provably
    # cannot move the number, so qualifying it would downgrade a verdict that cannot move.
    always = {"A": "1", "B": "1"}
    claim = _claim(
        ReportedBasin(attractor=[{"A": 1, "B": 1}], states=4), rules=always, scheme=None
    )
    assert scheme_sensitivity(claim)["agree"] is True
    assert _certify(claim).assumptions == ()


def test_an_absent_attractor_is_not_blamed_on_the_scheme_when_it_is_absent_either_way() -> None:
    # The claim has already failed on the attractor, not on the count. Minting a scheme assumption
    # here would say a verdict rests on a choice that cannot explain it — and the basis would read
    # "this run counted the 0 states whose trajectory ends in this attractor".
    claim = _claim(ReportedBasin(attractor=[{"A": 1, "B": 1}], states=4), scheme=None)
    assert scheme_sensitivity(claim)["agree"] is True
    certificate = _certify(claim)
    assert certificate.assessments[0].verdict is Verdict.FAILED
    assert certificate.assumptions == ()


def test_an_attractor_that_exists_only_asynchronously_is_blamed_on_the_scheme() -> None:
    # This network's synchronous attractor is a 2-cycle; asynchronously the four states around it
    # form one terminal set that no synchronous cycle equals. A claim reporting that set has failed
    # — but under no stated scheme the failure may be the reading rather than the network, and the
    # certificate says so instead of letting a scheme choice read as a mismatched model.
    rules = {"A": "!A", "B": "!A", "C": "A | C"}
    async_only = [
        {"A": 0, "B": 0, "C": 1}, {"A": 0, "B": 1, "C": 1},
        {"A": 1, "B": 0, "C": 1}, {"A": 1, "B": 1, "C": 1},
    ]
    claim = _claim(ReportedBasin(attractor=async_only, states=8), rules=rules, scheme=None)
    sensitivity = scheme_sensitivity(claim)
    assert sensitivity["agree"] is False
    assert "asynchronous updating" in sensitivity["basis"]


# --- one claim, one verdict ---------------------------------------------------------------------


def test_a_claim_reporting_both_a_basin_and_an_attractor_set_is_refused() -> None:
    with pytest.raises(ValueError, match="two claims about one network"):
        _claim(ReportedBasin(attractor=A_ON, states=1), attractors=[A_ON, B_ON, CYCLE])


# --- against a paper's own published basins -----------------------------------------------------

_REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "datasets" / "logical" / "cross_validation" / "reference.json"
)

#: Li et al. 2004, "The yeast cell-cycle network is robustly designed" (PNAS 101:4781), Table 1:
#: seven fixed points over eleven nodes, with these basins over the 2048-state space. The largest
#: — the G1 state — takes 1764 of them, which is the result that paper is remembered for.
LI_2004_BASINS = [1764, 151, 109, 9, 7, 7, 1]


def _li_2004_network() -> dict[str, str]:
    """The paper's 11-node network, from the committed CANA rules.

    CANA bundles a 12-node variant that adds `CellSize` as a free self-loop input; the paper's
    network is that one with the cell-size signal off, which leaves `Cln3` (its only target)
    constantly false. The restriction is *checked* below rather than assumed — a derived network
    nobody compares is a different model with a citation on it.
    """
    rules = dict(json.loads(_REFERENCE.read_text(encoding="utf-8"))["models"]["budding_yeast"]["rules"])
    del rules["CellSize"]
    rules["Cln3"] = "False"
    return rules


def test_the_restriction_to_eleven_nodes_is_the_twelve_node_network_with_cellsize_off() -> None:
    twelve = parse_boolean_network(
        json.loads(_REFERENCE.read_text(encoding="utf-8"))["models"]["budding_yeast"]["rules"]
    )
    eleven = parse_boolean_network(_li_2004_network())
    for state in eleven._states():
        theirs = dict(zip(eleven.nodes, state))
        mine = twelve.step({**theirs, "CellSize": 0})
        assert eleven.step(theirs) == {n: v for n, v in mine.items() if n != "CellSize"}


def test_reprolith_reproduces_li_2004s_published_basins() -> None:
    network = parse_boolean_network(_li_2004_network())
    assert sorted(network.basin_sizes(), reverse=True) == LI_2004_BASINS


def test_the_paper_s_headline_basin_certifies_as_reproduced() -> None:
    rules = _li_2004_network()
    network = parse_boolean_network(rules)
    g1 = max(zip(network.attractors(), network.basin_sizes()), key=lambda pair: pair[1])[0]
    assert [node for node, value in g1[0].items() if value] == ["Cdh1", "Sic1"]  # the G1 state
    claim = LogicalClaim(
        claim_id="li2004-g1-basin",
        quantity="states reaching the G1 steady state",
        rules=rules,
        reported={},
        source_location="Li et al. 2004 (PNAS 101:4781), Table 1",
        basin=ReportedBasin(attractor=list(g1), states=1764),
        # The paper updates every node at once, and says so — nothing is assumed here.
        scheme=UpdateScheme.SYNCHRONOUS,
    )
    certificate = certify_logical(
        paper=PaperIdentity(title="The yeast cell-cycle network is robustly designed"),
        engine_pin=solver_pin_for(nodes=11),
        claims=[claim],
    )
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert certificate.assumptions == ()
    assert "1764 of 2^11 = 2048 states" in certificate.assessments[0].protocol


def test_the_same_basin_is_the_same_count_and_a_different_fraction() -> None:
    # Why a count is the safer of the two to publish, in one network. `CellSize` is a self-loop, so
    # adding it doubles the state space without changing where anything flows: the G1 basin is 1764
    # states in both networks — and 86% of the paper's space against 43% of CANA's. A paper that
    # fixed an input before counting reports a fraction of a smaller whole, and a fraction compared
    # across two denominators is not a comparison. The protocol line carries the denominator for
    # exactly this reason.
    twelve = parse_boolean_network(
        json.loads(_REFERENCE.read_text(encoding="utf-8"))["models"]["budding_yeast"]["rules"]
    )
    assert 1764 in twelve.basin_sizes()
    assert 1764 / 2**12 == pytest.approx(0.4307, abs=1e-4)
    assert 1764 / 2**11 == pytest.approx(0.8613, abs=1e-4)
