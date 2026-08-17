"""The verification queue: load-bearing uncertainty, impact-ordered, expert decisions."""

from __future__ import annotations

import pytest
from reprolith import VerificationDecision, VerificationItem, VerificationQueue


def _item(item_id, *, depends_on=("c1",), margin=None):
    return VerificationItem(
        id=item_id,
        question=f"is {item_id} right?",
        best_estimate="1.2",
        basis="typical value",
        depends_on=depends_on,
        alternatives=("0.9", "1.5"),
        margin=margin,
    )


def test_item_is_self_contained() -> None:
    view = _item("a", depends_on=("c1", "c2")).to_dict()
    # An outside expert sees the question, estimate, basis, alternatives, and stakes.
    assert view["question"] and view["best_estimate"] and view["basis"]
    assert view["alternatives"] == ["0.9", "1.5"]
    assert view["impact"] == 2  # how many depend on it


def test_pending_is_impact_ordered_then_margin() -> None:
    queue = VerificationQueue()
    queue.add(_item("low", depends_on=("c1",)))
    queue.add(_item("high", depends_on=("c1", "c2", "c3")))
    queue.add(_item("near", depends_on=("c1",), margin=0.01))
    queue.add(_item("far", depends_on=("c1",), margin=0.5))
    order = [i.id for i in queue.pending()]
    # Most dependents first; among equal dependents, the nearer-the-margin verdict first.
    assert order[0] == "high"
    assert order.index("near") < order.index("far")


def test_decisions_are_recorded_attributed_and_deciding_resolves_pending() -> None:
    queue = VerificationQueue()
    queue.add(_item("a"))
    assert [i.id for i in queue.pending()] == ["a"]
    queue.decide("a", VerificationDecision(kind="confirm", expert="curator@lab", rationale="matches Table 1"))
    # Decided items leave the pending list; the decision is attributed and retrievable.
    assert queue.pending() == []
    decisions = queue.decisions_for("a")
    assert len(decisions) == 1 and decisions[0].expert == "curator@lab"
    # The original estimate remains retrievable.
    assert queue.get("a").best_estimate == "1.2"


def test_disagreement_is_preserved_not_overwritten() -> None:
    queue = VerificationQueue()
    queue.add(_item("a"))
    queue.decide("a", VerificationDecision(kind="correct", expert="e1", rationale="should be 1.5",
                                           corrected_value="1.5"))
    queue.decide("a", VerificationDecision(kind="reject", expert="e2", rationale="not reproducible"))
    kinds = [d.kind for d in queue.decisions_for("a")]
    assert kinds == ["correct", "reject"]  # both retained, not resolved to one


def test_decision_validation() -> None:
    queue = VerificationQueue()
    queue.add(_item("a"))
    with pytest.raises(KeyError):
        queue.decide("missing", VerificationDecision(kind="confirm", expert="e", rationale="r"))
    with pytest.raises(ValueError):
        queue.decide("a", VerificationDecision(kind="bogus", expert="e", rationale="r"))
    with pytest.raises(ValueError):  # a correction must supply the value
        queue.decide("a", VerificationDecision(kind="correct", expert="e", rationale="r"))
    with pytest.raises(ValueError):  # a decision must record a rationale
        queue.decide("a", VerificationDecision(kind="confirm", expert="e", rationale="  "))


def test_correction_reverifies_dependents_and_supersedes() -> None:
    from reprolith import (
        Assumption,
        CertificateLedger,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        reverify_dependents,
    )

    pin = EnginePin(engine="copasi", version="4.46")

    def _cert(qualified, verification_item):
        return build_certificate(
            paper=PaperIdentity(title="t"), engine_pin=pin,
            assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.REPRODUCED,
                                         source_location="T1", assumption_qualified=qualified)],
            assumptions=[Assumption(id="k", description="ka", chosen="1.2", basis="b",
                                    load_bearing=True, verification_item=verification_item)],
        )

    ledger = CertificateLedger()
    # A certificate resting on an unverified queued value.
    original = _cert(qualified=True, verification_item="VQ-1")
    original_digest = ledger.issue(original)

    item = VerificationItem(id="VQ-1", question="is ka=1.2?", best_estimate="1.2", basis="b",
                            depends_on=(original_digest,))
    queue = VerificationQueue()
    queue.add(item)
    queue.decide("VQ-1", VerificationDecision(kind="confirm", expert="e", rationale="confirmed 1.2"))

    # On confirmation, re-issue the dependent with its unverified qualification lifted, linked
    # to the one it supersedes.
    def recertify(old):
        return build_certificate(
            paper=old.paper, engine_pin=old.engine_pin, assessments=old.assessments,
            assumptions=[Assumption(id="k", description="ka", chosen="1.2", basis="b",
                                    load_bearing=True, verification_item=None)],  # qualification lifted
            supersedes=old,
        )

    replacements = reverify_dependents(item, ledger, queue=queue, recertify=recertify)
    assert len(replacements) == 1
    new = replacements[0]
    assert new.supersedes == original_digest  # links to what it supersedes
    assert new.assumptions[0].verification_item is None  # qualification lifted
    # The superseded certificate remains retrievable.
    assert ledger.get(original_digest) is original
    assert len(ledger) == 2


