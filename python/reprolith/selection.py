"""Choosing *which* claims to reproduce when the budget will not cover them all.

Nothing in Reprolith reproduces a paper's claims selectively today: :func:`~reprolith.certify.
certify_model` and its siblings take the claims they are handed and check every one. The choosing
happens outside the engine — by hand, when a claims dataset is written — and it has no surface to
be explainable or contestable at. This module is that surface.

The problem it solves is not "pick the best claims", it is **pick the best set**. A paper's
claims are not independent evidence: two panels of the same figure driven by the same rate
constants, the same reaction network, and the same unstated initial condition rest on one piece of
machinery. Reproducing both witnesses that machinery twice and everything else not at all. Ranking
claims by their own worth and taking the top of the list — :func:`select_greedily`, the baseline
every hand-written selection reduces to — cannot see that, because it never asks what a claim adds
*given the ones already chosen*. When the highest-worth claims are near-duplicates of each other,
greedy spends the whole budget on one region of the model.

:func:`select_jointly` scores the *set*: the sum of what its items are worth, less a penalty for
the evidence they share. Two claims overlap to the extent their footprints do — the parameters,
model components, and upstream assumptions each one's verdict rests on — measured as a Jaccard
ratio, so a claim that shares nothing costs nothing and a pair of exact duplicates cancels the
cheaper one out entirely.

Footprints are supplied by the caller, never guessed. A claim's ``quantity`` and ``conditions``
are free text; matching parameter names out of them would invent a dependency graph and then
select against it, and a selection defended by a fabricated overlap is worse than an unexplained
one. What a claim rests on is a modelling judgment, and this module records it rather than
deriving it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Any

from .dossier import Dossier

#: How many affordable subsets the exhaustive search will score before it gives up and hands the
#: pool to greedy-seeded local search. What bounds the count is the budget as much as the pool:
#: choosing four of twenty claims is three thousand subsets, so the exact answer is the normal
#: case for one paper and the heuristic is the tail where the budget covers nearly everything.
_EXACT_SUBSET_LIMIT = 200_000


@dataclass(frozen=True)
class EvidenceItem:
    """A candidate claim or figure, its standalone worth, its cost, and what it rests on.

    ``footprint`` is what makes this a *set* problem: the parameters, model components, and
    upstream assumptions whose correctness the item's verdict depends on. Two items sharing a
    footprint are, to that extent, one piece of evidence reported twice. An empty footprint says
    the item shares nothing with anything — which is a strong claim, and the reason it is not the
    silent default for an item the caller never characterized.
    """

    id: str
    value: float
    footprint: frozenset[str] = frozenset()
    cost: float = 1.0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("every evidence item needs an id")
        if self.value < 0.0:
            raise ValueError(f"{self.id}: evidential value cannot be negative")
        if self.cost <= 0.0:
            raise ValueError(f"{self.id}: cost must be positive, or the budget bounds nothing")


@dataclass(frozen=True)
class Selection:
    """A chosen set, what it scores, and every number that put it there."""

    chosen: tuple[str, ...]
    score: float
    gross_value: float
    overlap_penalty: float
    cost: float
    budget: float
    method: str
    #: The footprint elements the chosen set witnesses at least once — the coverage a set-level
    #: objective exists to protect, and the number that makes a greedy selection's loss visible.
    covered: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": list(self.chosen),
            "score": self.score,
            "gross_value": self.gross_value,
            "overlap_penalty": self.overlap_penalty,
            "cost": self.cost,
            "budget": self.budget,
            "method": self.method,
            "covered": list(self.covered),
        }


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """How much two footprints share, in [0, 1]. Two empty footprints share nothing.

    Zero for the empty case is the conservative reading in the direction that matters: an
    uncharacterized item is treated as overlapping nothing, so the objective never *invents* a
    redundancy and drops a claim on the strength of it. The cost is that a caller who leaves every
    footprint empty gets the greedy answer back — correctly, since there is then no set-level
    structure to exploit.
    """
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score_set(
    items: Sequence[EvidenceItem], *, redundancy: float = 1.0
) -> tuple[float, float, float]:
    """Score a set as (score, gross value, overlap penalty).

    The penalty for a pair is ``redundancy * jaccard(footprints) * min(value)``: it is charged
    against the *cheaper* of the two, so a pair of duplicates keeps the more valuable one's
    evidence and cancels the other's. ``redundancy`` scales the whole penalty — 0 recovers the
    plain sum that greedy maximizes, and 1 (the default) treats fully-shared evidence as fully
    redundant.
    """
    if redundancy < 0.0:
        raise ValueError("redundancy cannot be negative")
    gross = sum(item.value for item in items)
    penalty = sum(
        redundancy * jaccard(a.footprint, b.footprint) * min(a.value, b.value)
        for a, b in combinations(items, 2)
    )
    return gross - penalty, gross, penalty


def select_greedily(
    items: Iterable[EvidenceItem], *, budget: float, redundancy: float = 1.0
) -> Selection:
    """The baseline: take the best value-per-cost item that still fits, one at a time.

    This is what ranking a list and reading down it does, and it is the shape every ad-hoc "which
    claims can we afford" decision takes. It is kept here to be *measured against*: the returned
    :class:`Selection` is scored by the same set-level objective as :func:`select_jointly`, so the
    two are directly comparable, and a case where greedy loses is a case where the top of the
    ranking is several views of the same evidence.
    """
    pool = _validated(items)
    order = sorted(pool, key=lambda item: (-item.value / item.cost, item.id))
    chosen: list[EvidenceItem] = []
    spent = 0.0
    for item in order:
        if spent + item.cost <= budget:
            chosen.append(item)
            spent += item.cost
    return _selection(chosen, budget=budget, redundancy=redundancy, method="greedy")


def select_jointly(
    items: Iterable[EvidenceItem], *, budget: float, redundancy: float = 1.0
) -> Selection:
    """Choose the set that maximizes independent evidential value within ``budget``.

    Exact whenever the budget admits at most :data:`_EXACT_SUBSET_LIMIT` subsets — every
    affordable one is scored, which is the normal case for one paper's claims. Beyond that the
    search starts from the greedy answer and improves it by add/drop/swap steps until no single
    step helps; the result is reported with ``method="local-search"`` and is never worse than
    :func:`select_greedily`, because greedy is where it starts.
    """
    pool = _validated(items)
    if _affordable_subsets(pool, budget) <= _EXACT_SUBSET_LIMIT:
        return _exact(pool, budget=budget, redundancy=redundancy)
    return _local_search(pool, budget=budget, redundancy=redundancy)


def claim_selection_pool(
    dossier: Dossier,
    *,
    values: Mapping[str, float] | None = None,
    costs: Mapping[str, float] | None = None,
) -> tuple[EvidenceItem, ...]:
    """The candidate pool for one paper: its targetable claims, with their recorded footprints.

    Only targetable claims are candidates. A schematic figure the oracle cannot check is retained
    in the dossier but is not something a budget can be spent on, so offering it as a candidate
    would let a selection spend the budget on a claim no verdict can ever come from.

    ``values`` and ``costs`` are the caller's, defaulting to 1.0. Equal value is the honest
    default rather than a placeholder: Reprolith holds no basis for calling one of a paper's
    published results more valuable than another, and inventing one — figure panels over table
    cells, say — would be a ranking dressed as a measurement. Under equal values the objective
    reduces to spreading the budget across the machinery the claims rest on, which is the part
    this module can actually defend.
    """
    values = values or {}
    costs = costs or {}
    unknown = sorted((set(values) | set(costs)) - {c.id for c in dossier.claims})
    if unknown:
        # A value keyed to a claim id that is not in the dossier is a typo that silently does
        # nothing, and it does nothing to the *selection* — which is then defended by numbers the
        # caller believes were applied and were not.
        raise ValueError("no such claim in this dossier: " + ", ".join(unknown))
    return tuple(
        EvidenceItem(
            id=claim.id,
            value=values.get(claim.id, 1.0),
            footprint=claim.footprint,
            cost=costs.get(claim.id, 1.0),
        )
        for claim in dossier.targetable_claims()
    )


#: What a selection is, said in the report itself. The certificate scope statement is not reusable
#: here — it opens "This certificate attests…", and a selection certifies nothing, runs no model,
#: and reaches no verdict — so this report says its own scope in its own words.
SELECTION_NOTE = (
    "This is a plan for what to attempt, not a result. No model is run and no verdict is reached; "
    "a claim left unselected is neither reproduced nor unreproduced, only unattempted. Which "
    "results matter is the reader's judgment, never this selection's."
)

#: How a selection describes what it maximized, for the certificate that ends up resting on it.
#: The reader of a budgeted certificate is being asked to accept that the claims it did not
#: attempt were the right ones to skip, and the only way to contest that is to know the criterion.
#: Named here, beside the objective it names, so the sentence on the certificate and the code that
#: chose cannot drift apart.
SET_OBJECTIVE = "independent evidential value: set value less footprint overlap"


def stated_objective(selection: Selection) -> str:
    """The objective sentence a certificate records for ``selection``, search method included.

    The method belongs in it: ``local-search`` returns a set that is never worse than the greedy
    baseline but is not proven optimal, and a reader weighing what was skipped should not have to
    guess which of the two answers they are looking at.
    """
    return f"{SET_OBJECTIVE} ({selection.method})"


#: Said whenever no candidate claim records what it rests on. The selection is then greedy's
#: answer under another name, and a surface that presented it as an optimized set would be
#: claiming an analysis it did not perform.
UNCHARACTERIZED_NOTE = (
    "no candidate claim records a footprint, so nothing here was chosen for its independence: "
    "with no recorded overlap to measure, the set-level objective is the plain sum the ranking "
    "already maximizes, and this selection is the greedy one"
)

#: Said when the dossier offers no targetable claim at all. Distinguishing this from "the budget
#: afforded nothing" matters: both select nothing, and only one of them is fixed by a bigger
#: budget. Every dossier in the repository but one is in this state.
EMPTY_POOL_NOTE = (
    "this dossier records no targetable claim, so there was nothing to select from and a larger "
    "budget would change nothing"
)

#: Said when only some claims record a footprint. An uncharacterized claim is charged no overlap
#: by design, which protects it from an invented redundancy and, in the same motion, makes it look
#: maximally independent next to a claim whose dependencies were honestly written down.
PARTIAL_NOTE = (
    "{characterized} of {total} candidate claims record a footprint; the rest are charged no "
    "overlap because none was measured, so they compete as if independent of everything"
)


def claim_selection_report(
    dossier: Dossier,
    *,
    budget: float,
    values: Mapping[str, float] | None = None,
    costs: Mapping[str, float] | None = None,
    redundancy: float = 1.0,
) -> dict[str, Any]:
    """Which of a paper's claims to reproduce within ``budget``, and everything behind the answer.

    The report carries the greedy baseline beside the joint selection on purpose. A selection is a
    decision about what evidence a certificate will and will not rest on, so what it *changed* is
    part of the finding: where the two agree there was no set-level structure to exploit, and where
    they differ the report shows what the ranking would have bought instead.

    ``limits`` is where the report says what it could not do — a claim with no recorded footprint
    is charged no overlap, so a pool of them gets the greedy answer back under another name, and
    saying so is the difference between an honest report and one claiming an analysis it did not
    perform. That was the whole corpus's state until footprints were derived from the model files;
    it is still every dossier outside the four metformin entries.
    """
    pool = claim_selection_pool(dossier, values=values, costs=costs)
    joint = select_jointly(pool, budget=budget, redundancy=redundancy)
    greedy = select_greedily(pool, budget=budget, redundancy=redundancy)
    characterized = sum(1 for item in pool if item.footprint)
    limits: list[str] = []
    if not pool:
        limits.append(EMPTY_POOL_NOTE)
    elif not characterized:
        limits.append(UNCHARACTERIZED_NOTE)
    elif characterized < len(pool):
        limits.append(PARTIAL_NOTE.format(characterized=characterized, total=len(pool)))
    return {
        "entry": dossier.entry,
        "budget": budget,
        "candidates": len(pool),
        "characterized_candidates": characterized,
        "selection": joint.to_dict(),
        "greedy_baseline": greedy.to_dict(),
        "differs_from_greedy": joint.chosen != greedy.chosen,
        "unanchored_footprint_elements": list(dossier.unanchored_footprint_elements()),
        "limits": limits,
        "note": SELECTION_NOTE,
    }


def _max_size(pool: Sequence[EvidenceItem], budget: float) -> int:
    """The most items the budget can hold, taking the cheapest first — a bound, not a guess."""
    spent = 0.0
    size = 0
    for item in sorted(pool, key=lambda x: x.cost):
        if spent + item.cost > budget:
            break
        spent += item.cost
        size += 1
    return size


def _affordable_subsets(pool: Sequence[EvidenceItem], budget: float) -> int:
    """An upper bound on how many subsets the exhaustive search would enumerate."""
    return sum(comb(len(pool), size) for size in range(_max_size(pool, budget) + 1))


def _validated(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    """The pool as a list, in a deterministic order, with duplicate ids refused.

    Two items under one id makes the returned ``chosen`` ambiguous — the caller cannot tell which
    claim was selected — so it is a caller error rather than something silently deduplicated.
    """
    pool = sorted(items, key=lambda item: item.id)
    seen: set[str] = set()
    for item in pool:
        if item.id in seen:
            raise ValueError(f"duplicate evidence item id: {item.id}")
        seen.add(item.id)
    return pool


def _selection(
    chosen: Sequence[EvidenceItem], *, budget: float, redundancy: float, method: str
) -> Selection:
    score, gross, penalty = score_set(chosen, redundancy=redundancy)
    covered: set[str] = set()
    for item in chosen:
        covered |= item.footprint
    return Selection(
        chosen=tuple(sorted(item.id for item in chosen)),
        score=score,
        gross_value=gross,
        overlap_penalty=penalty,
        cost=sum(item.cost for item in chosen),
        budget=budget,
        method=method,
        covered=tuple(sorted(covered)),
    )


def _rank(subset: Sequence[EvidenceItem], redundancy: float) -> tuple[float, float, list[str]]:
    """A set's sort key: score first, then the deterministic tie-breaks.

    Ties break toward the cheaper set, then the sorted ids. Cheaper first is the substantive half:
    two sets carrying the same independent evidence are not equally good if one of them spends
    more of the budget to do it, and the rule is what keeps a claim that adds nothing — a
    duplicate whose whole value is cancelled by its overlap — from being bought anyway. Sorted ids
    are the last resort, so the answer never depends on the order the claims were extracted in.
    The score is negated so the whole key sorts ascending, smallest-is-best.
    """
    score = score_set(subset, redundancy=redundancy)[0]
    return (-score, sum(i.cost for i in subset), sorted(i.id for i in subset))


def _exact(pool: Sequence[EvidenceItem], *, budget: float, redundancy: float) -> Selection:
    best: list[EvidenceItem] = []
    best_rank = _rank(best, redundancy)
    for size in range(1, _max_size(pool, budget) + 1):
        for subset in combinations(pool, size):
            if sum(item.cost for item in subset) > budget:
                continue
            rank = _rank(subset, redundancy)
            if rank < best_rank:
                best, best_rank = list(subset), rank
    return _selection(best, budget=budget, redundancy=redundancy, method="exact")


def _local_search(pool: Sequence[EvidenceItem], *, budget: float, redundancy: float) -> Selection:
    seed = select_greedily(pool, budget=budget, redundancy=redundancy)
    by_id = {item.id: item for item in pool}
    current = [by_id[cid] for cid in seed.chosen]
    current_rank = _rank(current, redundancy)
    while True:
        best_move = None
        for move in _moves(current, pool, budget=budget):
            rank = _rank(move, redundancy)
            if rank < current_rank:
                best_move, current_rank = move, rank
        if best_move is None:
            break
        current = best_move
    return _selection(current, budget=budget, redundancy=redundancy, method="local-search")


def _moves(
    current: Sequence[EvidenceItem], pool: Sequence[EvidenceItem], *, budget: float
) -> list[list[EvidenceItem]]:
    """Every affordable one-step neighbour of ``current``: drop one, add one, or swap one for one.

    Swaps are what a drop-only or add-only neighbourhood cannot reach: replacing a near-duplicate
    with a claim covering untouched machinery is a single move here and two individually-worse
    moves otherwise, so a search without it stalls on exactly the sets this module exists to fix.
    """
    inside = {item.id for item in current}
    outside = [item for item in pool if item.id not in inside]
    spent = sum(item.cost for item in current)
    moves: list[list[EvidenceItem]] = []
    for item in current:
        moves.append([x for x in current if x.id != item.id])
    for item in outside:
        if spent + item.cost <= budget:
            moves.append([*current, item])
    for out in current:
        for item in outside:
            if spent - out.cost + item.cost <= budget:
                moves.append([x for x in current if x.id != out.id] + [item])
    return moves


__all__ = [
    "EMPTY_POOL_NOTE",
    "SET_OBJECTIVE",
    "EvidenceItem",
    "PARTIAL_NOTE",
    "SELECTION_NOTE",
    "Selection",
    "UNCHARACTERIZED_NOTE",
    "claim_selection_pool",
    "claim_selection_report",
    "jaccard",
    "score_set",
    "select_greedily",
    "select_jointly",
    "stated_objective",
]
