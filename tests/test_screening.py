"""Seeding's intake gates: quality and licensing/ethics (spec: catalog-seeding).

Pure policy, no engine — these run in the core CI job.
"""

from __future__ import annotations

from reprolith import Candidate, Screening, screen_candidate, storable_content


def test_a_clear_non_target_is_set_aside_with_a_reason() -> None:
    result = screen_candidate(Candidate(title="An editorial", source="feed", contains_model=False))
    assert result.outcome is Screening.SET_ASIDE
    assert "no reproducible computational model" in result.reason


def test_an_uncertain_candidate_is_retained_as_backlog_not_dropped() -> None:
    # The honest default for un-curated intake: unknown signals -> keep as backlog.
    result = screen_candidate(Candidate(title="Maybe a model", source="feed"))
    assert result.outcome is Screening.RETAIN
    assert "retained as backlog" in result.reason


def test_a_model_with_no_targetable_claim_is_set_aside() -> None:
    result = screen_candidate(
        Candidate(title="Model, no results", source="feed",
                  contains_model=True, has_targetable_claim=False)
    )
    assert result.outcome is Screening.SET_ASIDE
    assert "no targetable claim" in result.reason


def test_a_reproducible_candidate_is_accepted() -> None:
    result = screen_candidate(
        Candidate(title="A PK model with a table", source="feed", licence="cc-by",
                  contains_model=True, has_targetable_claim=True)
    )
    assert result.outcome is Screening.ACCEPT
    assert not result.blocked_on_access


def test_patient_data_source_is_excluded_outright() -> None:
    # No scope creep into patient or personal data, regardless of other signals.
    result = screen_candidate(
        Candidate(title="Clinical dataset", source="feed",
                  contains_model=True, has_targetable_claim=True, carries_personal_data=True)
    )
    assert result.outcome is Screening.SET_ASIDE
    assert "personal data" in result.reason
    assert result.storable == ()


def test_restricted_licence_stores_only_metadata() -> None:
    assert storable_content("restricted") == ("metadata", "citation")
    assert storable_content(None) == ("metadata", "citation")
    assert "full-text" in storable_content("cc-by") and "model" in storable_content("CC0")


def test_unobtainable_model_is_accepted_but_blocked_on_access() -> None:
    # A reproducible target whose model cannot be lawfully fetched is admitted blocked, not failed.
    result = screen_candidate(
        Candidate(title="Paywalled model", source="feed", licence="restricted",
                  contains_model=True, has_targetable_claim=True, model_obtainable=False)
    )
    assert result.outcome is Screening.ACCEPT
    assert result.blocked_on_access
    assert result.storable == ("metadata", "citation")
