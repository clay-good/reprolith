"""Seeding the blind PK/PD test set from real BioModels labels (bootstrap task 1.4)."""

from __future__ import annotations

from reprolith import (
    Catalog,
    LifecycleState,
    ModelClass,
    OverallVerdict,
    ReprolithQuery,
    build_agreement_report,
    load_test_set,
    seed_catalog,
)


def test_dataset_has_both_label_classes() -> None:
    data = load_test_set()
    verdicts = [e["expected_verdict"] for e in data["entries"]]
    # ~20 known-reproducible and ~10 known-hard, per task 1.4.
    assert 18 <= verdicts.count("reproduced") <= 25
    assert 8 <= verdicts.count("not-reproduced") <= 12
    assert data["label_basis"]  # the basis of the labels is documented


def test_every_seeded_entry_carries_a_label_source_and_expected_verdict() -> None:
    catalog = Catalog()
    entries = seed_catalog(catalog)
    assert len(entries) == len(catalog.entries)
    for entry in entries:
        assert entry.model_class is ModelClass.ODE_PKPD
        assert entry.state is LifecycleState.QUEUED
        gt = entry.ground_truth
        assert gt is not None
        assert gt.expected in OverallVerdict  # a concrete expected verdict
        assert gt.source  # the label's source/basis is recorded


def test_reseeding_does_not_duplicate() -> None:
    catalog = Catalog()
    seed_catalog(catalog)
    n = len(catalog)
    seed_catalog(catalog)  # same set again, resolved by accession
    assert len(catalog) == n


def test_labels_are_blind_through_the_query_surface() -> None:
    catalog = Catalog()
    seed_catalog(catalog)
    query = ReprolithQuery(catalog, ledger=_empty_ledger())
    for view in query.list_catalog():
        assert "ground_truth" not in view  # the label never leaves via the read surface


def test_seeded_labels_feed_the_agreement_report() -> None:
    catalog = Catalog()
    entries = seed_catalog(catalog)
    # If Reprolith echoed every label perfectly, agreement would be 100% — this checks the
    # labels flow into the report, not that any real verdicts were produced.
    items = [(e, e.ground_truth.expected) for e in entries]
    report = build_agreement_report(items)
    assert report.total == len(entries)
    assert report.agreement_rate() == 1.0


def _empty_ledger():
    from reprolith import CertificateLedger

    return CertificateLedger()
