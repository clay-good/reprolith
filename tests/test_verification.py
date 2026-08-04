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
