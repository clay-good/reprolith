"""Constraint-based self-validation against a known result (spec: constraint-based-class).

Reproduces the standard E. coli core model's published maximal growth rate through the real
ingest -> solve pathway. This is the constraint-based analogue of the PK/PD blind self-validation
set: a real published model whose optimum is independently known. Needs the ``engine`` extra
(python-libsbml with fbc) and the ``fba`` extra (scipy); skips without either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    FbaModel,
    flux_variability,
    gene_essentiality,
    ingest_fbc_sbml,
    reaction_essentiality,
    solve_objective,
)

_MODEL_PATH = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"

# The independently-established maximal growth rate of e_coli_core on its default medium
# (Orth, Fleming & Palsson 2010; BiGG). This is the ground truth, encoded nowhere in the engine.
_KNOWN_GROWTH_RATE = 0.873922
_BIOMASS = "R_BIOMASS_Ecoli_core_w_GAM"


@pytest.fixture(scope="module")
def model() -> FbaModel:
    return ingest_fbc_sbml(_MODEL_PATH.read_text(encoding="utf-8"))


def test_ingests_the_documented_structure(model: FbaModel) -> None:
    # e_coli_core is documented as 72 metabolites and 95 reactions.
    assert len(model.species_ids) == 72
    assert len(model.reaction_ids) == 95
    assert _BIOMASS in model.reaction_ids


def test_reproduces_the_known_growth_rate(model: FbaModel) -> None:
    optimum = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    assert optimum == pytest.approx(_KNOWN_GROWTH_RATE, abs=1e-4)


def test_the_full_oracle_runs_on_a_real_model(model: FbaModel) -> None:
    # The fingerprint analyses must run end to end on a real network, not just the tiny fixtures:
    # variability returns a well-formed interval per reaction, essentiality a reaction subset.
    intervals = flux_variability(
        model.stoichiometry, model.objective, model.lower, model.upper
    )
    assert len(intervals) == len(model.reaction_ids)
    for low, high in intervals:
        assert low <= high + 1e-6

    essential = reaction_essentiality(
        model.stoichiometry, model.objective, model.lower, model.upper
    )
    # The biomass reaction is essential by construction — deleting the objective abolishes it.
    assert model.reaction_index(_BIOMASS) in essential


def test_captures_gene_associations(model: FbaModel) -> None:
    # e_coli_core annotates 69 of its 95 reactions with a gene-protein-reaction rule over 137 genes;
    # the rest (exchanges, ATP maintenance, biomass) are spontaneous and carry none.
    assert len(model.gene_associations) == 69
    assert len(model.genes()) == 137


def test_reproduces_gene_essentiality(model: FbaModel) -> None:
    # Gene deletion via the GPR rules on the real network. Enolase (b2779) is an independently
    # known essential gene for aerobic growth on glucose — the non-circular anchor; the full set
    # is a small, deterministic subset of the 137 genes.
    essential = gene_essentiality(model)
    assert "b2779" in essential
    assert essential == frozenset(
        {"b0720", "b1136", "b1779", "b2415", "b2416", "b2779", "b2926"}
    )
