#!/usr/bin/env python3
"""Regenerate the constraint-based (FBA) milestone artifact from committed data.

The constraint-based counterpart of ``run_milestone.py``. Seeds the catalog with the constraint-
based entries whose reproducibility is independently known, certifies each *blind* through the
shared ``certify_constraint_based`` — the verdict path never sees the label — scores agreement with
ground truth on the same machinery the PK/PD run uses, and writes the walkable result.

The set is n=7: the E. coli core model, labelled by its documented maximal growth rate, plus six
diverse genome-scale models (``datasets/constraint_based/cross_validation/``) — spanning bacteria, a
pathogen (M. tuberculosis iEK1008), and a eukaryote (S. cerevisiae iMM904) — each labelled by the
growth rate the independent COBRApy implementation computes for it. Every entry's ground-truth
source is recorded on its label.

Reproducible from the repository alone — no network — but needs the ``engine`` extra
(python-libsbml with fbc) and the ``fba`` extra (scipy). Run from the repo root:

    python scripts/run_fba_milestone.py
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

from reprolith import (
    Catalog,
    DossierClaim,
    EnginePin,
    GroundTruth,
    Identifiers,
    ModelArtifact,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    ReferenceKind,
    certify_constraint_based,
    constraint_based_dossier,
    run_test_set,
)
from reprolith.persistence import dossier_from_dict

REPO = Path(__file__).resolve().parents[1]
CB = REPO / "datasets" / "constraint_based"
CROSS = CB / "cross_validation"
# A stable, solver-independent pin: the FROG fingerprint is portable, so the LP backend is metadata.
PIN = EnginePin(engine="scipy-highs", version="linprog-highs", algorithm="simplex")


def _e_coli_core() -> tuple[Identifiers, GroundTruth, object, str]:
    """The E. coli core entry, labelled by its documented growth rate; dossier from the worked example."""
    identifiers = Identifiers(
        title="E. coli core metabolic model (Orth, Fleming & Palsson 2010)", accession="e_coli_core"
    )
    label = GroundTruth(
        expected=OverallVerdict.REPRODUCED,
        source="BiGG / Orth, Fleming & Palsson (2010): known maximal growth rate 0.873922",
    )
    dossier = dossier_from_dict(
        json.loads((CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
    )
    return identifiers, label, dossier, (CB / "e_coli_core.xml").read_text(encoding="utf-8")


def _cross_validation_entry(model_id: str, record: dict) -> tuple[Identifiers, GroundTruth, object, str]:
    """A genome-scale entry, labelled by the COBRApy reference growth; a minimal adopt-and-verify dossier."""
    identifiers = Identifiers(title=f"{model_id} ({record['organism']})", accession=model_id)
    label = GroundTruth(
        expected=OverallVerdict.REPRODUCED,
        source=f"{record['source']}; reference growth {record['reference_growth']:.6f} via "
               f"{record['reference_tool']}",
    )
    dossier = constraint_based_dossier(
        model_id,
        model=ModelArtifact(filename=f"{model_id}.xml.gz", detected_format="sbml-fbc", validates=True),
        objective_claims=[DossierClaim(
            id=f"{model_id}-growth",
            quantity="maximal growth rate on the distributed medium",
            conditions="the model's distributed exchange bounds",
            source_location=record["source"],
            reference_kind=ReferenceKind.NUMERIC,
            reference_data=(record["reference_growth"],),
        )],
        # The distributed model already carries its medium in its bounds; nothing to override.
        medium=(),
    )
    sbml = gzip.decompress((CROSS / f"{model_id}.xml.gz").read_bytes()).decode("utf-8")
    return identifiers, label, dossier, sbml


def main() -> None:
    catalog = Catalog()
    reference = json.loads((CROSS / "reference_growth.json").read_text(encoding="utf-8"))["models"]

    specs = [_e_coli_core()] + [
        _cross_validation_entry(mid, reference[mid]) for mid in sorted(reference)
    ]

    certified = {}
    for identifiers, label, dossier, sbml in specs:
        catalog.add(identifiers, ModelClass.CONSTRAINT_BASED, ground_truth=label)
        # Certify blind: only the dossier and model are inputs; the label is never read.
        certified[identifiers.accession] = certify_constraint_based(
            dossier, sbml=sbml,
            paper=PaperIdentity(title=identifiers.title, doi=""),
            engine_pin=PIN,
        )

    certificates, report = run_test_set(
        catalog.entries, engine_pin=PIN, certified=certified, advance=True
    )

    milestone = CB / "milestone"
    milestone.mkdir(exist_ok=True)
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    )
    certs = milestone / "certificates"
    certs.mkdir(exist_ok=True)
    for accession, cert in certified.items():
        (certs / f"{accession}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n"
        )
    (milestone / "catalog.json").write_text(
        json.dumps(catalog.to_dict(), indent=2, sort_keys=True) + "\n"
    )

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"entries: {len(certificates)} | verdicts: {dict(counts)}")
    print(f"agreement: {report.agreements}/{report.total}")
    print(f"wrote {(milestone / 'agreement_report.json').relative_to(REPO)}")


if __name__ == "__main__":
    main()
