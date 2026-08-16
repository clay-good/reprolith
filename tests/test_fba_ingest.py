"""SBML-fbc ingestion into the FBA oracle (spec: constraint-based-class).

Bridges a published constraint-based model to the oracle: parse fbc SBML -> solve. Needs both
the ``engine`` extra (python-libsbml with fbc) and the ``fba`` extra (scipy); skips without either.
"""

from __future__ import annotations

import pytest

libsbml = pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    flux_variability,
    ingest_fbc_sbml,
    reaction_essentiality,
    solve_objective,
)


def _tiny_fbc_sbml(*, objective_type: str = "maximize") -> str:
    """A minimal fbc-v2 model: v_in -> A -> v_out, v_in bounded to 8, objective on v_out.

    Built with libsbml itself so the ingest is validated against the library's own writer rather
    than hand-rolled XML.
    """
    ns = libsbml.SBMLNamespaces(3, 1, "fbc", 2)
    document = libsbml.SBMLDocument(ns)
    document.setPackageRequired("fbc", False)
    model = document.createModel()
    model.getPlugin("fbc").setStrict(True)

    compartment = model.createCompartment()
    compartment.setId("cell")
    compartment.setConstant(True)

    species = model.createSpecies()
    species.setId("A")
    species.setCompartment("cell")
    species.setBoundaryCondition(False)
    species.setHasOnlySubstanceUnits(True)
    species.setConstant(False)

    for pid, value in (("zero", 0.0), ("eight", 8.0), ("inf", float("inf"))):
        parameter = model.createParameter()
        parameter.setId(pid)
        parameter.setValue(value)
        parameter.setConstant(True)

    def reaction(rid: str, reactant: str | None, product: str | None, lb: str, ub: str) -> None:
        r = model.createReaction()
        r.setId(rid)
        r.setReversible(False)
        r.setFast(False)
        if reactant:
            ref = r.createReactant()
            ref.setSpecies(reactant)
            ref.setStoichiometry(1.0)
            ref.setConstant(True)
        if product:
            ref = r.createProduct()
            ref.setSpecies(product)
            ref.setStoichiometry(1.0)
            ref.setConstant(True)
        plugin = r.getPlugin("fbc")
        plugin.setLowerFluxBound(lb)
        plugin.setUpperFluxBound(ub)

    reaction("v_in", None, "A", "zero", "eight")
    reaction("v_out", "A", None, "zero", "inf")

    objective = model.getPlugin("fbc").createObjective()
    objective.setId("obj")
    objective.setType(objective_type)
    model.getPlugin("fbc").setActiveObjectiveId("obj")
    flux_objective = objective.createFluxObjective()
    flux_objective.setReaction("v_out")
    flux_objective.setCoefficient(1.0)

    return str(libsbml.writeSBMLToString(document))


def test_ingests_stoichiometry_bounds_and_objective() -> None:
    model = ingest_fbc_sbml(_tiny_fbc_sbml())
    assert model.species_ids == ("A",)
    assert model.reaction_ids == ("v_in", "v_out")
    assert model.stoichiometry == ((1.0, -1.0),)  # A produced by v_in, consumed by v_out
    assert model.objective == (0.0, 1.0)
    assert model.lower == (0.0, 0.0)
    assert model.upper == (8.0, None)  # v_out's infinite upper bound becomes unbounded


def test_ingested_model_solves_and_feeds_the_oracle() -> None:
    model = ingest_fbc_sbml(_tiny_fbc_sbml())
    optimum = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    assert optimum == pytest.approx(8.0)
    # The named-reaction helper lets a caller judge a specific flux by id.
    intervals = flux_variability(model.stoichiometry, model.objective, model.lower, model.upper)
    assert intervals[model.reaction_index("v_out")] == pytest.approx((8.0, 8.0))
    assert reaction_essentiality(
        model.stoichiometry, model.objective, model.lower, model.upper
    ) == frozenset({0, 1})


def test_minimize_objective_is_refused_not_solved_with_the_wrong_sign() -> None:
    # Merely negating the objective vector makes the flux distribution an equivalent maximization,
    # but the optimal VALUE the oracle returns is then negated too — so a reproducible minimize
    # model would be judged against the paper's un-negated optimum and certify as FAILED. Refuse it
    # (like other unsupported constructs) rather than hand back a wrong verdict.
    with pytest.raises(ValueError, match="only 'maximize' is supported"):
        ingest_fbc_sbml(_tiny_fbc_sbml(objective_type="minimize"))
