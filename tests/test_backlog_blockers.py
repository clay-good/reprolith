"""What the backlog is blocked *on*, not just how much of it is blocked.

`by_state` said 27 entries are blocked and stopped there. It could not say that all 27 are
blocked on one and the same missing input, which is the difference between twenty-seven problems
and one — and which is exactly the sentence the `autonomous-build-loop` spec asks an agent to be
able to write when it explains why it chose one unit of work over the alternatives.
"""

from __future__ import annotations

from reprolith import Catalog, Identifiers, LifecycleState, ModelClass
from reprolith.mcp_server import dispatch_tool, load_repository


def _blocked(catalog: Catalog, accession: str, *missing: str):
    entry = catalog.add(
        Identifiers(title=accession, accession=accession), ModelClass.ODE_PKPD
    )
    entry.transition(LifecycleState.INGESTING, at="t", actor="a", reason="r")
    entry.transition(
        LifecycleState.BLOCKED, at="t", actor="a", reason="r", missing_inputs=missing
    )
    return entry


def test_one_missing_input_behind_many_entries_is_reported_once_with_its_count() -> None:
    catalog = Catalog()
    for accession in ("A", "B", "C"):
        _blocked(catalog, accession, "no claims extracted")
    _blocked(catalog, "D", "the model file does not parse")
    blocked_on = catalog.backlog_health()["blocked_on"]
    assert [(b["entries"], b["missing"]) for b in blocked_on] == [
        (3, "no claims extracted"),
        (1, "the model file does not parse"),
    ]
    assert blocked_on[0]["accessions"] == ["A", "B", "C"]


def test_an_entry_blocked_on_two_things_counts_toward_both() -> None:
    """Both are true of it, and either one alone leaves it blocked."""
    catalog = Catalog()
    _blocked(catalog, "A", "no claims", "no model")
    counts = {b["missing"]: b["entries"] for b in catalog.backlog_health()["blocked_on"]}
    assert counts == {"no claims": 1, "no model": 1}


def test_only_the_move_that_put_it_in_its_current_state_counts() -> None:
    """An entry released and blocked again is waiting on the second reason, not on both.

    Counting every historical block would rank a capability by work it already unblocked once.
    """
    catalog = Catalog()
    entry = _blocked(catalog, "A", "the first reason")
    entry.transition(LifecycleState.QUEUED, at="t", actor="a", reason="released")
    entry.transition(LifecycleState.INGESTING, at="t", actor="a", reason="r")
    entry.transition(
        LifecycleState.BLOCKED, at="t", actor="a", reason="r", missing_inputs=("the second reason",)
    )
    assert [b["missing"] for b in catalog.backlog_health()["blocked_on"]] == ["the second reason"]


def test_an_unblocked_backlog_reports_nothing_blocking_it() -> None:
    catalog = Catalog()
    catalog.add(Identifiers(title="A", accession="A"), ModelClass.ODE_PKPD)
    assert catalog.backlog_health()["blocked_on"] == []


def test_the_committed_backlog_is_one_capability_deep() -> None:
    """Read off the shipped catalog: 0 claimable, 27 blocked, and all 27 on one missing input.

    The number in `Catalog.backlog_health`'s own docstring used to be written by hand here and had
    gone stale by three; this derives it, so the next entry that blocks on something else shows up
    as a second row rather than as a sentence nobody re-counted.
    """
    query, _ = load_repository("datasets/milestone", aggregate=True)
    health = query.backlog_health()
    assert health["claimable"] == 0
    blocked_on = health["blocked_on"]
    assert len(blocked_on) == 1, [b["missing"] for b in blocked_on]
    assert blocked_on[0]["entries"] == health["by_state"]["blocked"]
    assert "extracting a paper's targetable claims" in blocked_on[0]["missing"]


def test_the_agent_surface_answers_the_same() -> None:
    query, _ = load_repository("datasets/milestone", aggregate=True)
    assert dispatch_tool(query, "backlog_health", {})["blocked_on"] == (
        query.backlog_health()["blocked_on"]
    )
