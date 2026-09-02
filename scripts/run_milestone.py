#!/usr/bin/env python3
"""Regenerate the bootstrap milestone artifact from committed data.

Seeds the catalog from the labelled test set, certifies every entry that has verified claims
in the claims dataset (currently metformin, whose model ships in datasets/worked_examples/),
honestly blocks the rest, scores agreement with ground truth, and writes the agreement report.

Reproducible from the repository alone — no network — but needs the optional ``engine`` extra to
run the certified entries and the ``corroborate`` extra (libRoadRunner) for the per-claim engine
independence check (``pip install -e ".[dev,engine,corroborate]"``). Run from the repo root:

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
    corroborate_curve,
    engine_pin,
    load_claims_dataset,
    run_test_set,
    seed_catalog,
)
from reprolith.mcp_server import write_json_atomically
from reprolith.persistence import prune_certificate_directory

REPO = Path(__file__).resolve().parents[1]
DATASETS = REPO / "datasets"


def _artifact_validates(sbml: str) -> bool:
    """Whether libSBML reads this artifact without a fatal error — measured, not asserted.

    Both milestone scripts wrote `validates=True` as a literal, and `validate_constraint_based`
    then *checks* that flag as evidence the adopted model validates, while `estimate_difficulty`
    reads it as "a runnable model shipped". A self-asserted flag consumed as a measurement is the
    same defect as an empty mismatch list standing for an unrun comparison — which the very next
    field in this constructor refuses to do, and says so. `ingest_sbml` has always computed it.
    """
    from reprolith.sbml import _libsbml

    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    return not any(
        document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        for i in range(document.getNumErrors())
    )


def main() -> None:
    catalog = Catalog()
    entries = seed_catalog(catalog)
    corroboration: dict[str, dict[str, object]] = {}

    pin: EnginePin = engine_pin()  # the concrete installed COPASI version
    claims = load_claims_dataset(DATASETS / "pkpd_claims.json")
    certified = certified_from_claims(claims, base_dir=DATASETS, engine_pin=pin)

    certificates, report = run_test_set(entries, engine_pin=pin, certified=certified, advance=True)

    out = DATASETS / "milestone" / "agreement_report.json"
    out.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Store each certified certificate's content as JSON so it can be re-opened and served
    # (design goal 3) without recomputing it — e.g. loaded into the MCP server's ledger.
    cert_dir = DATASETS / "milestone" / "certificates"
    cert_dir.mkdir(exist_ok=True)
    prune_certificate_directory(cert_dir, certified)
    for accession, cert in certified.items():
        (cert_dir / f"{accession}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # Ingest and store each certified entry's dossier (its extracted model structure) and its
    # reconstruction bundle (the adopted model, the recipe, and the assumptions), so the MCP
    # server can serve both for inspection.
    from dataclasses import replace

    from reprolith import (
        Assumption,
        Claim,
        DossierClaim,
        Identifiers,
        ModelArtifact,
        ModelOrigin,
        RecipeStep,
        ReconstructionBundle,
        ReferenceKind,
        estimate_difficulty,
        ingest_sbml,
    )
    from reprolith.footprints import derive_footprints


    dossier_dir = DATASETS / "milestone" / "dossiers"
    bundle_dir = DATASETS / "milestone" / "bundles"
    dossier_dir.mkdir(exist_ok=True)
    bundle_dir.mkdir(exist_ok=True)
    for accession, entry in claims["entries"].items():
        sbml = (DATASETS / entry["model_file"]).read_text(encoding="utf-8")
        dossier = ingest_sbml(sbml, entry=accession, source_label=f"BioModels {accession}")
        # The paper's own claims, joined onto the structure ingested from its model file. A model
        # states no claims — it says what *can* be read, never what the paper showed — so an
        # SBML-only dossier records none, and every dossier in this repository recorded zero.
        # `select-claims` reads a dossier's claims, so it had nothing to select from anywhere;
        # `covers()` compared a bundle against a dossier that listed nothing. The claims are not
        # invented here: each is the curated record from `pkpd_claims.json`, carrying the source
        # location the curator read it from.
        #
        # And each one's footprint is derived from the model that produces it — what the claim's
        # verdict rests on, read off the reactions, rules and compartments rather than matched out
        # of its own prose. See `reprolith.footprints`.
        targets = [record["species"] for record in entry["claims"]]
        footprints = derive_footprints(sbml, targets)
        dossier = replace(dossier, claims=tuple(
            DossierClaim(
                id=record["claim_id"],
                quantity=record["quantity"],
                # What distinguishes this claim's run from the entry's other ones. The dose arm is
                # in the quantity for these papers; the conditions field carries the metric read.
                conditions=f"{record['metric']} of {record['species']}",
                source_location=record["source_location"],
                reference_kind=ReferenceKind.NUMERIC,
                reference_data=(float(record["reported"]),),
                footprint=footprints[record["species"]],
            )
            for record in entry["claims"]
        ))
        (dossier_dir / f"{accession}.json").write_text(
            json.dumps(dossier.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
                       output=f"[{c.species}]",
                       # A scheduled claim's window is its *last* segment, not the entry's
                       # default: the run the claim reports starts where the prior doses left off.
                       time_span=f"0-{c.schedule[-1][0] if c.schedule else entry['duration']}",
                       steps=int(entry.get("steps", 480)),
                       parameter_overrides=c.parameter_overrides, metric=c.metric,
                       schedule=c.schedule)
            for rec in entry["claims"]
        )
        bundle = ReconstructionBundle(
            entry=accession,
            engine_pin=pin,
            model=ModelArtifact(
                filename=entry["model_file"], detected_format="sbml",
                validates=_artifact_validates(
                    (DATASETS / entry["model_file"]).read_text(encoding="utf-8")
                ),
            ),
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
        # `covers()` exists to stop a bundle overstating what it addresses, and until the dossiers
        # carried the paper's claims it could not be called on anything: it compared a recipe
        # against a dossier that listed nothing, returned false on every shipped pair, and was
        # called from no code at all. Now that both sides name the same claims it is a gate. A
        # bundle that has drifted from its dossier — a claim with no recipe step, a step naming a
        # claim the paper does not make — is a reconstruction whose published scope is wrong, and
        # publishing it quietly is exactly what this was written to prevent.
        if not bundle.covers(dossier):
            raise SystemExit(
                f"{accession}: the reconstruction bundle does not cover its dossier — "
                f"claims with no recipe step: {bundle.uncovered_claims(dossier)}; "
                f"steps naming no claim: {bundle.unmatched_steps(dossier)}"
            )
        (bundle_dir / f"{accession}.json").write_text(
            json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Engine independence, per claim: the same curve under both COPASI and libRoadRunner
        # (spec: simulation-oracle). The kinetic milestone has reported this since it shipped and
        # PK/PD never did, so the class carrying the one manuscript-checked reproduction in the
        # corpus was also the one whose verdicts rested, as far as any artifact showed, on a
        # single solver. Driven off the bundle's own recipe, overrides included, so what is
        # corroborated is the run each claim actually made and not just the model's default arm.
        model_sbml = (DATASETS / entry["model_file"]).read_text(encoding="utf-8")
        for step in recipe:
            result = corroborate_curve(
                model_sbml,
                step.output.strip("[]"),
                duration=float(step.time_span.split("-", 1)[1]),
                steps=int(step.steps or 480),
                overrides=step.parameter_overrides,
                # Without this the scheduled claims were corroborated against the model's default
                # arm and published `engine_independent` under their own claim ids — the exact
                # "not just the model's default arm" failure the comment above claims to prevent,
                # by a route it did not cover.
                schedule=step.schedule,
            )
            corroboration[f"{accession}:{step.claim_id}"] = {
                # The engines, the builds they ran as, and the distance as a bound rather than a
                # measurement — the fields every class's record shares, from one place.
                **result.record(),
                # The values in force for the window that was corroborated. For a scheduled step
                # they live in its last segment, and reading `parameter_overrides` alone showed
                # `{}` for a claim that runs at 194.96 mg — a record saying the default arm ran.
                "overrides": {
                    name: value
                    for name, value in (
                        step.schedule[-1][1] if step.schedule else step.parameter_overrides
                    )
                },
                "prior_administrations": [
                    {"duration": duration, "overrides": {n: v for n, v in overrides}}
                    for duration, overrides in step.schedule[:-1]
                ],
            }

    (DATASETS / "milestone" / "corroboration.json").write_text(
        json.dumps(corroboration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Persist the advanced catalog (lifecycle state, history, and difficulty) so the durable
    # registry reflects the run and can be reloaded — e.g. by the MCP server.
    # Atomic: this file is what both surfaces read at start-up and what a live MCP server
    # re-reads under its lock, and a plain write_text truncates it to zero before writing
    # ~52 KB. A crash in that window leaves a blank catalog behind.
    write_json_atomically(DATASETS / "milestone" / "catalog.json", catalog.to_dict())

    stable = sum(1 for c in corroboration.values() if c["engine_independent"])
    print(f"engine-independent claims: {stable}/{len(corroboration)}")
    counts = Counter(cert.overall.value for cert in certificates)
    print(f"entries: {len(certificates)} | verdicts: {dict(counts)}")
    print(f"agreement: {report.agreements}/{report.total}")
    print(f"wrote {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
