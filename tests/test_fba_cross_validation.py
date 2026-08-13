"""Cross-validation: Reprolith reproduces an independent tool's result on diverse real models.

The E. coli core self-validation checks one small model against one documented number. This checks
that ``ingest_fbc_sbml`` + the solver reproduce, on several structurally diverse genome-scale
models (different organisms, 500-750 reactions), the growth rate the community-standard COBRApy
computes for each model's distributed medium. The reference values were produced by COBRApy (a
*different* implementation) and committed to ``reference_growth.json``, so this is a genuine
non-circular reproduction — and it exercises the ingester on far more structural variety than the
single core model, where a stoichiometry-, bound-, or objective-parsing bug would surface as a
disagreement.

Needs the ``engine`` (python-libsbml with fbc) and ``fba`` (scipy) extras — but *not* COBRApy,
which only generated the committed reference. Skips without them.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    flux_variability,
    gene_essentiality,
    ingest_fbc_sbml,
    loopless_flux_variability,
    parsimonious_fluxes,
    production_envelope,
    reaction_essentiality,
    solve_objective,
    synthetic_lethal_genes,
    synthetic_lethal_reactions,
)

_DIR = Path(__file__).parent.parent / "datasets" / "constraint_based" / "cross_validation"
_REFERENCE = json.loads((_DIR / "reference_growth.json").read_text(encoding="utf-8"))["models"]
_CORE = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
_ESSENTIALITY = json.loads((_DIR / "e_coli_core_essentiality.json").read_text(encoding="utf-8"))
_SYNTHETIC_LETHAL = json.loads(
    (_DIR / "e_coli_core_synthetic_lethal.json").read_text(encoding="utf-8")
)
_SYNTHETIC_LETHAL_GENES = json.loads(
    (_DIR / "e_coli_core_synthetic_lethal_genes.json").read_text(encoding="utf-8")
)
_FVA = json.loads((_DIR / "e_coli_core_fva.json").read_text(encoding="utf-8"))
_LOOPLESS_FVA = json.loads((_DIR / "e_coli_core_loopless_fva.json").read_text(encoding="utf-8"))
_PFBA = json.loads((_DIR / "e_coli_core_pfba.json").read_text(encoding="utf-8"))
_ENVELOPE = json.loads(
    (_DIR / "e_coli_core_production_envelope.json").read_text(encoding="utf-8")
)
_IT341_FVA = json.loads((_DIR / "iIT341_fva.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("model_id", sorted(_REFERENCE))
def test_reprolith_reproduces_the_reference_growth(model_id: str) -> None:
    record = _REFERENCE[model_id]
    sbml = gzip.decompress((_DIR / f"{model_id}.xml.gz").read_bytes()).decode("utf-8")
    model = ingest_fbc_sbml(sbml)

    # Ingestion recovered the documented structure, so a parsing error can't hide as a coincidence.
    assert len(model.reaction_ids) == record["reactions"]
    assert len(model.species_ids) == record["metabolites"]

    optimum = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    assert optimum == pytest.approx(record["reference_growth"], rel=1e-5)


def test_essentiality_matches_the_cobra_reference_on_e_coli_core() -> None:
    # The deletion analyses — gene essentiality (with its GPR AND/OR logic) and reaction
    # essentiality — must recover exactly the sets COBRApy's independent single-deletion analysis
    # finds. A cross-tool check of the most intricate new code, not a self-asserted number.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))

    assert set(gene_essentiality(model)) == set(_ESSENTIALITY["essential_genes"])

    essential_indices = reaction_essentiality(
        model.stoichiometry, model.objective, model.lower, model.upper
    )
    # Reprolith reaction ids carry the SBML "R_" prefix; COBRApy's do not.
    essential_reactions = {
        model.reaction_ids[i].removeprefix("R_") for i in essential_indices
    }
    assert essential_reactions == set(_ESSENTIALITY["essential_reactions"])


def test_synthetic_lethal_pairs_match_the_cobra_reference_on_e_coli_core() -> None:
    # Double-deletion (epistasis): the synthetic-lethal reaction pairs — viable to delete singly but
    # lethal together — must match, pair for pair, the set COBRApy's double_reaction_deletion finds.
    # A cross-tool check of an analysis single deletion is blind to, over the whole ~2900-pair sweep.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))
    pairs = synthetic_lethal_reactions(
        model.stoichiometry, model.objective, model.lower, model.upper
    )
    # Reprolith reaction ids carry the SBML "R_" prefix; COBRApy's do not.
    computed = {
        frozenset(model.reaction_ids[i].removeprefix("R_") for i in pair) for pair in pairs
    }
    reference = {frozenset(pair) for pair in _SYNTHETIC_LETHAL["pairs"]}
    assert reference  # the reference is non-trivial, so equality is a real check
    assert computed == reference


def test_synthetic_lethal_genes_match_the_cobra_reference_on_e_coli_core() -> None:
    # The gene-level double deletion: synthetic-lethal gene pairs — viable to delete singly but
    # lethal together through the model's GPR rules — must match COBRApy's double_gene_deletion
    # pair-for-pair. Exercises the GPR AND/OR logic under paired deletion, not just single.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))
    computed = {frozenset(pair) for pair in synthetic_lethal_genes(model)}
    reference = {frozenset(pair) for pair in _SYNTHETIC_LETHAL_GENES["pairs"]}
    assert reference  # the reference is non-trivial, so equality is a real check
    assert computed == reference


def test_flux_variability_matches_the_cobra_reference_on_e_coli_core() -> None:
    # The third FROG component: every reaction's flux-variability interval at the optimum must
    # match COBRApy's independent flux_variability_analysis, so the whole fingerprint (objective,
    # variability, deletions) is cross-validated against the standard tool, not just the objective.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))
    intervals = flux_variability(
        model.stoichiometry, model.objective, model.lower, model.upper,
        fraction_of_optimum=_FVA["fraction_of_optimum"],
    )
    reference = _FVA["intervals"]
    for reaction_id, (low, high) in zip(model.reaction_ids, intervals):
        ref_low, ref_high = reference[reaction_id.removeprefix("R_")]
        assert low == pytest.approx(ref_low, abs=1e-6)
        assert high == pytest.approx(ref_high, abs=1e-6)


def test_flux_variability_matches_the_cobra_reference_on_a_larger_model() -> None:
    # FVA is otherwise cross-validated only on the 95-reaction core. Repeat it on iIT341 (H. pylori,
    # 554 reactions, a different organism) so the variability code is shown to generalize beyond one
    # small toy network — a bug that only bites at scale or on other stoichiometries surfaces here.
    sbml = gzip.decompress((_DIR / "iIT341.xml.gz").read_bytes()).decode("utf-8")
    model = ingest_fbc_sbml(sbml)
    intervals = flux_variability(
        model.stoichiometry, model.objective, model.lower, model.upper,
        fraction_of_optimum=_IT341_FVA["fraction_of_optimum"],
    )
    reference = _IT341_FVA["intervals"]
    for reaction_id, (low, high) in zip(model.reaction_ids, intervals):
        ref_low, ref_high = reference[reaction_id.removeprefix("R_")]
        assert low == pytest.approx(ref_low, abs=1e-6)
        assert high == pytest.approx(ref_high, abs=1e-6)


def test_loopless_flux_variability_matches_the_cobra_reference_on_e_coli_core() -> None:
    # Reprolith's loop-law MILP must reproduce COBRApy's independent loopless FVA
    # (flux_variability_analysis(loopless=True)) reaction-for-reaction — a non-circular cross-tool
    # check that the loop removal is *correct*, not merely self-consistent.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))
    intervals = loopless_flux_variability(
        model.stoichiometry, model.objective, model.lower, model.upper,
        fraction_of_optimum=_LOOPLESS_FVA["fraction_of_optimum"],
    )
    reference = _LOOPLESS_FVA["intervals"]
    for reaction_id, (low, high) in zip(model.reaction_ids, intervals):
        ref_low, ref_high = reference[reaction_id.removeprefix("R_")]
        assert low == pytest.approx(ref_low, abs=1e-6)
        assert high == pytest.approx(ref_high, abs=1e-6)

    # The reference must genuinely differ from plain FVA, or the test would pass trivially: the
    # FRD7/SUCDi loop reactions are the ones removed, so their loopless interval is strictly tighter.
    for loop_reaction in ("SUCDi", "FRD7"):
        plain_low, plain_high = _FVA["intervals"][loop_reaction]
        loopless_low, loopless_high = reference[loop_reaction]
        assert (plain_high - plain_low) - (loopless_high - loopless_low) > 100.0


def test_parsimonious_flux_matches_the_cobra_reference_on_e_coli_core() -> None:
    # pFBA's minimized total flux Σ|vᵢ| is uniquely defined (unlike the individual fluxes, which can
    # differ among alternate optima across solvers), so Reprolith's parsimonious_fluxes must
    # reproduce COBRApy's pfba total flux — and preserve the growth optimum — reaction-set aside.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))
    solution = parsimonious_fluxes(model.stoichiometry, model.objective, model.lower, model.upper)
    assert solution.total_flux == pytest.approx(_PFBA["total_flux"], rel=1e-6)
    assert solution.objective_value == pytest.approx(_PFBA["objective_value"], rel=1e-6)


def test_production_envelope_matches_the_cobra_reference_on_e_coli_core() -> None:
    # The acetate-vs-growth production envelope must reproduce COBRApy's production_envelope point
    # for point — the whole concave frontier, not a single objective value. A non-circular
    # cross-tool check of the phenotypic phase plane against the community-standard implementation.
    model = ingest_fbc_sbml(_CORE.read_text(encoding="utf-8"))
    target = model.reaction_index("R_" + _ENVELOPE["target"])
    envelope = production_envelope(
        model.stoichiometry, model.objective, model.lower, model.upper,
        target=target, points=_ENVELOPE["points"],
    )
    reference = _ENVELOPE["envelope"]
    assert len(envelope.growth) == len(reference)
    for (growth, lo, hi), (ref_growth, ref_lo, ref_hi) in zip(
        zip(envelope.growth, envelope.target_min, envelope.target_max), reference
    ):
        assert growth == pytest.approx(ref_growth, abs=1e-6)
        assert lo == pytest.approx(ref_lo, abs=1e-6)
        assert hi == pytest.approx(ref_hi, abs=1e-6)
