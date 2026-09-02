"""Whether the gaps a reconstruction must close belong in a claim's footprint. Measured: no.

The `budgeted-claim-selection` proposal asked for them — "include in the footprint every gap
reconstruction must close to run the claim" — and on this corpus that turns out to be a rule that
costs discrimination and buys none, for a reason the proposal could not have known: every
load-bearing gap these dossiers record is a property of the *model*, not of a claim's run. The
reaction network, the compartment volumes, the function definitions, the events and the units are
needed by every claim alike, so adding them to each footprint adds the same constant everywhere.

This is the measurement, kept runnable because the numbers in `docs/claim-selection.md` are only
as true as the corpus they were taken from — a dossier whose gaps were per-claim would change
them, and should reopen the question rather than pass quietly.

Dependency-free: it reads committed dossiers and re-scores them; nothing is simulated.
"""

from __future__ import annotations

import itertools
import json
import statistics
from pathlib import Path

from reprolith import (
    claim_selection_pool,
    dossier_from_dict,
    jaccard,
    select_jointly,
)
from reprolith.selection import EvidenceItem

_DOSSIERS = Path(__file__).resolve().parent.parent / "datasets" / "milestone" / "dossiers"
_ENTRY = "BIOMD0000001028"  # the 33-claim paper, this corpus's largest selection problem


def _dossier(entry: str = _ENTRY):
    return dossier_from_dict(json.loads((_DOSSIERS / f"{entry}.json").read_text("utf-8")))


def _load_bearing_gaps(dossier) -> frozenset[str]:
    return frozenset(gap.element for gap in dossier.gaps if gap.load_bearing)


def test_every_load_bearing_gap_in_this_corpus_is_the_models_not_a_claims() -> None:
    """The premise of the whole finding: these gaps do not vary between claims.

    A gap naming a model-wide property — its reaction network, its compartment volumes — is needed
    by every claim that runs at all. If a dossier ever records a gap that only some claims need,
    this assertion is where that shows up.
    """
    for entry in ("BIOMD0000001027", "BIOMD0000001028", "BIOMD0000001029", "BIOMD0000001039"):
        gaps = _load_bearing_gaps(_dossier(entry))
        assert gaps == {
            "compartment volumes",
            "events",
            "function definitions",
            "reaction network",
            "units",
        }, f"{entry} records a gap this finding was not measured against"


def test_adding_the_gaps_raises_overlap_without_telling_two_claims_apart() -> None:
    dossier = _dossier()
    gaps = _load_bearing_gaps(dossier)
    footprints = [c.footprint for c in dossier.claims if c.targetable and c.footprint]
    assert len(footprints) == 33

    base = [jaccard(a, b) for a, b in itertools.combinations(footprints, 2)]
    with_gaps = [jaccard(a | gaps, b | gaps) for a, b in itertools.combinations(footprints, 2)]

    # Mean overlap rises by half again, and the spread that separates a shared-machinery pair from
    # an independent one *shrinks* — the added set is identical for every claim, so it can only
    # push every pair toward each other.
    assert round(statistics.mean(base), 3) == 0.251
    assert round(statistics.mean(with_gaps), 3) == 0.380
    assert round(max(base) - min(base), 3) == 0.955
    assert round(max(with_gaps) - min(with_gaps), 3) == 0.864


def test_adding_the_gaps_makes_the_selector_decline_claims_the_budget_affords() -> None:
    """The decisive consequence, and the reason this is a rejection rather than a preference.

    Charged as pairwise overlap, a dependency every claim shares makes one more claim's marginal
    value negative — so the answer is a *smaller* set than the budget allows, and the shrinkage is
    driven by machinery the claims have in common rather than by anything about the claims.
    """
    dossier = _dossier("BIOMD0000001027")
    gaps = _load_bearing_gaps(dossier)
    pool = claim_selection_pool(dossier)
    with_gaps = [EvidenceItem(i.id, i.value, i.footprint | gaps, i.cost) for i in pool]

    assert len(select_jointly(pool, budget=4.0).chosen) == 4
    assert len(select_jointly(with_gaps, budget=4.0).chosen) == 3
    assert len(select_jointly(pool, budget=5.0).chosen) == 5
    assert len(select_jointly(with_gaps, budget=5.0).chosen) == 3


def test_the_guide_states_the_numbers_this_rejection_rests_on() -> None:
    page = (
        Path(__file__).resolve().parent.parent / "docs" / "claim-selection.md"
    ).read_text(encoding="utf-8")
    for number in ("0.251", "0.380", "0.955", "0.864"):
        assert number in page, f"docs/claim-selection.md no longer states {number}"
