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


def _tiny_fbc_sbml(*, objective_type: str = "maximize", objective_reaction: str = "v_out") -> str:
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
    flux_objective.setReaction(objective_reaction)
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


def test_an_objective_naming_a_reaction_the_model_lacks_is_refused() -> None:
    """Dropping the term leaves an objective that optimizes to zero and matches a reported zero."""
    with pytest.raises(ValueError, match="does not contain"):
        ingest_fbc_sbml(_tiny_fbc_sbml(objective_reaction="v_biomass"))


def _fbc_model(*, bound_value: str = 'value="1000"', extra: str = "", gpr: str = "") -> str:
    """A one-reaction fbc model, with hooks for the constructs these tests probe."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core"'
        ' xmlns:fbc="http://www.sbml.org/sbml/level3/version1/fbc/version2"'
        ' level="3" version="1" fbc:required="false"><model fbc:strict="false">'
        '<listOfCompartments><compartment id="c" constant="true"/></listOfCompartments>'
        '<listOfParameters>'
        f'<parameter id="ub" {bound_value} constant="true"/>'
        '<parameter id="lb" value="0" constant="true"/>'
        '</listOfParameters>'
        '<listOfSpecies>'
        '<species id="A" compartment="c" hasOnlySubstanceUnits="true" boundaryCondition="false"'
        ' constant="false"/>'
        '</listOfSpecies>'
        f'{gpr}'
        '<listOfReactions>'
        '<reaction id="R" reversible="false" fbc:lowerFluxBound="lb" fbc:upperFluxBound="ub">'
        '<listOfProducts><speciesReference species="A" stoichiometry="1" constant="true"/></listOfProducts>'
        '</reaction></listOfReactions>'
        f'{extra}'
        '<fbc:listOfObjectives fbc:activeObjective="obj">'
        '<fbc:objective fbc:id="obj" fbc:type="maximize">'
        '<fbc:listOfFluxObjectives>'
        '<fbc:fluxObjective fbc:reaction="R" fbc:coefficient="1"/>'
        '</fbc:listOfFluxObjectives></fbc:objective></fbc:listOfObjectives>'
        "</model></sbml>"
    )


def test_a_flux_bound_that_is_not_a_number_is_refused() -> None:
    """A NaN bound is dropped by the solver, so the constraint the artifact states disappears."""
    pytest.importorskip("libsbml")
    from reprolith import ingest_fbc_sbml

    with pytest.raises(ValueError, match="NaN"):
        ingest_fbc_sbml(_fbc_model(bound_value='value="NaN"'))


def test_a_construct_that_moves_a_flux_bound_is_refused() -> None:
    """An LP is a steady-state snapshot; a rule or event that moves a bound changes the program."""
    pytest.importorskip("libsbml")
    from reprolith import ingest_fbc_sbml

    with_rule = _fbc_model(
        extra='<listOfRules><assignmentRule variable="ub">'
              '<math xmlns="http://www.w3.org/1998/Math/MathML"><cn>3</cn></math>'
              "</assignmentRule></listOfRules>"
    )
    with pytest.raises(ValueError, match="cannot be ingested"):
        ingest_fbc_sbml(with_rule)


def test_a_gene_rule_naming_an_undeclared_product_is_refused() -> None:
    """Falling back to the raw id invents a gene, and it enters the deletion fingerprint as real."""
    pytest.importorskip("libsbml")
    from reprolith import ingest_fbc_sbml

    model = _fbc_model().replace(
        '<listOfProducts>',
        '<fbc:geneProductAssociation><fbc:geneProductRef fbc:geneProduct="gMISSING"/>'
        "</fbc:geneProductAssociation><listOfProducts>",
        1,
    )
    with pytest.raises(ValueError, match="does not "):
        ingest_fbc_sbml(model)
