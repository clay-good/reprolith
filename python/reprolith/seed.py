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
from pathlib import Path
from typing import Any

from .catalog import Catalog, CatalogEntry, GroundTruth, Identifiers
from .enums import ModelClass, OverallVerdict

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


__all__ = ["DEFAULT_DATASET", "load_test_set", "seed_catalog"]
