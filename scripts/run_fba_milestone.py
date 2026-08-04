#!/usr/bin/env python3
"""Regenerate the constraint-based (FBA) milestone artifact from committed data.

The constraint-based counterpart of ``run_milestone.py``. Seeds the catalog with the one
ground-truth constraint-based entry (the E. coli core model, labelled by its independently-known
maximal growth rate), certifies it *blind* through the shared ``certify_constraint_based`` — the
verdict path never sees the label — scores agreement with ground truth on the same machinery the
PK/PD run uses, and writes the walkable result: the agreement report, the certificate, and the
advanced catalog.

Reproducible from the repository alone — no network — but needs the ``engine`` extra
(python-libsbml with fbc) and the ``fba`` extra (scipy). Run from the repo root:

    python scripts/run_fba_milestone.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from reprolith import (
    Catalog,
    EnginePin,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    certify_constraint_based,
    run_test_set,
)
from reprolith.persistence import dossier_from_dict

REPO = Path(__file__).resolve().parents[1]
CB = REPO / "datasets" / "constraint_based"
ACCESSION = "e_coli_core"
# A stable, solver-independent pin: the FROG fingerprint is portable, so the LP backend is metadata.
PIN = EnginePin(engine="scipy-highs", version="linprog-highs", algorithm="simplex")


def main() -> None:
    catalog = Catalog()
    entry = catalog.add(
        Identifiers(title="E. coli core metabolic model (Orth, Fleming & Palsson 2010)",
                    accession=ACCESSION),
        ModelClass.CONSTRAINT_BASED,
        ground_truth=GroundTruth(
            expected=OverallVerdict.REPRODUCED,
            source="BiGG / Orth, Fleming & Palsson (2010): known maximal growth rate 0.873922",
        ),
    )

    # Certify blind: the dossier and model are the only inputs; the ground-truth label is never read.
    dossier = dossier_from_dict(
        json.loads((CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
    )
    certificate = certify_constraint_based(
        dossier,
        sbml=(CB / "e_coli_core.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(title=entry.identifiers.title, doi="10.1128/ecosalplus.10.2.1"),
        engine_pin=PIN,
    )

    certificates, report = run_test_set(
        catalog.entries, engine_pin=PIN, certified={ACCESSION: certificate}, advance=True
    )

    milestone = CB / "milestone"
    milestone.mkdir(exist_ok=True)
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    )
    certs = milestone / "certificates"
    certs.mkdir(exist_ok=True)
    (certs / f"{ACCESSION}.json").write_text(
        json.dumps(certificates[0].content(), indent=2, sort_keys=True) + "\n"
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
