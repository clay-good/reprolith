"""The update scheme reaches the run, and is qualified only where it could change the answer.

Two halves of one feature had been apart since this class was written. The dossier records an
unstated update scheme as a **load-bearing gap** — the way in — and `certify_logical` had no way
to carry a *stated* one through to the run, no way to certify the attractor sets where the scheme
actually matters, and no assumption on the way out. `judge_attractor_set` had been the class's
answer to a reported attractor set the whole time, reachable from tests alone; the milestone script
re-implemented the comparison rather than calling it.

The qualification is measured rather than asserted, and the measurement here is **exact**:
attractors are enumerated, so "the two schemes agree" is a proof. The rule that matters is that it
compares what the claim was judged *on* — see the fixed-point test below, which is the defect this
file was written after finding.
"""

from __future__ import annotations

import pytest
from reprolith import (
    LogicalClaim,
    PaperIdentity,
    UpdateScheme,
    certify_logical,
)
from reprolith.enums import OverallVerdict, Verdict
from reprolith.logical import scheme_sensitivity, solver_pin

# The toggle switch: two mutually repressing nodes. Its two fixed points are the biology; its
# (0,0)<->(1,1) 2-cycle is an artifact of updating both nodes at once, and it does not survive
# asynchronous updating. So this network's attractor set is scheme-dependent and its fixed-point
# set is not — which is exactly the distinction the qualification has to make.
TOGGLE = {"A": "!B", "B": "!A"}
SYNC_ATTRACTORS = [[{"A": 0, "B": 1}], [{"A": 1, "B": 0}], [{"A": 0, "B": 0}, {"A": 1, "B": 1}]]
ASYNC_ATTRACTORS = [[{"A": 0, "B": 1}], [{"A": 1, "B": 0}]]


def _claim(**kw) -> LogicalClaim:
    base = dict(
        claim_id="toggle",
        quantity="attractor set",
        rules=TOGGLE,
        reported={},
        source_location="Fig 2",
        attractors=SYNC_ATTRACTORS,
    )
    base.update(kw)
    return LogicalClaim(**base)


def _certificate(claim: LogicalClaim, scheme: UpdateScheme = UpdateScheme.SYNCHRONOUS):
    return certify_logical(
        paper=PaperIdentity(title="a toggle switch"),
        engine_pin=solver_pin(scheme=scheme),
        claims=[claim],
    )


# --- the attractor set can be certified at all --------------------------------------------------


def test_a_reported_attractor_set_is_certified_through_the_front_end() -> None:
    """`judge_attractor_set` was reachable from tests and from nothing else."""
    certificate = _certificate(_claim())
    (assessment,) = certificate.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    assert "3 attractor(s), all reported" in assessment.discrepancy


def test_the_scheme_a_source_states_reaches_the_run() -> None:
    """Under asynchronous updating the synchronous 2-cycle is gone, so the same network judged
    against the asynchronous set reproduces and against the synchronous set does not."""
    claim = _claim(scheme=UpdateScheme.ASYNCHRONOUS, attractors=ASYNC_ATTRACTORS)
    (assessment,) = _certificate(claim, UpdateScheme.ASYNCHRONOUS).assessments
    assert assessment.verdict is Verdict.REPRODUCED

    mismatched = _claim(scheme=UpdateScheme.ASYNCHRONOUS, attractors=SYNC_ATTRACTORS)
    (assessment,) = _certificate(mismatched, UpdateScheme.ASYNCHRONOUS).assessments
    assert assessment.verdict is not Verdict.REPRODUCED
    assert "1 reported attractor(s) not found" in assessment.discrepancy


# --- the qualification, and where it does not belong --------------------------------------------


def test_an_unstated_scheme_that_could_change_the_answer_is_load_bearing_with_the_difference() -> None:
    certificate = _certificate(_claim())
    (assumption,) = certificate.assumptions
    assert assumption.id == "logical-scheme-toggle"
    assert assumption.load_bearing
    # An author *can* close this one — a paper can state its scheme — unlike the spatial wall,
    # which is a limit of the solver. The queue ranks the two differently for that reason.
    assert assumption.author_can_close is True
    assert "3 attractor(s) under synchronous" in assumption.basis
    assert "2 under asynchronous" in assumption.basis
    assert "1 that exist only under the one judged" in assumption.basis
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED


def test_a_fixed_point_claim_is_never_qualified_for_the_scheme() -> None:
    """The defect this file was written after finding. A fixed point is one under either scheme —
    a state whose synchronous successor is itself has no unstable node to flip — so a steady-state
    verdict cannot move with the choice. Comparing attractor *sets* here reported this very
    network's spurious 2-cycle as grounds to qualify it, which is measuring the wrong quantity and
    would have downgraded every fixed-point certificate this class publishes."""
    steady = _claim(attractors=None, quantity="steady state", reported={"A": 1, "B": 0})
    certificate = _certificate(steady)
    assert certificate.assessments[0].verdict is Verdict.REPRODUCED
    assert certificate.assumptions == ()
    assert certificate.overall is OverallVerdict.REPRODUCED
    sensitivity = scheme_sensitivity(steady)
    assert sensitivity["agree"] is True
    assert "no run is needed" in sensitivity["why"]


def test_a_stated_scheme_rests_on_nothing_this_engine_chose() -> None:
    claim = _claim(scheme=UpdateScheme.ASYNCHRONOUS, attractors=ASYNC_ATTRACTORS)
    certificate = _certificate(claim, UpdateScheme.ASYNCHRONOUS)
    assert certificate.assumptions == ()
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert scheme_sensitivity(claim) is None


def test_a_network_whose_schemes_agree_is_not_qualified_either() -> None:
    """Not every network is scheme-dependent: one whose attractors are all fixed points gives the
    same set either way, and that is a proof rather than a hope — so qualifying it would downgrade
    a verdict the choice cannot touch."""
    cascade = _claim(
        rules={"A": "A", "B": "A"},
        attractors=[[{"A": 0, "B": 0}], [{"A": 1, "B": 1}]],
    )
    assert scheme_sensitivity(cascade)["agree"] is True
    assert _certificate(cascade).assumptions == ()


# --- the pin cannot disagree with what ran ------------------------------------------------------


def test_a_pin_naming_the_other_scheme_is_refused() -> None:
    """The sibling of the path check: `solver_pin` takes a scheme from the caller and nothing made
    it agree with what was computed, so a certificate could announce asynchronous updating over a
    synchronous enumeration — two accounts of one number with the stronger one false."""
    claim = _claim(scheme=UpdateScheme.ASYNCHRONOUS, attractors=ASYNC_ATTRACTORS)
    with pytest.raises(ValueError, match="judged under asynchronous updating and the pin says"):
        _certificate(claim, UpdateScheme.SYNCHRONOUS)


def test_claims_judged_under_two_schemes_cannot_share_one_pin() -> None:
    with pytest.raises(ValueError, match="one pin cannot name both"):
        certify_logical(
            paper=PaperIdentity(title="two schemes"),
            engine_pin=solver_pin(),
            claims=[
                _claim(claim_id="sync"),
                _claim(claim_id="async", scheme=UpdateScheme.ASYNCHRONOUS,
                       attractors=ASYNC_ATTRACTORS),
            ],
        )