def test_pin_change_flags_certificates_for_review() -> None:
    from reprolith import (
        CertificateLedger,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        certificates_needing_review,
    )

    def _cert(version):
        return build_certificate(
            paper=PaperIdentity(title=f"m{version}"), engine_pin=EnginePin(engine="copasi", version=version),
            assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.REPRODUCED,
                                         source_location="T1")],
        )

    ledger = CertificateLedger()
    ledger.issue(_cert("4.46"))
    ledger.issue(_cert("4.47"))
    # After the pin advances to 4.47, only the 4.46 certificate is stale and needs re-review.
    stale = certificates_needing_review(ledger, EnginePin(engine="copasi", version="4.47"))
    assert [c.engine_pin.version for c in stale] == ["4.46"]


def test_a_decided_item_cannot_be_quietly_replaced() -> None:
    """Otherwise an expert's decision ends up attached to a question they never saw."""
    import pytest

    queue = VerificationQueue()
    item = VerificationItem(
        id="v1", question="is the dose the salt form?", best_estimate="free base",
        basis="the model's input is free base", depends_on=("c1",),
    )
    queue.add(item)
    queue.decide("v1", VerificationDecision(kind="confirm", expert="a reviewer", rationale="agreed"))
    queue.add(item)  # re-adding the same question is a no-op, not a problem

    changed = VerificationItem(
        id="v1", question="is the dose per kg?", best_estimate="total",
        basis="the table header", depends_on=("c1",),
    )
    with pytest.raises(ValueError, match="already carries an expert decision"):
        queue.add(changed)


def test_a_pending_item_cannot_lift_its_dependents_qualification() -> None:
    """Otherwise the unverified value becomes a clean green certificate with nobody having ruled."""
    from reprolith import (
        Assumption,
        CertificateLedger,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        reverify_dependents,
    )

    original = build_certificate(
        paper=PaperIdentity(title="t"), engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c", quantity="AUC", verdict=Verdict.REPRODUCED,
                                     source_location="T1")],
        assumptions=[Assumption(id="k", description="ka", chosen="1.2", basis="b",
                                load_bearing=False, verification_item="VQ-9")],
    )
    ledger = CertificateLedger()
    digest = ledger.issue(original)
    assert original.overall.value == "partially-reproduced"  # withheld, pending review

    queue = VerificationQueue()
    item = VerificationItem(id="VQ-9", question="is ka=1.2?", best_estimate="1.2", basis="b",
                            depends_on=(digest,))
    queue.add(item)

    def recertify(old):  # pragma: no cover - must never be reached
        raise AssertionError("re-certified while the item was still pending")

    with pytest.raises(ValueError, match="no expert decision yet"):
        reverify_dependents(item, ledger, queue=queue, recertify=recertify)

    # A rejection is not a confirmation either.
    queue.decide("VQ-9", VerificationDecision(kind="reject", expert="e", rationale="not supported"))
    with pytest.raises(ValueError, match="rejected"):
        reverify_dependents(item, ledger, queue=queue, recertify=recertify)


def test_a_downgrade_that_is_pending_review_says_so_in_the_gap_report() -> None:
    """The report whose job is to explain a withheld pass cannot be silent about the reason."""
    from reprolith import (
        Assumption,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
    )
    from reprolith.render import gap_items

    cert = build_certificate(
        paper=PaperIdentity(title="t"), engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(claim_id="c", quantity="peak", verdict=Verdict.REPRODUCED,
                                     source_location="Fig 1")],
        assumptions=[Assumption(id="k", description="dose not stated", chosen="10 mg", basis="typical",
                                load_bearing=False, verification_item="VQ-7")],
    )
    assert cert.overall.value == "partially-reproduced"
    needs = [item["needs"] for item in gap_items(cert)]
    assert any("VQ-7" in n and "dose not stated" in n for n in needs)
