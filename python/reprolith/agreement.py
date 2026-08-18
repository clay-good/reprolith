"""Blind self-validation: agreement of Reprolith's verdicts with ground truth (task 7.2).

Ground-truth labels are withheld from the ingestion, reconstruction, and oracle stages
(design D4); this module is where they are finally read — *after* a verdict already exists —
to measure whether Reprolith's blind verdict matches the label. It computes a per-entry and
aggregate agreement report that is the milestone's acceptance gate (spec: ``model-catalog`` —
"Agreement reporting"; bootstrap delta — "Agreement as the milestone gate").

The report is a pure function of stored labels and produced verdicts, so it is reproducible:
the same entries and verdicts always yield the same report.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .catalog import CatalogEntry
from .enums import OverallVerdict


def summarize_report(report: dict[str, Any]) -> dict[str, int]:
    """Split a committed agreement report into matched / abstained / other entry counts.

    The single source of truth for the honesty rule the whole read surface depends on: an
    *abstention* is a *disagreement* whose blind verdict was ``blocked`` — Reprolith declined to
    assert, "insufficient information" — counted apart from a verdict that confidently differed
    from the label ("An abstention is never counted as a wrong verdict"). ``other`` is the
    remaining confident differences. The three partition ``total`` exactly: because an abstention
    is only ever a *disagreement*, a matched entry (including the ``blocked->blocked`` case where
    the label itself was ``blocked``) counts once, in ``matched``, and never also in ``abstained``.
    Reads only the committed report's aggregate counts and its ``expected->actual`` confusion keys.
    Refuses a report whose own counters cannot partition, rather than publishing the nonsense that
    falls out of the subtraction: these numbers are the credibility claim the read surface, the CLI,
    and the public registry all state, so a report missing or misstating ``total`` must be a loud
    failure and never a negative count of wrong verdicts.
    """
    total = int(report.get("total", 0))
    matched = int(report.get("agreements", 0))
    confusion = report.get("confusion", {})
    abstained = 0
    for key, count in confusion.items():
        expected, _, actual = key.partition("->")
        if actual == "blocked" and expected != actual:  # a disagreement that abstained
            abstained += int(count)
    if total < 0 or matched < 0 or matched + abstained > total:
        raise ValueError(
            f"the agreement report does not partition: total={total}, agreements={matched}, "
            f"abstentions={abstained} — matched and abstained cannot exceed the labelled entries"
        )
    # The confusion rows are the report's own account of what happened, so they are checked against
    # the counters rather than only alongside them. The guard above catches an inflated abstention
    # count and used to let an inflated `agreements` through untouched: 55 matching rows and 45
    # wrong verdicts published as 100 agreements and zero disagreements, off one edited integer.
    if confusion:
        rows = sum(int(count) for count in confusion.values())
        agreeing = sum(
            int(count) for key, count in confusion.items()
            if key.partition("->")[0] == key.partition("->")[2]
        )
        if rows != total or agreeing != matched:
            raise ValueError(
                f"the agreement report contradicts its own confusion rows: total={total} and "
                f"agreements={matched}, but the rows record {rows} entries of which {agreeing} "
                "match their label"
            )
    return {"total": total, "matched": matched, "abstained": abstained, "other": total - matched - abstained}


@dataclass(frozen=True)
class EntryAgreement:
    """Whether one labelled entry's blind verdict matched its ground-truth label."""

    entry: str
    expected: str
    actual: str
    agree: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "expected": self.expected,
            "actual": self.actual,
            "agree": self.agree,
            "source": self.source,
        }


@dataclass(frozen=True)
class AgreementReport:
    """Per-entry and aggregate agreement between blind verdicts and ground-truth labels.

    Only labelled entries contribute; an unlabelled entry has nothing to be measured against
    and is skipped rather than counted as agreement.
    """

    per_entry: tuple[EntryAgreement, ...]

    @property
    def total(self) -> int:
        return len(self.per_entry)

    @property
    def agreements(self) -> int:
        return sum(1 for e in self.per_entry if e.agree)

    @property
    def disagreements(self) -> tuple[EntryAgreement, ...]:
        return tuple(e for e in self.per_entry if not e.agree)

    def agreement_rate(self) -> float | None:
        """Fraction of labelled entries whose verdict matched, or ``None`` if none labelled."""
        if not self.per_entry:
            return None
        return self.agreements / self.total

    def confusion(self) -> dict[str, int]:
        """Counts of every ``expected->actual`` pair, so error structure is visible."""
        counts: dict[str, int] = {}
        for e in self.per_entry:
            key = f"{e.expected}->{e.actual}"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_entry": [e.to_dict() for e in self.per_entry],
            "total": self.total,
            "agreements": self.agreements,
            "disagreements": len(self.disagreements),
            "agreement_rate": self.agreement_rate(),
            "confusion": self.confusion(),
        }


def _entry_key(entry: CatalogEntry) -> str:
    ids = entry.identifiers
    return ids.doi or ids.pubmed_id or ids.accession or ids.title


def build_agreement_report(
    items: Iterable[tuple[CatalogEntry, OverallVerdict]],
) -> AgreementReport:
    """Build the agreement report from (entry, produced verdict) pairs.

    Entries without a ground-truth label are skipped. Per-entry results preserve input order,
    so the report is reproducible for a fixed input.
    """
    per_entry: list[EntryAgreement] = []
    for entry, verdict in items:
        label = entry.ground_truth
        if label is None:
            continue
        per_entry.append(
            EntryAgreement(
                entry=_entry_key(entry),
                expected=label.expected.value,
                actual=verdict.value,
                agree=verdict is label.expected,
                source=label.source,
            )
        )
    return AgreementReport(per_entry=tuple(per_entry))


__all__ = ["AgreementReport", "EntryAgreement", "build_agreement_report", "summarize_report"]
