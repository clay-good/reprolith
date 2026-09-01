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


def test_a_report_that_contradicts_its_own_confusion_rows_is_refused() -> None:
    """The partition guard checked one direction and ignored the rows it had already parsed.

    These numbers are the credibility claim the CLI, the MCP surface, and the public registry all
    state. Inflating `agreements` by one integer published 55 matches and 45 wrong verdicts as
    "100 matched, 0 abstentions, 0 other of 100" — and deleting the confusion key entirely did the
    same, which is why an empty rowset with labelled entries is refused rather than skipped.
    """
    import pytest
    from reprolith.agreement import summarize_report

    honest = {"total": 100, "agreements": 55,
              "confusion": {"reproduced->reproduced": 55, "reproduced->not-reproduced": 45}}
    assert summarize_report(honest) == {"total": 100, "matched": 55, "abstained": 0, "other": 45}

    inflated = {**honest, "agreements": 100}
    with pytest.raises(ValueError, match="contradicts its own confusion rows"):
        summarize_report(inflated)
    with pytest.raises(ValueError, match="contradicts its own confusion rows"):
        summarize_report({"total": 100, "agreements": 100})          # rows deleted
    with pytest.raises(ValueError, match="contradicts its own confusion rows"):
        summarize_report({"total": 100, "agreements": 100, "confusion": {}})  # rows emptied
    # An empty report is still an empty report, not a corrupted one.
    assert summarize_report({"total": 0, "agreements": 0, "confusion": {}})["total"] == 0


def test_the_other_column_says_which_direction_it_ran_in() -> None:
    """"other" is where Reprolith was wrong, and it was the only number with no account of itself.

    The abstentions beside it carry a sentence saying they are not wrong verdicts. The column that
    holds the actual wrong verdicts held two different facts under one word: withholding a pass
    somebody else gave, and giving one they withheld. The second is the failure this project exists
    not to commit, and a reader could not tell which they were looking at.
    """
    from reprolith.agreement import confident_differences

    report = {
        "total": 6,
        "agreements": 1,
        "confusion": {
            "reproduced->reproduced": 1,
            "reproduced->partially-reproduced": 3,
            "not-reproduced->reproduced": 1,
            "reproduced->blocked": 1,
        },
    }
    rows = confident_differences(report)
    # The abstention is not here: it is counted apart everywhere else, and this is where the
    # verdicts that actually asserted something wrong are named.
    assert [(r["expected"], r["actual"], r["count"]) for r in rows] == [
        ("not-reproduced", "reproduced", 1),
        ("reproduced", "partially-reproduced", 3),
    ]
    assert rows[0]["direction"] == "a stronger verdict than the label — a false pass"
    assert rows[1]["direction"] == "stricter than the label"

    # And they are exactly the rows `summarize_report` counts as "other", so the two cannot drift.
    from reprolith.agreement import summarize_report

    assert sum(r["count"] for r in rows) == summarize_report(report)["other"]


def test_a_label_that_declined_where_the_verdict_asserted_is_neither_word() -> None:
    """`blocked` is not on the verdict scale — it is the refusal to be placed on it — so an entry
    labelled blocked against a verdict that asserted is not "stricter" or "a false pass"."""
    from reprolith.agreement import confident_differences

    (row,) = confident_differences(
        {"total": 1, "agreements": 0, "confusion": {"blocked->reproduced": 1}}
    )
    assert row["direction"] == "asserted where the label declined to"
