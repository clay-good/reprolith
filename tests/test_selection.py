"""Choosing which claims to reproduce: a set-level objective against the greedy baseline.

Pure policy, no engine — these run in the core CI job.
"""

from __future__ import annotations

import random

import pytest
from reprolith import EvidenceItem, jaccard, score_set, select_greedily, select_jointly

# One paper's claims, and the machinery each one's verdict rests on. Figure 2's three panels are
# the paper's headline result and score highest on their own — and they are the same absorption /
# elimination / central-volume fit shown at three doses, so reproducing all three witnesses that
# fit three times and the rest of the model not at all. Figure 3 and Table 1 are individually
# worth less and rest on machinery nothing else touches.
_FIG2_A = EvidenceItem("fig2a", value=1.00, footprint=frozenset({"k_abs", "k_el", "V_central"}))
_FIG2_B = EvidenceItem("fig2b", value=0.95, footprint=frozenset({"k_abs", "k_el", "V_central"}))
_FIG2_C = EvidenceItem("fig2c", value=0.90, footprint=frozenset({"k_abs", "k_el", "V_central"}))
_FIG3 = EvidenceItem("fig3", value=0.60, footprint=frozenset({"Q_periph", "V_periph"}))
_TABLE1 = EvidenceItem("table1", value=0.55, footprint=frozenset({"dose_schedule", "infusion_t"}))
_PAPER = (_FIG2_A, _FIG2_B, _FIG2_C, _FIG3, _TABLE1)


def test_greedy_spends_the_whole_budget_on_near_duplicate_panels() -> None:
    # The baseline reads down a ranking, so the three highest-scoring claims win — and they are
    # three views of one fit. Three claims bought three of the paper's seven model components.
    greedy = select_greedily(_PAPER, budget=3)
    assert greedy.chosen == ("fig2a", "fig2b", "fig2c")
    assert greedy.covered == ("V_central", "k_abs", "k_el")


def test_the_greedy_baseline_ranks_by_value_per_cost_not_raw_value() -> None:
    # The baseline has to be the strong form of greedy, or the comparison this module rests on is
    # rigged: beating a baseline that ignores cost would prove nothing about set-level selection.
    pool = [
        EvidenceItem("one_big", value=3.0, footprint=frozenset({"p"}), cost=4.0),
        EvidenceItem("two_small_a", value=2.0, footprint=frozenset({"q"}), cost=2.0),
        EvidenceItem("two_small_b", value=1.9, footprint=frozenset({"r"}), cost=2.0),
    ]
    greedy = select_greedily(pool, budget=4.0)
    assert greedy.chosen == ("two_small_a", "two_small_b")
    assert greedy.score == pytest.approx(3.9)


def test_joint_selection_beats_greedy_when_the_top_claims_are_near_duplicates() -> None:
    # The case this module exists for. Same budget, same candidates, same objective — the joint
    # search keeps one panel of the duplicate cluster and spends the rest of the budget where
    # nothing has been witnessed yet, and it wins on the objective *and* on raw coverage.
    greedy = select_greedily(_PAPER, budget=3)
    joint = select_jointly(_PAPER, budget=3)

    assert joint.chosen == ("fig2a", "fig3", "table1")
    assert joint.score > greedy.score
    assert len(joint.covered) > len(greedy.covered)
    # Greedy's gross value is the higher of the two — that is exactly what it maximizes — and it
    # pays for it in overlap, so the set-level score inverts the ranking.
    assert greedy.gross_value > joint.gross_value
    assert greedy.overlap_penalty > 0.0
    assert joint.overlap_penalty == 0.0


def test_the_duplicate_cluster_is_represented_but_only_once() -> None:
    # Dropping the cluster entirely would be the opposite failure: it is the paper's headline
    # result and the most valuable single claim there is. Joint selection keeps one, not none.
    joint = select_jointly(_PAPER, budget=3)
    from_cluster = [c for c in joint.chosen if c.startswith("fig2")]
    assert from_cluster == ["fig2a"]


def test_joint_selection_never_loses_to_greedy_on_a_pool_it_could_have_picked() -> None:
    # Greedy's answer is always inside the joint search's feasible set, so a joint answer that
    # scored lower would be a search defect rather than a modelling judgment. 200 pools drawn from
    # a fixed seed, deliberately overlap-heavy: footprints are drawn from a small shared alphabet.
    rng = random.Random(20260828)
    alphabet = [f"p{i}" for i in range(6)]
    for _ in range(200):
        pool = [
            EvidenceItem(
                id=f"c{i}",
                value=round(rng.uniform(0.1, 1.0), 3),
                footprint=frozenset(rng.sample(alphabet, rng.randint(1, 3))),
                cost=float(rng.randint(1, 3)),
            )
            for i in range(8)
        ]
        budget = float(rng.randint(2, 6))
        greedy = select_greedily(pool, budget=budget)
        joint = select_jointly(pool, budget=budget)
        assert joint.score >= greedy.score - 1e-12
        assert joint.cost <= budget


def test_without_overlap_the_two_selections_agree() -> None:
    # No shared machinery is no set-level structure, and the joint objective collapses to the sum
    # greedy maximizes. A selector that reshuffled disjoint claims would be inventing a reason to.
    pool = [
        EvidenceItem("a", value=1.0, footprint=frozenset({"x"})),
        EvidenceItem("b", value=0.9, footprint=frozenset({"y"})),
        EvidenceItem("c", value=0.8, footprint=frozenset({"z"})),
    ]
    assert select_jointly(pool, budget=2).chosen == select_greedily(pool, budget=2).chosen


