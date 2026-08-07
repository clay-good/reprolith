"""SBML reaction-network ingestion into the stochastic (SSA) class (spec: Stochastic dossier shape).

The stochastic counterpart of the FBA `ingest_fbc_sbml`: parse a standard SBML reaction network
into the species, reactions, and initial counts the Gillespie SSA runs. Needs the engine extra
(python-libsbml); the tests skip without it. The fixture is committed, so these exercise only the
read path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")

from reprolith import (  # noqa: E402
    Verdict,
    ensemble_final_counts,
    ingest_stochastic_sbml,
    judge_scalar,
    species_mean_variance,
)

_FIX = Path(__file__).parent / "fixtures"


def test_ingest_immigration_death_recovers_the_reactions() -> None:
    species, reactions, initial = ingest_stochastic_sbml(
        (_FIX / "immigration_death.xml").read_text(encoding="utf-8")
    )
    assert species == ["A"]
    assert initial == [0]
    assert len(reactions) == 2
    birth = next(r for r in reactions if not r.reactants)
    death = next(r for r in reactions if r.reactants)
    assert birth.rate == 10.0 and birth.products == ((0, 1),)
    assert death.rate == 1.0 and death.reactants == ((0, 1),) and death.products == ()


def test_ingested_network_reproduces_the_poisson_mean_end_to_end() -> None:
    species, reactions, initial = ingest_stochastic_sbml(
        (_FIX / "immigration_death.xml").read_text(encoding="utf-8")
    )
    ensemble = ensemble_final_counts(
        len(species), reactions, initial, duration=40.0, trajectories=400, seed=20260807
    )
    mean, _ = species_mean_variance(ensemble, species=0)
    # k/γ = 10/1 = 10 is the Poisson stationary mean; the ingested network reproduces it.
    verdict = judge_scalar(
        claim_id="A-mean", quantity="stationary mean", source_location="SBML network",
        reported=10.0, predicted=mean,
    )
    assert verdict.verdict is Verdict.REPRODUCED


def test_non_integer_initial_amount_is_rejected() -> None:
    import libsbml

    doc = libsbml.SBMLDocument(3, 2)
    model = doc.createModel()
    comp = model.createCompartment()
    comp.setId("c")
    comp.setConstant(True)
    comp.setSize(1.0)
    species = model.createSpecies()
    species.setId("A")
    species.setCompartment("c")
    species.setInitialAmount(2.5)  # not a whole molecule count
    species.setHasOnlySubstanceUnits(True)
    species.setBoundaryCondition(False)
    species.setConstant(False)
    with pytest.raises(ValueError, match="non-integer"):
        ingest_stochastic_sbml(libsbml.writeSBMLToString(doc))


def test_lint_stochastic_inline_verdict_and_mcp_registration() -> None:
    from reprolith import lint_stochastic
    from reprolith.mcp_server import TOOL_DEFINITIONS

    assert "lint_stochastic" in {t["name"] for t in TOOL_DEFINITIONS}
    result = lint_stochastic(
        (_FIX / "immigration_death.xml").read_text(encoding="utf-8"),
        species=0, reported_mean=10.0, duration=40.0, trajectories=400, seed=20260807,
    )
    assert result.verdict is Verdict.REPRODUCED
    assert result.method == "scalar-relative-error"
    assert result.scope.machine == "reproducible-not-correct-not-clinical"
