#!/usr/bin/env python3
"""Regenerate the constraint-based cross-validation reference values from the committed models.

The cross-validation set's ground truth (``datasets/constraint_based/cross_validation/``) is what an
independent implementation — COBRApy — computes for each committed model. For a reproducibility
tool, that ground truth must itself be reproducible: this script regenerates all three reference
files from the models, so the committed numbers are auditable, not magic constants.

  - ``reference_growth.json``       — max growth on the distributed medium, per genome-scale model
  - ``e_coli_core_essentiality.json`` — essential genes and reactions (single-deletion)
  - ``e_coli_core_fva.json``        — flux-variability interval per reaction at the optimum

Needs COBRApy (``pip install cobra``) — a dev-time reference generator, not a Reprolith runtime
dependency. Deterministic: re-running produces byte-identical files. Run from the repo root:

    python scripts/regenerate_fba_references.py
"""

from __future__ import annotations

import gzip
import io
import json
import warnings
from pathlib import Path

import cobra

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
CB = REPO / "datasets" / "constraint_based"
CROSS = CB / "cross_validation"

# Genome-scale cross-validation models and their source publications (BiGG accession -> metadata).
_GENOME_SCALE = {
    "iIT341": {"organism": "Helicobacter pylori 26695",
               "reference": "doi:10.1128/JB.187.16.5818-5830.2005 (PMID 16077130)"},
    "iLJ478": {"organism": "Thermotoga maritima MSB8",
               "reference": "doi:10.1101/gr.234503 (PMID 14718003)"},
    "iNF517": {"organism": "Lactococcus lactis subsp. cremoris MG1363",
               "reference": "doi:10.1128/AEM.00113-13 (PMID 23974059)"},
    "iJO1366": {"organism": "Escherichia coli str. K-12 substr. MG1655 (genome-scale)",
                "reference": "doi:10.1038/msb.2011.65 (PMID 21988831)"},
}


def _load(path: Path) -> cobra.Model:
    xml = gzip.decompress(path.read_bytes()).decode("utf-8") if path.suffix == ".gz" else path.read_text()
    return cobra.io.read_sbml_model(io.StringIO(xml))


def _essential(frame: object) -> list[str]:
    return sorted(
        list(ids)[0]
        for ids, growth in zip(frame["ids"], frame["growth"])  # type: ignore[index]
        if growth is None or growth != growth or growth < 1e-6
    )


def _round(value: float) -> float:
    # Normalize signed zero so regeneration is byte-stable (an LP can return -0.0 for a hard 0).
    rounded = round(float(value), 9)
    return 0.0 if rounded == 0.0 else rounded


def _write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=path.name == "reference_growth.json") + "\n")
    print(f"wrote {path.relative_to(REPO)}")


def main() -> None:
    tool = f"COBRApy {cobra.__version__}"

    growth_models = {}
    for model_id, meta in _GENOME_SCALE.items():
        model = _load(CROSS / f"{model_id}.xml.gz")
        growth_models[model_id] = {
            "organism": meta["organism"],
            "source": f"BiGG Models http://bigg.ucsd.edu/models/{model_id} ; {meta['reference']}",
            "reference_growth": float(model.slim_optimize()),
            "reference_tool": f"{tool} slim_optimize on the model's distributed medium",
            "reactions": len(model.reactions),
            "metabolites": len(model.metabolites),
            "genes": len(model.genes),
        }
    _write(CROSS / "reference_growth.json", {
        "description": "Cross-validation set: Reprolith's ingest_fbc_sbml + solver must reproduce "
                       "the growth rate the independent COBRApy implementation computes for each "
                       "model's distributed medium. Non-circular (a different implementation is the "
                       "reference) and it validates ingestion on structurally diverse real models.",
        "models": growth_models,
    })

    core = _load(CB / "e_coli_core.xml")
    _write(CROSS / "e_coli_core_essentiality.json", {
        "description": "Independent reference essential sets for e_coli_core, computed by COBRApy "
                       "single_gene_deletion / single_reaction_deletion on the distributed medium. "
                       "Reprolith's gene_essentiality and reaction_essentiality must match these — a "
                       "non-circular cross-tool check of the deletion analyses (incl. GPR AND/OR logic).",
        "reference_tool": tool,
        "essential_genes": _essential(cobra.flux_analysis.single_gene_deletion(core, processes=1)),
        "essential_reactions": _essential(
            cobra.flux_analysis.single_reaction_deletion(core, processes=1)
        ),
    })

    fva = cobra.flux_analysis.flux_variability_analysis(core, fraction_of_optimum=1.0, processes=1)
    _write(CROSS / "e_coli_core_fva.json", {
        "description": "Independent reference flux-variability intervals for e_coli_core at the "
                       "optimum, from COBRApy flux_variability_analysis (fraction_of_optimum=1.0). "
                       "Reprolith's flux_variability must match these — the third FROG component.",
        "reference_tool": tool,
        "fraction_of_optimum": 1.0,
        "intervals": {
            cid: [_round(fva.loc[cid]["minimum"]), _round(fva.loc[cid]["maximum"])]
            for cid in sorted(fva.index)
        },
    })


if __name__ == "__main__":
    main()
