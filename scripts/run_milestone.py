#!/usr/bin/env python3
"""Regenerate the bootstrap milestone artifact from committed data.

Seeds the catalog from the labelled test set, certifies every entry that has verified claims
in the claims dataset (currently metformin, whose model ships in datasets/worked_examples/),
honestly blocks the rest, scores agreement with ground truth, and writes the agreement report.

Reproducible from the repository alone — no network — but needs the optional engine extra
(``pip install -e ".[dev,engine]"``) to run the certified entries. Run from the repo root:

    python scripts/run_milestone.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from reprolith import (
    Catalog,
    EnginePin,
    certified_from_claims,
    engine_pin,
    load_claims_dataset,
    run_test_set,
    seed_catalog,
)

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "datasets"


def main() -> None:
    catalog = Catalog()
    entries = seed_catalog(catalog)

    pin: EnginePin = engine_pin()  # the concrete installed COPASI version
    claims = load_claims_dataset(DATASETS / "pkpd_claims.json")
    certified = certified_from_claims(claims, base_dir=DATASETS, engine_pin=pin)

    certificates, report = run_test_set(entries, engine_pin=pin, certified=certified)

    out = DATASETS / "milestone" / "agreement_report.json"
    out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"entries: {len(certificates)} | verdicts: {dict(counts)}")
    print(f"agreement: {report.agreements}/{report.total}")
    print(f"wrote {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
