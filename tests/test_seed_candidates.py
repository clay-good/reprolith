"""Un-curated seeding through the intake gates (spec: catalog-seeding). Pure policy, no engine."""

from __future__ import annotations

from reprolith import (
    Candidate,
    Catalog,
    LifecycleState,
    ModelClass,
    seed_candidates,
)


def _candidates() -> list[Candidate]:
    return [
        Candidate(title="Reproducible open model", source="preprint-feed", licence="cc-by",
                  contains_model=True, has_targetable_claim=True),
        Candidate(title="Maybe a model", source="preprint-feed"),  # uncertain -> retained
        Candidate(title="An editorial", source="preprint-feed", contains_model=False),  # set aside
        Candidate(title="Paywalled model", source="preprint-feed", licence="restricted",
                  contains_model=True, has_targetable_claim=True, model_obtainable=False),
    ]


def test_seeds_accepted_and_retained_sets_aside_non_targets() -> None:
    catalog = Catalog()
    report = seed_candidates(
        catalog, _candidates(), source="preprint-feed", model_class=ModelClass.ODE_PKPD
    )
    assert report.seeded == ("Reproducible open model", "Paywalled model")
    assert report.retained == ("Maybe a model",)
    assert [t for t, _ in report.set_aside] == ["An editorial"]
    # The editorial was not admitted; the other three became catalog entries.
    assert len(catalog.entries) == 3


def test_unobtainable_model_is_admitted_but_blocked_on_access() -> None:
    catalog = Catalog()
    report = seed_candidates(
        catalog, _candidates(), source="preprint-feed", model_class=ModelClass.ODE_PKPD
    )
    assert report.blocked_on_access == ("Paywalled model",)
    blocked = next(e for e in catalog.entries if e.identifiers.title == "Paywalled model")
    assert blocked.state is LifecycleState.BLOCKED  # not FAILED, not claimable
    assert not blocked.is_claimable(0.0)


def test_every_seeded_entry_links_back_to_its_source() -> None:
    catalog = Catalog()
    seed_candidates(catalog, _candidates(), source="preprint-feed", model_class=ModelClass.ODE_PKPD)
    for entry in catalog.entries:
        assert "preprint-feed" in entry.sources


def test_one_unobtainable_source_does_not_block_a_paper_another_can_supply() -> None:
    # Two sources describe the same paper, so the catalog resolves them to one entry. Deciding
    # access candidate by candidate blocked that entry on the restricted source and left nothing to
    # ever unblock it, even though the open-access source in the same pass could supply the model.
    catalog = Catalog()
    report = seed_candidates(
        catalog,
        [
            Candidate(title="Same paper", source="publisher", licence="restricted",
                      contains_model=True, has_targetable_claim=True, model_obtainable=False),
            Candidate(title="Same paper", source="repository", licence="cc-by",
                      contains_model=True, has_targetable_claim=True),
        ],
        source="mixed-feed", model_class=ModelClass.ODE_PKPD,
    )
    assert len(catalog.entries) == 1
    entry = catalog.entries[0]
    assert entry.state is not LifecycleState.BLOCKED
    assert entry.is_claimable(0.0)
    assert report.blocked_on_access == ()
    # One resolved entry is one line in the report, not one per candidate that reached it.
    assert report.seeded == ("Same paper",)
    assert report.retained == ()


def test_a_paper_no_source_can_supply_is_still_blocked() -> None:
    catalog = Catalog()
    report = seed_candidates(
        catalog,
        [
            Candidate(title="Locked paper", source="publisher", licence="restricted",
                      contains_model=True, has_targetable_claim=True, model_obtainable=False),
            Candidate(title="Locked paper", source="mirror", licence="restricted",
                      contains_model=True, has_targetable_claim=True, model_obtainable=False),
        ],
        source="mixed-feed", model_class=ModelClass.ODE_PKPD,
    )
    assert report.blocked_on_access == ("Locked paper",)
    assert catalog.entries[0].state is LifecycleState.BLOCKED
