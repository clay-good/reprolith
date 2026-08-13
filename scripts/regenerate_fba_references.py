#!/usr/bin/env python3
"""Regenerate the constraint-based cross-validation reference values from the committed models.

The cross-validation set's ground truth (``datasets/constraint_based/cross_validation/``) is what an
independent implementation — COBRApy — computes for each committed model. For a reproducibility
tool, that ground truth must itself be reproducible: this script regenerates all three reference
files from the models, so the committed numbers are auditable, not magic constants.

  - ``reference_growth.json``       — max growth on the distributed medium, per genome-scale model
  - ``e_coli_core_essentiality.json`` — essential genes and reactions (single-deletion)
  - ``e_coli_core_synthetic_lethal.json`` — synthetic-lethal reaction pairs (double-deletion)
  - ``e_coli_core_synthetic_lethal_genes.json`` — synthetic-lethal gene pairs (double gene deletion)
  - ``e_coli_core_fva.json``        — flux-variability interval per reaction at the optimum
  - ``iIT341_fva.json``             — the same, on a larger different-organism model (generality)
  - ``iIT341_synthetic_lethal.json``  — synthetic-lethal reaction pairs on a bounded iIT341 subset
  - ``e_coli_core_loopless_fva.json`` — loopless flux-variability interval per reaction at the optimum
  - ``e_coli_core_pfba.json``        — parsimonious-FBA total flux (min Σ|vᵢ|) at the optimum
  - ``e_coli_core_production_envelope.json`` — acetate-vs-growth production envelope (concave frontier)

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
    "iMM904": {"organism": "Saccharomyces cerevisiae S288C (eukaryote)",
               "reference": "doi:10.1186/1752-0509-3-37 (PMID 19321003)"},
    "iEK1008": {"organism": "Mycobacterium tuberculosis H37Rv",
                "reference": "doi:10.1186/s12918-018-0557-y (PMID 29499714)"},
    "iAF1260": {"organism": "Escherichia coli str. K-12 substr. MG1655 (2007 reconstruction)",
                "reference": "doi:10.1038/msb4100155 (PMID 17593909)"},
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


def _viable_singles(frame: object, floor: float) -> list[str]:
    return sorted(
        list(ids)[0]
        for ids, growth in zip(frame["ids"], frame["growth"])  # type: ignore[index]
        if growth is not None and growth == growth and growth >= floor
    )


def _lethal_pairs(frame: object, floor: float) -> list[list[str]]:
    pairs = []
    for ids, growth in zip(frame["ids"], frame["growth"]):  # type: ignore[index]
        members = sorted(ids)
        if len(members) != 2:
            continue
        if growth is None or growth != growth or growth < floor:
            pairs.append(members)
    return sorted(pairs)


def _synthetic_lethal_reactions(model: cobra.Model) -> list[list[str]]:
    """Synthetic-lethal reaction pairs from COBRApy double_reaction_deletion: both singly viable,
    lethal together. Restricts the pairwise sweep to the single-viable reactions (an essential
    reaction's pairs are lethal by itself, not synthetically), matching Reprolith's definition."""
    floor = 1e-6 * float(model.slim_optimize())
    viable = _viable_singles(cobra.flux_analysis.single_reaction_deletion(model, processes=1), floor)
    double = cobra.flux_analysis.double_reaction_deletion(model, reaction_list1=viable, processes=1)
    return _lethal_pairs(double, floor)


def _synthetic_lethal_reactions_subset(model: cobra.Model, n: int) -> dict:
    """Synthetic-lethal reaction pairs among the ``n`` lexicographically-smallest single-viable
    reactions — a bounded double-deletion sweep for a genome-scale model, where the full O(R²) sweep
    is too costly. The subset is stored explicitly so the check is reproducible and the same reaction
    set drives both the reference and Reprolith."""
    floor = 1e-6 * float(model.slim_optimize())
    viable = _viable_singles(cobra.flux_analysis.single_reaction_deletion(model, processes=1), floor)
    subset = sorted(viable)[:n]
    double = cobra.flux_analysis.double_reaction_deletion(model, reaction_list1=subset, processes=1)
    return {"subset": subset, "pairs": _lethal_pairs(double, floor)}


def _synthetic_lethal_genes(model: cobra.Model) -> list[list[str]]:
    """Synthetic-lethal gene pairs from COBRApy double_gene_deletion: both singly viable, lethal
    together. Same construction as the reaction version, restricted to single-viable genes."""
    floor = 1e-6 * float(model.slim_optimize())
    viable = _viable_singles(cobra.flux_analysis.single_gene_deletion(model, processes=1), floor)
    double = cobra.flux_analysis.double_gene_deletion(model, gene_list1=viable, processes=1)
    return _lethal_pairs(double, floor)


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

    _write(CROSS / "e_coli_core_synthetic_lethal.json", {
        "description": "Independent reference synthetic-lethal reaction pairs for e_coli_core, from "
                       "COBRApy double_reaction_deletion on the distributed medium: pairs viable to "
                       "delete singly but lethal together. Reprolith's synthetic_lethal_reactions "
                       "must match this set exactly — a non-circular cross-tool check of the "
                       "double-deletion (epistasis) analysis single deletion cannot reveal.",
        "reference_tool": tool,
        "pairs": _synthetic_lethal_reactions(core),
    })

    _write(CROSS / "e_coli_core_synthetic_lethal_genes.json", {
        "description": "Independent reference synthetic-lethal gene pairs for e_coli_core, from "
                       "COBRApy double_gene_deletion on the distributed medium: gene pairs viable to "
                       "delete singly but lethal together (through the model's GPR rules). "
                       "Reprolith's synthetic_lethal_genes must match this set exactly — a "
                       "non-circular cross-tool check of gene-level double deletion, the classic "
                       "synthetic-lethality screen single-gene deletion is blind to.",
        "reference_tool": tool,
        "pairs": _synthetic_lethal_genes(core),
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

    # FVA on a second, larger, different-organism model, so the variability code is cross-validated
    # beyond the 95-reaction core — proving it is not overfit to one small toy network.
    it341 = _load(CROSS / "iIT341.xml.gz")
    it341_fva = cobra.flux_analysis.flux_variability_analysis(
        it341, fraction_of_optimum=1.0, processes=1
    )
    _write(CROSS / "iIT341_fva.json", {
        "description": "Independent reference flux-variability intervals for iIT341 (H. pylori, 554 "
                       "reactions) at the optimum, from COBRApy flux_variability_analysis. Reprolith's "
                       "flux_variability must match these — the FROG variability component checked on "
                       "a model 6x the core's size and a different organism, not just the toy core.",
        "reference_tool": tool,
        "fraction_of_optimum": 1.0,
        "intervals": {
            cid: [_round(it341_fva.loc[cid]["minimum"]), _round(it341_fva.loc[cid]["maximum"])]
            for cid in sorted(it341_fva.index)
        },
    })

    it341_sl = _synthetic_lethal_reactions_subset(it341, 45)
    _write(CROSS / "iIT341_synthetic_lethal.json", {
        "description": "Independent reference synthetic-lethal reaction pairs for iIT341 (H. pylori, "
                       "554 reactions) among the 45 smallest single-viable reactions, from COBRApy "
                       "double_reaction_deletion. A bounded double-deletion sweep on a second, larger, "
                       "different-organism model, so Reprolith's synthetic_lethal_reactions is shown to "
                       "generalize beyond the 95-reaction E. coli core — not just to reproduce one "
                       "small network's epistasis.",
        "reference_tool": tool,
        "subset": it341_sl["subset"],
        "pairs": it341_sl["pairs"],
    })

    loopless = cobra.flux_analysis.flux_variability_analysis(
        core, fraction_of_optimum=1.0, loopless=True, processes=1
    )
    _write(CROSS / "e_coli_core_loopless_fva.json", {
        "description": "Independent reference *loopless* flux-variability intervals for e_coli_core "
                       "at the optimum, from COBRApy flux_variability_analysis(loopless=True). These "
                       "differ from the plain FVA reference exactly on reactions inflated by "
                       "thermodynamically infeasible internal loops (e.g. FRD7/SUCDi). Reprolith's "
                       "loopless_flux_variability must match these — a non-circular cross-tool check "
                       "of the loop-law MILP against COBRApy's independent implementation.",
        "reference_tool": tool,
        "fraction_of_optimum": 1.0,
        "intervals": {
            cid: [_round(loopless.loc[cid]["minimum"]), _round(loopless.loc[cid]["maximum"])]
            for cid in sorted(loopless.index)
        },
    })

    pfba = cobra.flux_analysis.pfba(core)
    _write(CROSS / "e_coli_core_pfba.json", {
        "description": "Independent reference parsimonious-FBA result for e_coli_core, from COBRApy "
                       "pfba. total_flux is the minimized Σ|vᵢ| holding the objective optimal — the "
                       "uniquely-defined pFBA quantity (individual fluxes can differ among alternate "
                       "optima, so only the total and the preserved objective are cross-checked). "
                       "Reprolith's parsimonious_fluxes must reproduce both.",
        "reference_tool": tool,
        "total_flux": _round(float(pfba.fluxes.abs().sum())),
        "objective_value": _round(float(core.slim_optimize())),
    })

    # Production envelope: acetate secretion (the textbook overflow byproduct) versus growth. Grid
    # over the biomass objective, min/max acetate at each level — the classic concave frontier.
    target, points = "EX_ac_e", 20
    biomass = [r.id for r in core.reactions if r.objective_coefficient != 0][0]
    env = cobra.flux_analysis.production_envelope(core, [biomass], objective=target, points=points)
    _write(CROSS / "e_coli_core_production_envelope.json", {
        "description": "Independent reference production envelope for e_coli_core from COBRApy "
                       "production_envelope: the min/max acetate secretion (EX_ac_e) at each growth "
                       "level, swept over the biomass objective. Reprolith's production_envelope must "
                       "reproduce the whole concave frontier — a cross-tool check of the phenotypic "
                       "phase plane, not a single point.",
        "reference_tool": tool,
        "target": target,
        "objective": biomass,
        "points": points,
        "envelope": [
            [_round(g), _round(lo), _round(hi)]
            for g, lo, hi in zip(env[biomass], env["flux_minimum"], env["flux_maximum"])
        ],
    })


if __name__ == "__main__":
    main()
