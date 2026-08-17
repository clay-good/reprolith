"""The overall-verdict rule and the honesty invariants it enforces."""

from __future__ import annotations

from dataclasses import replace

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


def _asm(load_bearing: bool) -> Assumption:
    return Assumption(
        id="a1",
        description="unstated growth medium",
        chosen="default bounds",
        basis="not stated in the paper",
        load_bearing=load_bearing,
    )


def test_load_bearing_assumption_alone_forbids_a_clean_pass() -> None:
    # Every claim reproduced and NONE assumption-qualified, but a load-bearing assumption
    # sits on the record. The downgrade must fire on the assumption's own flag — otherwise a
    # caller could slip an unstated guess past the clean pass by handing it to the builder
    # while leaving the claims unqualified.
    assessments = [_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.REPRODUCED, cid="b")]
    assert derive_overall(assessments) is OverallVerdict.REPRODUCED
    assert derive_overall(assessments, [_asm(True)]) is OverallVerdict.PARTIALLY_REPRODUCED


def test_non_load_bearing_assumption_keeps_a_clean_pass() -> None:
    # A stated / non-load-bearing assumption does not taint an otherwise clean reproduction.
    assessments = [_claim(Verdict.REPRODUCED, cid="a")]
    assert derive_overall(assessments, [_asm(False)]) is OverallVerdict.REPRODUCED


def test_build_certificate_downgrades_on_load_bearing_assumption_only() -> None:
    # The escape closed at the builder: unqualified claims + a load-bearing assumption ->
    # partially-reproduced, which in turn makes the certificate not submission-ready.
    from reprolith.presubmission import presubmission_report

    cert = build_certificate(
        paper=PaperIdentity(title="t"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[_claim(Verdict.REPRODUCED, cid="a"), _claim(Verdict.REPRODUCED, cid="b")],
        assumptions=[_asm(True)],
    )
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert presubmission_report(cert)["ready_to_submit"] is False


def test_a_value_still_awaiting_expert_verification_withholds_a_clean_pass() -> None:
    """The verification-queue spec: a result resting on a queued value is reported as qualified."""
    queued = Assumption(
        id="a1", description="the dose's salt form", chosen="free base",
        basis="the model's dose input is free base", load_bearing=False,
        verification_item="VQ-1",
    )
    clean = ClaimAssessment(
        claim_id="c1", quantity="Cmax", verdict=Verdict.REPRODUCED, source_location="Table 1",
    )
    assert derive_overall([clean], [queued]) is OverallVerdict.PARTIALLY_REPRODUCED
    # The same assumption, already decided, does not withhold anything.
    assert derive_overall([clean], [replace(queued, verification_item=None)]) is OverallVerdict.REPRODUCED
