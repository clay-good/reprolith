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


__all__ = ["AgreementReport", "EntryAgreement", "build_agreement_report"]
