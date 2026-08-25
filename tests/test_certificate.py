"""The overall-verdict rule and the honesty invariants it enforces."""

from __future__ import annotations

from dataclasses import replace

import pytest
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


def _claim(
    verdict: Verdict, *, qualified: bool = False, cid: str = "c", root_cause: str | None = None
) -> ClaimAssessment:
    # A partial or failed verdict names a cause: the builder refuses one that does not, the same
    # way the judges always have.
    if root_cause is None and verdict in (Verdict.PARTIAL, Verdict.FAILED):
        root_cause = "uncategorized"
    return ClaimAssessment(
        claim_id=cid,
        quantity="q",
        verdict=verdict,
        source_location="loc",
        assumption_qualified=qualified,
        root_cause=root_cause,
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


def test_a_supplied_number_verdict_without_its_protocol_is_refused_at_the_builder() -> None:
    """The invariant lives where the other honesty rules live, not only on the claim types.

    `EstimationClaim` and `PopulationClaim` refuse a blank protocol, but the judges and the builder
    are public, so a caller can assemble the same certificate from assessments directly and publish
    a clean estimation pass for `recovered == reported` with nothing behind it.
    """
    from reprolith import judge_estimation

    bare = judge_estimation(
        claim_id="cl", quantity="CL/F estimate", source_location="Table 3",
        reported=3.2, recovered=3.2,
    )
    with pytest.raises(ValueError, match="protocol"):
        build_certificate(
            paper=PaperIdentity(title="A data-shipping paper", doi="10.0/e"),
            engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
            assessments=[bare],
        )

    stated = replace(bare, protocol="maximum likelihood, Nelder-Mead, shipped dataset")
    cert = build_certificate(
        paper=PaperIdentity(title="A data-shipping paper", doi="10.0/e"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        assessments=[stated],
    )
    assert cert.assessments[0].protocol is not None


def test_two_assumptions_under_one_id_are_refused() -> None:
    """An assumption a verdict rests on has to be identifiable to be readable."""
    same_id = [
        Assumption(id="sampling", description="d", chosen="500 subjects", basis="b",
                   load_bearing=True),
        Assumption(id="sampling", description="d", chosen="20 subjects", basis="b",
                   load_bearing=False),
    ]
    with pytest.raises(ValueError, match="appears twice"):
        build_certificate(
            paper=PaperIdentity(title="P", doi="10.0/a"),
            engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
            assessments=[],
            assumptions=same_id,
        )


def test_an_assumption_cannot_be_attributed_to_the_paper() -> None:
    """`attributed_to` was free text with a default, so the invariant was carried by a docstring.

    An assumption exists *because* the paper did not supply the value. The human certificate prints
    them under "supplied by Reprolith, not the paper" while the machine form carries the field
    verbatim, so a certificate naming the paper as the source of Reprolith's own guess states two
    contradictory things about one number and an agent reads only the false half. Checked on the
    load path too, because the registry reads certificates off disk and never rebuilds them.
    """
    from reprolith import Assumption, EnginePin, PaperIdentity, build_certificate
    from reprolith.persistence import certificate_from_content

    borrowed = Assumption(
        id="V1", description="central volume of distribution", chosen="12.3 L",
        basis="inferred from the reported AUC", load_bearing=True,
        attributed_to="Zake et al. 2021, Table 2",
    )
    pin = EnginePin(engine="copasi", version="4.46")
    paper = PaperIdentity(title="t", doi="10.1/x")
    with pytest.raises(ValueError, match="can only be attributed to"):
        build_certificate(paper=paper, engine_pin=pin, assessments=[], assumptions=[borrowed])

    honest = build_certificate(
        paper=paper, engine_pin=pin, assessments=[],
        assumptions=[Assumption(id="V1", description="central volume", chosen="12.3 L",
                                basis="AUC", load_bearing=True)],
    )
    content = honest.content()
    content["assumptions"][0]["attributed_to"] = "Zake et al. 2021, Table 2"
    with pytest.raises(ValueError, match="can only be attributed to"):
        certificate_from_content(content)


def test_two_claims_under_one_id_are_refused_on_both_paths() -> None:
    """A claim a verdict is published against has to be identifiable — and one was not.

    The gap report resolves an estimation claim by looking its id up among the assessments, so
    two claims sharing an id published the first one's row twice and dropped the second's
    shortfall: a "what was missing" report missing one of the things that was missing.
    """
    from reprolith import ReproductionLevel, Verdict
    from reprolith.certificate import require_distinct_claim_ids
    from reprolith.persistence import certificate_from_content

    def assessment(quantity: str, verdict: Verdict) -> ClaimAssessment:
        return ClaimAssessment(
            claim_id="cl", quantity=quantity, verdict=verdict, source_location="Table 3",
            discrepancy=None, root_cause="the re-fit did not recover the estimate",
            level=ReproductionLevel.ESTIMATION, protocol="maximum likelihood, shipped dataset",
        )

    duplicated = [assessment("CL/F", Verdict.REPRODUCED), assessment("V/F", Verdict.FAILED)]
    with pytest.raises(ValueError, match="claim id 'cl' appears twice"):
        build_certificate(
            paper=PaperIdentity(title="P", doi="10.0/dup"),
            engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
            assessments=duplicated,
        )
    require_distinct_claim_ids([assessment("CL/F", Verdict.REPRODUCED)])  # one id, no complaint

    # And a hand-edited file cannot smuggle the same shape back in through the load path.
    good = build_certificate(
        paper=PaperIdentity(title="P", doi="10.0/dup"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        assessments=[assessment("CL/F", Verdict.REPRODUCED)],
    )
    content = good.content()
    content["assessments"].append(dict(content["assessments"][0], quantity="V/F"))
    with pytest.raises(ValueError, match="appears twice"):
        certificate_from_content(content)
