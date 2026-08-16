"""Blind self-validation agreement report (bootstrap task 7.2)."""

from __future__ import annotations

from reprolith import (
    Catalog,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    build_agreement_report,
)


def _labelled(catalog: Catalog, title: str, expected: OverallVerdict, *, doi: str | None = None):
    return catalog.add(
        Identifiers(title=title, doi=doi),
        ModelClass.ODE_PKPD,
        ground_truth=GroundTruth(expected=expected, source="BioModels curation"),
    )


def test_report_scores_per_entry_and_aggregate() -> None:
    catalog = Catalog()
    e1 = _labelled(catalog, "repro A", OverallVerdict.REPRODUCED, doi="10.1/a")
    e2 = _labelled(catalog, "hard B", OverallVerdict.NOT_REPRODUCED, doi="10.1/b")
    e3 = _labelled(catalog, "repro C", OverallVerdict.REPRODUCED, doi="10.1/c")

    report = build_agreement_report([
        (e1, OverallVerdict.REPRODUCED),         # agree
        (e2, OverallVerdict.PARTIALLY_REPRODUCED),  # disagree (expected not-reproduced)
        (e3, OverallVerdict.REPRODUCED),         # agree
    ])

    assert report.total == 3
    assert report.agreements == 2
    assert report.agreement_rate() == 2 / 3
    assert {d.entry for d in report.disagreements} == {"10.1/b"}
    assert report.confusion()["not-reproduced->partially-reproduced"] == 1
    assert report.confusion()["reproduced->reproduced"] == 2


def test_unlabelled_entries_are_skipped() -> None:
    catalog = Catalog()
    labelled = _labelled(catalog, "labelled", OverallVerdict.REPRODUCED, doi="10.1/a")
    unlabelled = catalog.add(Identifiers(title="no label"), ModelClass.ODE_PKPD)

    report = build_agreement_report([
        (labelled, OverallVerdict.REPRODUCED),
        (unlabelled, OverallVerdict.NOT_REPRODUCED),
    ])
    # Only the labelled entry can be measured against ground truth.
    assert report.total == 1
    assert [e.entry for e in report.per_entry] == ["10.1/a"]


def test_empty_report_has_no_rate() -> None:
    assert build_agreement_report([]).agreement_rate() is None


def test_report_is_reproducible() -> None:
    catalog = Catalog()
    e1 = _labelled(catalog, "A", OverallVerdict.REPRODUCED, doi="10.1/a")
    e2 = _labelled(catalog, "B", OverallVerdict.BLOCKED, doi="10.1/b")
    items = [(e1, OverallVerdict.REPRODUCED), (e2, OverallVerdict.NOT_REPRODUCED)]
    # Same labels and verdicts -> byte-identical report, so the gate is auditable.
    assert build_agreement_report(items).to_dict() == build_agreement_report(items).to_dict()


def test_report_records_the_label_source() -> None:
    catalog = Catalog()
    e = _labelled(catalog, "A", OverallVerdict.REPRODUCED, doi="10.1/a")
    report = build_agreement_report([(e, OverallVerdict.REPRODUCED)])
    assert report.per_entry[0].source == "BioModels curation"


def test_summarize_report_partitions_and_never_double_counts_a_matched_abstention() -> None:
    """matched / abstained / other partition total exactly, even when the label itself is blocked."""
    from reprolith.agreement import summarize_report

    # A report with: one matched reproduction, one matched abstention (label was blocked and the
    # verdict abstained -> agree), 30 honest abstentions on reproducible-labelled entries, and one
    # confident difference. A matched abstention must count only as matched, never also as abstained.
    report = {
        "total": 33,
        "agreements": 2,  # reproduced->reproduced and blocked->blocked
        "confusion": {
            "reproduced->reproduced": 1,
            "blocked->blocked": 1,           # matched abstention — not a disagreement
            "reproduced->blocked": 30,       # honest abstentions
            "not-reproduced->reproduced": 1,  # a confident difference (wrong verdict)
        },
    }
    s = summarize_report(report)
    assert s["matched"] == 2
    assert s["abstained"] == 30  # the blocked->blocked match is excluded
    assert s["other"] == 1
    assert s["matched"] + s["abstained"] + s["other"] == s["total"]  # exact partition


def test_a_report_whose_counters_cannot_partition_is_refused() -> None:
    # These counts are the credibility claim the read surface, the CLI, and the public registry all
    # state. A report missing its total used to yield a NEGATIVE count of wrong verdicts, served
    # verbatim; the subtraction must fail loudly instead of publishing nonsense.
    import pytest
    from reprolith.agreement import summarize_report

    no_total = {"agreements": 29, "confusion": {"reproduced->blocked": 30}}
    with pytest.raises(ValueError, match="does not partition"):
        summarize_report(no_total)

    overcounted = {"total": 2, "agreements": 3, "confusion": {}}
    with pytest.raises(ValueError, match="does not partition"):
        summarize_report(overcounted)

    # An honestly empty report is still a legal partition of nothing.
    assert summarize_report({"total": 0, "agreements": 0, "confusion": {}})["other"] == 0