def test_redundancy_zero_recovers_the_greedy_answer_on_the_duplicate_paper() -> None:
    # The knob is honest in both directions: told that repeated evidence is worth full price, the
    # joint search agrees with greedy on the very case it otherwise overturns.
    joint = select_jointly(_PAPER, budget=3, redundancy=0.0)
    assert joint.chosen == select_greedily(_PAPER, budget=3, redundancy=0.0).chosen


def test_an_uncharacterized_claim_is_never_dropped_for_an_invented_overlap() -> None:
    # An empty footprint means "not characterized", and the objective refuses to guess: it charges
    # no penalty, so an unannotated claim competes on its own value rather than being penalized
    # for a redundancy nobody measured.
    assert jaccard(frozenset(), frozenset({"k"})) == 0.0
    pool = [
        EvidenceItem("annotated_hi", value=1.0, footprint=frozenset({"k"})),
        EvidenceItem("annotated_lo", value=0.9, footprint=frozenset({"k"})),
        EvidenceItem("unannotated", value=0.8),
    ]
    assert select_jointly(pool, budget=2).chosen == ("annotated_hi", "unannotated")


def test_cost_is_respected_and_a_worthless_claim_is_not_bought() -> None:
    pool = [
        EvidenceItem("cheap", value=0.5, cost=1.0),
        EvidenceItem("dear", value=2.0, cost=4.0),
        EvidenceItem("free_and_worthless", value=0.0, cost=1.0),
    ]
    chosen = select_jointly(pool, budget=4.0)
    assert chosen.chosen == ("dear",)
    assert chosen.cost <= 4.0


def test_equal_evidence_for_less_budget_wins() -> None:
    # Two sets carrying the same independent evidence are not equally good: the one that spends
    # less of the budget to carry it is. Without the rule the answer here would be the single
    # expensive claim, at twice the cost for the same score.
    pool = [
        EvidenceItem("a_expensive", value=1.0, footprint=frozenset({"p"}), cost=4.0),
        EvidenceItem("b_cheap", value=0.6, footprint=frozenset({"q"}), cost=1.0),
        EvidenceItem("c_cheap", value=0.4, footprint=frozenset({"r"}), cost=1.0),
    ]
    chosen = select_jointly(pool, budget=4.0)
    assert chosen.chosen == ("b_cheap", "c_cheap")
    assert chosen.score == pytest.approx(1.0)
    assert chosen.cost == 2.0


def test_a_budget_that_affords_nothing_selects_nothing() -> None:
    empty = select_jointly([EvidenceItem("a", value=1.0, cost=2.0)], budget=1.0)
    assert empty.chosen == ()
    assert empty.score == 0.0


def test_a_large_pool_falls_back_to_local_search_and_still_beats_greedy() -> None:
    # Past the exhaustive-search limit the answer is a heuristic, and the guarantee that makes it
    # safe to ship is that it starts at greedy and only moves uphill. Five of fifty is two million
    # subsets, so this is the local-search path.
    #
    # The pool is built so that reaching the better set *requires* exchanging one claim for
    # another. Every chosen claim contributes more on its own than it costs in overlap, so
    # dropping any one of them lowers the score; the budget is full, so nothing can be added. A
    # search that can only add or drop stalls on greedy's answer here, and a swap neighbourhood is
    # the only thing that moves it — which is the whole shape this module was written for.
    shared = [
        EvidenceItem(f"share{i}", value=1.00, footprint=frozenset({"k_el", f"s{i}a", f"s{i}b"}))
        for i in range(10)
    ]
    separate = [
        EvidenceItem(f"sep{i}", value=0.95, footprint=frozenset({f"d{i}x", f"d{i}y", f"d{i}z"}))
        for i in range(40)
    ]
    pool = shared + separate
    greedy = select_greedily(pool, budget=5)
    joint = select_jointly(pool, budget=5)
    assert joint.method == "local-search"
    assert greedy.chosen == tuple(sorted(item.id for item in shared[:5]))
    assert joint.score > greedy.score
    assert len(joint.covered) > len(greedy.covered)


def test_the_same_pool_in_any_order_selects_the_same_set() -> None:
    # Determinism is a product property here too: the selection is a published, contestable
    # decision, so it cannot depend on the order the claims happened to be extracted in.
    rng = random.Random(7)
    shuffled = list(_PAPER)
    rng.shuffle(shuffled)
    assert select_jointly(shuffled, budget=3).chosen == select_jointly(_PAPER, budget=3).chosen


def test_the_reported_numbers_reconstruct_the_score() -> None:
    joint = select_jointly(_PAPER, budget=4)
    assert joint.score == pytest.approx(joint.gross_value - joint.overlap_penalty)
    by_id = {item.id: item for item in _PAPER}
    recomputed = score_set([by_id[c] for c in joint.chosen])
    assert recomputed[0] == pytest.approx(joint.score)


def test_ill_formed_pools_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate evidence item id"):
        select_jointly([EvidenceItem("a", value=1.0), EvidenceItem("a", value=2.0)], budget=2)
    with pytest.raises(ValueError, match="cost must be positive"):
        EvidenceItem("a", value=1.0, cost=0.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        EvidenceItem("a", value=-1.0)
    with pytest.raises(ValueError, match="needs an id"):
        EvidenceItem("  ", value=1.0)
    with pytest.raises(ValueError, match="redundancy cannot be negative"):
        score_set([], redundancy=-1.0)
