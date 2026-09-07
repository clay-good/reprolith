#!/usr/bin/env python3
"""Regenerate the constraint-based (FBA) milestone artifact from committed data.

The constraint-based counterpart of ``run_milestone.py``. Seeds the catalog with the constraint-
based entries whose reproducibility is independently known, certifies each *blind* through the
shared ``certify_constraint_based`` — the verdict path never sees the label — scores agreement with
ground truth on the same machinery the PK/PD run uses, and writes the walkable result.

The set is n=8: the E. coli core model, labelled by its documented maximal growth rate, plus seven
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
from reprolith.constraint_based import EssentialityClaim
from reprolith.corroboration import corroborate_objective
from reprolith.fba import EssentialKind, ReportedEssentialSet, solver_pin
from reprolith.mcp_server import write_json_atomically
from reprolith.persistence import dossier_from_dict, prune_certificate_directory

REPO = Path(__file__).resolve().parents[1]
CB = REPO / "datasets" / "constraint_based"
CROSS = CB / "cross_validation"
# The FROG fingerprint is portable, so a verdict here should not move with the LP backend — but the
# certificate still has to name the software that produced it, read from the installed scipy rather
# than asserted, so a third party knows what solved these programs.
PIN = solver_pin()


def _artifact_validates(sbml: str) -> bool:
    """Whether libSBML reads this artifact without a fatal error — measured, not asserted."""
    from reprolith.sbml import _libsbml

    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    return not any(
        document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        for i in range(document.getNumErrors())
    )


def _e_coli_core() -> tuple[Identifiers, GroundTruth, object, str]:
    """The E. coli core entry, labelled by its documented growth rate; dossier from the worked example."""
    identifiers = Identifiers(
        title="E. coli core metabolic model (Orth, Fleming & Palsson 2010)", accession="e_coli_core"
    )
    label = GroundTruth(
        expected=OverallVerdict.REPRODUCED,
        source=(
            "BiGG / Orth, Fleming & Palsson (2010): known maximal growth rate 0.873922; "
            "essential genes and reactions from COBRApy's single-deletion analysis"
        ),
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
        model=ModelArtifact(
            filename=f"{model_id}.xml.gz", detected_format="sbml-fbc",
            # Measured, not asserted — validate_constraint_based checks this flag as
            # evidence the adopted model validates, and estimate_difficulty reads it as
            # "a runnable model shipped". Writing True made both consume an assertion.
            validates=_artifact_validates(
                gzip.decompress((CROSS / f"{model_id}.xml.gz").read_bytes()).decode("utf-8")
            ),
        ),
        objective_claims=[DossierClaim(
            id=f"{model_id}-growth",
            quantity="maximal growth rate on the distributed medium",
            conditions="the model's distributed exchange bounds",
            # A `source_location` names where the reference VALUE came from — the claims dataset says
            # so in as many words: "A claim's reference value comes from the paper (cited in
            # source_location), not from re-running the model." For these entries it did not: the
            # reference was computed by an independent tool re-running this same model file, which is
            # what makes the cross-validation non-circular and is the whole point of the set. Citing
            # only the publication let a certificate read as a reproduction of the paper's own
            # published number, over its DOI, when a reader following that pointer would find no such
            # number. The tool is already recorded beside the reference; it travels with the claim now.
            source_location=(
                f"{record['source']} — reference value computed by {record['reference_tool']} "
                "re-running this model file, not a number read from the paper"
            ),
            reference_kind=ReferenceKind.NUMERIC,
            reference_data=(record["reference_growth"],),
        )],
        # The distributed model already carries its medium in its bounds; nothing to override.
        medium=(),
    )
    sbml = gzip.decompress((CROSS / f"{model_id}.xml.gz").read_bytes()).decode("utf-8")
    return identifiers, label, dossier, sbml


def _essentiality_claims(sbml: str) -> list[EssentialityClaim]:
    """The E. coli core deletion claims, against COBRApy's own committed essential sets.

    The class's second reproduction target beside the objective value, and the one a genome-scale
    paper validates against experimental knockouts. Both sets are the *independent tool's*, so the
    citation says so — the same disclosure every other reference in this milestone carries.

    The reaction ids need translating and the translation is *checked*: COBRApy strips the SBML
    ``R_`` prefix this package keeps, so a set aligned without knowing that reports all eighteen
    reactions as present on one side only — a naming convention read as a structural disagreement
    about the model, which is the trap the FROG comparison already had to learn once.
    """
    from reprolith import ingest_fbc_sbml

    reference = json.loads(
        (CROSS / "e_coli_core_essentiality.json").read_text(encoding="utf-8")
    )
    cited = (
        f"{reference['reference_tool']} single-deletion analysis of this model file — reference "
        "sets computed by that tool, not read from the paper"
    )
    # The sweep runs under the *dossier's* medium, as every claim on this certificate does — which
    # for this entry is the model's own distributed bounds, and those are what the reference tool
    # deleted against. An essential set is a property of the model and its bounds together, so two
    # sets taken under different media would disagree for a reason that is not the solver's.
    model = ingest_fbc_sbml(sbml)
    reactions = tuple(f"R_{r}" for r in reference["essential_reactions"])
    unknown = [r for r in reactions if r not in model.reaction_ids]
    if unknown:
        raise AssertionError(
            f"the reference names reactions this model does not have after prefixing: {unknown}"
        )
    genes = tuple(reference["essential_genes"])
    missing = [g for g in genes if g not in model.genes()]
    if missing:
        raise AssertionError(f"the reference names genes this model does not carry: {missing}")
    return [
        EssentialityClaim(
            claim_id="e_coli_core-essential-genes",
            quantity="the set of genes whose single deletion abolishes growth",
            reported=ReportedEssentialSet(kind=EssentialKind.GENES, ids=genes),
            source_location=cited,
        ),
        EssentialityClaim(
            claim_id="e_coli_core-essential-reactions",
            quantity="the set of reactions whose single knockout abolishes growth",
            reported=ReportedEssentialSet(kind=EssentialKind.REACTIONS, ids=reactions),
            source_location=cited,
        ),
    ]


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
            # Only for the small model: a deletion sweep is one LP per gene and per reaction, which
            # is a second and a half here and minutes on the genome-scale set. What the rest would
            # cost is a measurement rather than a silence — the same scoping the FROG fingerprint
            # is published under.
            essentiality=(
                _essentiality_claims(sbml) if identifiers.accession == "e_coli_core" else ()
            ),
        )

    certificates, report = run_test_set(
        catalog.entries, engine_pin=PIN, certified=certified, advance=True
    )

    milestone = CB / "milestone"
    milestone.mkdir(exist_ok=True)
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    certs = milestone / "certificates"
    certs.mkdir(exist_ok=True)
    prune_certificate_directory(certs, certified)
    for accession, cert in certified.items():
        (certs / f"{accession}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    # Atomic: this file is what both surfaces read at start-up and what a live MCP server
    # re-reads under its lock, and a plain write_text truncates it to zero before writing
    # ~52 KB. A crash in that window leaves a blank catalog behind.
    write_json_atomically(milestone / "catalog.json", catalog.to_dict())

    # Engine independence: the same model solved by COBRApy — a different reader and a different
    # LP backend — and compared on the objective *value*, which is the one quantity two correct
    # solvers must agree on when the flux vector that attains it is not unique. Written only when
    # COBRApy is installed, and this class published nothing at all until it was: an absent record
    # says "no second engine was asked", which the corroboration surface reports as unchecked
    # rather than as a pass.
    corroboration = {}
    for identifiers, _, _, sbml in specs:
        try:
            result = corroborate_objective(sbml)
        except ImportError:
            print("cobrapy is not installed; no corroboration written (install the "
                  "'corroborate' extra)")
            corroboration = {}
            break
        corroboration[identifiers.accession] = result.record()
    if corroboration:
        (milestone / "corroboration.json").write_text(
            json.dumps(corroboration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        stable = sum(1 for c in corroboration.values() if c["engine_independent"])
        print(f"engine-independent: {stable}/{len(corroboration)}")

    # The **FROG fingerprint** the class spec asks this class to generate — flux optimum, reaction
    # variability, objective, gene and reaction deletion — published beside the certificates, and
    # compared component by component against COBRApy's own. `frog_fingerprint` had computed one
    # since the class was written with nothing publishing or comparing it.
    #
    # For `e_coli_core` only, and the reason is measured rather than a preference: a fingerprint is
    # a couple of LPs per reaction plus one per gene, which is 0.8s on this 95-reaction model and
    # 145s on the 1226-reaction iEK1008 — so the genome-scale set would put half an hour on a
    # script that must be re-run after any change to the solver, the oracle or the verdict rule.
    # What is published is what a reader can check quickly; what it would cost to publish the rest
    # is stated rather than left as a silence.
    core = next((sbml for identifiers, _, _, sbml in specs
                 if identifiers.accession == "e_coli_core"), None)
    if core is not None and corroboration:
        from reprolith.corroboration import frog_agreement

        agreement = frog_agreement(core)
        frog_dir = milestone / "frog"
        frog_dir.mkdir(exist_ok=True)
        (frog_dir / "e_coli_core.json").write_text(
            json.dumps(agreement, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"FROG: {agreement['components_compared']} components agree with cobrapy to "
            f"{agreement['worst_difference_of_objective']:.1e} of the objective"
        )

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"entries: {len(certificates)} | verdicts: {dict(counts)}")
    print(f"agreement: {report.agreements}/{report.total}")
    print(f"wrote {(milestone / 'agreement_report.json').relative_to(REPO)}")


if __name__ == "__main__":
    main()
