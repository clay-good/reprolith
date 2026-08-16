"""Seeding the catalog from the labelled PK/PD test set (bootstrap task 1.4).

The bootstrap milestone's acceptance gate is a blind PK/PD test set carrying independent
ground-truth reproducibility labels (spec: ``model-catalog`` — "Blind self-validation test
set"). This loads that set from ``datasets/pkpd_test_set.json`` — real BioModels entries whose
labels come from BioModels' manual-curation status — and adds each one to a catalog as an
``ode-pkpd`` entry with a :class:`~reprolith.catalog.GroundTruth` label attached.

The label rides on the catalog entry and is withheld from the verdict path (design D4); it is
read only later, by the agreement report. Seeding de-duplicates on the BioModels accession, so
re-seeding the same set never creates duplicates.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import Catalog, CatalogEntry, GroundTruth, Identifiers
from .enums import LifecycleState, ModelClass, OverallVerdict
from .screening import Candidate, Screening, screen_candidate

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "datasets" / "pkpd_test_set.json"


def load_test_set(path: Path | str = DEFAULT_DATASET) -> dict[str, Any]:
    """Load the labelled test-set dataset (with its provenance) from disk."""
    with open(path, encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def seed_catalog(
    catalog: Catalog,
    dataset: dict[str, Any] | None = None,
) -> list[CatalogEntry]:
    """Add every dataset entry to ``catalog`` as a labelled ``ode-pkpd`` entry.

    Loads the default dataset when none is given. The ground-truth label records its expected
    verdict and the basis of the label (the dataset's ``label_basis``), so a reviewer can see
    exactly why each entry is labelled as it is. Returns the entries in dataset order.
    """
    if dataset is None:
        dataset = load_test_set()

    basis = dataset.get("label_basis", "")
    model_class = ModelClass(dataset.get("model_class", "ode-pkpd"))
    source = dataset.get("source")
    entries: list[CatalogEntry] = []
    for record in dataset["entries"]:
        label = GroundTruth(
            expected=OverallVerdict(record["expected_verdict"]),
            source=record.get("label_source", basis),
        )
        entry = catalog.add(
            Identifiers(title=record["title"], accession=record["accession"]),
            model_class,
            ground_truth=label,
            source=source,
        )
        entries.append(entry)
    return entries


@dataclass(frozen=True)
class SeedingReport:
    """The outcome of an un-curated seeding pass, so the shift to un-curated intake is observable."""

    seeded: tuple[str, ...]  # accepted as work
    retained: tuple[str, ...]  # uncertain, kept as backlog
    set_aside: tuple[tuple[str, str], ...]  # (title, reason) — not admitted
    blocked_on_access: tuple[str, ...]  # admitted but the model cannot be lawfully obtained

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeded": list(self.seeded),
            "retained": list(self.retained),
            "set_aside": [{"title": t, "reason": r} for t, r in self.set_aside],
            "blocked_on_access": list(self.blocked_on_access),
        }


def seed_candidates(
    catalog: Catalog,
    candidates: Iterable[Candidate],
    *,
    source: str,
    model_class: ModelClass = ModelClass.UNASSIGNED,
    at: str = "seed",
    actor: str = "seeder",
) -> SeedingReport:
    """Seed un-curated candidates through the intake gates (spec: catalog-seeding).

    This is the *explicit* shift from labelled to un-curated seeding (:func:`seed_catalog` is the
    labelled path). Each candidate is screened by :func:`~reprolith.screening.screen_candidate`: a
    set-aside candidate is recorded with its reason and not admitted; an accepted or retained one is
    added to the catalog, tagged with its ``source``, as unlabelled work; and one whose model cannot
    be lawfully obtained is admitted but moved to ``BLOCKED`` on access grounds — not left as
    claimable work it cannot yet become, and not marked failed. Returns a :class:`SeedingReport` so
    the pass is auditable.
    """
    seeded: list[str] = []
    retained: list[str] = []
    set_aside: list[tuple[str, str]] = []
    blocked: list[str] = []

    for candidate in candidates:
        result = screen_candidate(candidate)
        if result.outcome is Screening.SET_ASIDE:
            set_aside.append((candidate.title, result.reason))
            continue

        entry = catalog.add(Identifiers(title=candidate.title), model_class, source=source)
        (retained if result.outcome is Screening.RETAIN else seeded).append(candidate.title)

        if result.blocked_on_access and entry.state is LifecycleState.QUEUED:
            entry.transition(LifecycleState.INGESTING, at=at, actor=actor,
                             reason="attempt to obtain the model from its source")
            entry.transition(LifecycleState.BLOCKED, at=at, actor=actor,
                             reason="the required model cannot be lawfully obtained",
                             missing_inputs=("model artifact (licence/access restricted)",))
            blocked.append(candidate.title)

    return SeedingReport(
        seeded=tuple(seeded), retained=tuple(retained),
        set_aside=tuple(set_aside), blocked_on_access=tuple(blocked),
    )


__all__ = ["DEFAULT_DATASET", "SeedingReport", "load_test_set", "seed_candidates", "seed_catalog"]
