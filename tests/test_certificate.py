"""The overall-verdict rule and the honesty invariants it enforces."""

from __future__ import annotations

from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    build_certificate,
    derive_overall,
)


def _claim(verdict: Verdict, *, qualified: bool = False, cid: str = "c") -> ClaimAssessment:
    return ClaimAssessment(
        claim_id=cid,
        quantity="q",
        verdict=verdict,
        source_location="loc",
        assumption_qualified=qualified,
    )


def test_all_reproduced_is_reproduced() -> None:
    assert derive_overall([_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.REPRODUCED, cid="b")]) is (
        OverallVerdict.REPRODUCED
    )


def test_assumption_qualified_cannot_be_clean_reproduced() -> None:
    # Every claim reproduced, but one rests on a load-bearing assumption:
    # the certificate refuses to call this a clean pass.
    assessments = [
        _claim(Verdict.REPRODUCED, cid="a"),
        _claim(Verdict.REPRODUCED, cid="b", qualified=True),
    ]
    assert derive_overall(assessments) is OverallVerdict.PARTIALLY_REPRODUCED


def test_mixed_is_partial() -> None:
    assessments = [_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.FAILED, cid="b")]
    assert derive_overall(assessments) is OverallVerdict.PARTIALLY_REPRODUCED


def test_none_reproduced_is_not_reproduced() -> None:
    assessments = [_claim(Verdict.FAILED, cid="a"), _claim(Verdict.PARTIAL, cid="b")]
    assert derive_overall(assessments) is OverallVerdict.NOT_REPRODUCED


def test_nothing_evaluable_is_blocked() -> None:
    assert derive_overall([]) is OverallVerdict.BLOCKED
    assert derive_overall([_claim(Verdict.NOT_EVALUABLE, cid="a")]) is OverallVerdict.BLOCKED


def test_not_evaluable_claims_are_excluded_not_counted_against() -> None:
    # One reproduced, one not-evaluable: the not-evaluable claim is set aside, so the
    # evaluable set is fully reproduced.
    assessments = [_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.NOT_EVALUABLE, cid="b")]
    assert derive_overall(assessments) is OverallVerdict.REPRODUCED


def test_build_certificate_derives_overall() -> None:
    cert = build_certificate(
        paper=PaperIdentity(title="t"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[_claim(Verdict.REPRODUCED, cid="a", qualified=True)],
        assumptions=[
            Assumption(
                id="k1",
                description="assumed initial condition",
                chosen="0",
                basis="unstated in paper; steady-state assumed",
                load_bearing=True,
            )
        ],
    )
    # A caller cannot pass in a clean 'reproduced' — the rule downgrades it.
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
