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
from reprolith.mcp_server import write_json_atomically
from reprolith.persistence import prune_certificate_directory

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "datasets"


def main() -> None:
    catalog = Catalog()
    entries = seed_catalog(catalog)

    pin: EnginePin = engine_pin()  # the concrete installed COPASI version
    claims = load_claims_dataset(DATASETS / "pkpd_claims.json")
    certified = certified_from_claims(claims, base_dir=DATASETS, engine_pin=pin)

    certificates, report = run_test_set(entries, engine_pin=pin, certified=certified, advance=True)

    out = DATASETS / "milestone" / "agreement_report.json"
    out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")

    # Store each certified certificate's content as JSON so it can be re-opened and served
    # (design goal 3) without recomputing it — e.g. loaded into the MCP server's ledger.
    cert_dir = DATASETS / "milestone" / "certificates"
    cert_dir.mkdir(exist_ok=True)
    prune_certificate_directory(cert_dir, certified)
    for accession, cert in certified.items():
        (cert_dir / f"{accession}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n"
        )

    # Ingest and store each certified entry's dossier (its extracted model structure) and its
    # reconstruction bundle (the adopted model, the recipe, and the assumptions), so the MCP
    # server can serve both for inspection.
    from reprolith import (
        Assumption,
        Claim,
        Identifiers,
        ModelArtifact,
        ModelOrigin,
        RecipeStep,
        ReconstructionBundle,
        estimate_difficulty,
        ingest_sbml,
    )

    dossier_dir = DATASETS / "milestone" / "dossiers"
    bundle_dir = DATASETS / "milestone" / "bundles"
    dossier_dir.mkdir(exist_ok=True)
    bundle_dir.mkdir(exist_ok=True)
    for accession, entry in claims["entries"].items():
        sbml = (DATASETS / entry["model_file"]).read_text(encoding="utf-8")
        dossier = ingest_sbml(sbml, entry=accession, source_label=f"BioModels {accession}")
        (dossier_dir / f"{accession}.json").write_text(
            json.dumps(dossier.to_dict(), indent=2, sort_keys=True) + "\n"
        )
        # Record the advisory difficulty from the ingested dossier's observable signals.
        catalog_entry = catalog.find(Identifiers(title="", accession=accession))
        if catalog_entry is not None:
            catalog_entry.difficulty = estimate_difficulty(dossier)
        # The recipe carries what makes one run differ from another — the sample count, the dose,
        # and the metric read out — so the bundle can re-run the claims it describes. Without them
        # its two steps were identical where the claims differ by dose, and re-running the bundle
        # as published gave the 500 mg answer to both.
        recipe = tuple(
            RecipeStep(claim_id=(c := Claim.from_record(rec)).claim_id, protocol=c.source_location,
                       # SBML concentration notation: `simulate` reads the engine's concentration
                       # data, and a bare species id is the *amount* to anyone who resolves the
                       # symbol as SBML defines it — 2247x apart on this model's real compartments.
                       output=f"[{c.species}]", time_span=f"0-{entry['duration']}",
                       steps=int(entry.get("steps", 480)),
                       parameter_overrides=c.parameter_overrides, metric=c.metric)
            for rec in entry["claims"]
        )
        bundle = ReconstructionBundle(
            entry=accession,
            engine_pin=pin,
            model=ModelArtifact(filename=entry["model_file"], detected_format="sbml", validates=True),
            origin=ModelOrigin.AUTHOR_SUPPLIED,
            recipe=recipe,
            assumptions=tuple(Assumption(**a) for a in entry.get("assumptions", [])),
            source_dossier=accession,
            # Left unchecked, and recorded as unchecked. Adopt-and-verify compares an adopted
            # model against a dossier extracted from the *paper*; here the dossier was ingested
            # from this very file, so the comparison can only ever come back empty and would
            # publish a vacuous agreement as though something had been verified.
            mismatches=None,
        )
        (bundle_dir / f"{accession}.json").write_text(
            json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n"
        )

    # Persist the advanced catalog (lifecycle state, history, and difficulty) so the durable
    # registry reflects the run and can be reloaded — e.g. by the MCP server.
    # Atomic: this file is what both surfaces read at start-up and what a live MCP server
    # re-reads under its lock, and a plain write_text truncates it to zero before writing
    # ~52 KB. A crash in that window leaves a blank catalog behind.
    write_json_atomically(DATASETS / "milestone" / "catalog.json", catalog.to_dict())

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"entries: {len(certificates)} | verdicts: {dict(counts)}")
    print(f"agreement: {report.agreements}/{report.total}")
    print(f"wrote {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
