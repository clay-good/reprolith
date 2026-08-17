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


def _single_reactant_model(rate_math: str) -> str:
    """An ``S -> P`` reaction whose single-parameter kinetic law is ``rate_math`` (parameter ``k``)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1"><model>'
        '<listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>'
        '<listOfSpecies>'
        '<species id="S" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"'
        ' boundaryCondition="false" constant="false"/>'
        '<species id="P" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"'
        ' boundaryCondition="false" constant="false"/>'
        '</listOfSpecies>'
        '<listOfReactions><reaction id="R" reversible="false">'
        '<listOfReactants><speciesReference species="S" stoichiometry="1" constant="true"/></listOfReactants>'
        '<listOfProducts><speciesReference species="P" stoichiometry="1" constant="true"/></listOfProducts>'
        '<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        f"{rate_math}"
        '</math><listOfLocalParameters><localParameter id="k" value="0.5"/></listOfLocalParameters>'
        '</kineticLaw></reaction></listOfReactions></model></sbml>'
    )


def test_single_parameter_non_mass_action_law_is_refused_not_coerced() -> None:
    # A constant-flux law over a consumed reactant carries exactly one parameter, so a
    # parameter-count check alone would read it as mass action k*S and run a fabricated propensity.
    # The structural check refuses it.
    constant_flux = _single_reactant_model("<ci>k</ci>")
    with pytest.raises(ValueError, match="not mass action"):
        ingest_stochastic_sbml(constant_flux)

    inhibition = _single_reactant_model(
        "<apply><divide/><ci>k</ci><apply><plus/><cn>1</cn><ci>S</ci></apply></apply>"
    )
    with pytest.raises(ValueError, match="not mass action"):
        ingest_stochastic_sbml(inhibition)

    # The genuine mass-action form for the same reaction is accepted, rate read from the parameter.
    mass_action = _single_reactant_model("<apply><times/><ci>k</ci><ci>S</ci></apply>")
    _, reactions, _ = ingest_stochastic_sbml(mass_action)
    assert len(reactions) == 1
    assert reactions[0].rate == 0.5 and reactions[0].reactants == ((0, 1),)


def _dimerization_model(reactants_xml: str, rate_math: str) -> str:
    """A ``2X -> Y`` reaction whose reactant side is written as ``reactants_xml``."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1"><model>'
        '<listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>'
        '<listOfSpecies>'
        '<species id="X" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"'
        ' boundaryCondition="false" constant="false"/>'
        '<species id="Y" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"'
        ' boundaryCondition="false" constant="false"/>'
        '</listOfSpecies>'
        '<listOfReactions><reaction id="R" reversible="false">'
        f"<listOfReactants>{reactants_xml}</listOfReactants>"
        '<listOfProducts><speciesReference species="Y" stoichiometry="1" constant="true"/></listOfProducts>'
        '<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        f"{rate_math}"
        '</math><listOfLocalParameters><localParameter id="k" value="0.01"/></listOfLocalParameters>'
        '</kineticLaw></reaction></listOfReactions></model></sbml>'
    )


def test_a_repeated_reactant_reference_ingests_at_the_same_order_as_a_stoichiometry() -> None:
    # SBML lets 2X be written either as one reference with stoichiometry 2 or as two separate
    # references. Reading the references one by one gave the second encoding two first-order terms
    # (k*n*n, consuming X twice per firing, so counts could go negative) while the mass-action
    # check — which aggregates — passed the model. Both encodings must ingest identically.
    squared = "<apply><times/><ci>k</ci><ci>X</ci><ci>X</ci></apply>"
    aggregated = _dimerization_model(
        '<speciesReference species="X" stoichiometry="2" constant="true"/>', squared
    )
    repeated = _dimerization_model(
        '<speciesReference species="X" stoichiometry="1" constant="true"/>'
        '<speciesReference species="X" stoichiometry="1" constant="true"/>',
        squared,
    )
    _, from_aggregated, _ = ingest_stochastic_sbml(aggregated)
    _, from_repeated, _ = ingest_stochastic_sbml(repeated)
    assert from_aggregated[0].reactants == ((0, 2),)
    assert from_repeated == from_aggregated

    # And the propensity is the dimerization form n(n-1)/2, never n*n — at the stochastic rate
    # constant, which is the file's k times 2! so that the sampler tracks the law the file states
    # (dX/dt = -2k·X²) rather than half of it.
    assert from_repeated[0].propensity([4, 0]) == pytest.approx(2 * 0.01 * 6)
    assert from_repeated[0].propensity([1, 0]) == 0.0


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


def test_constructs_the_ssa_cannot_represent_are_refused_not_dropped() -> None:
    """Each of these changes what the model does; ingesting the reactions alone runs a different one."""
    header = (
        '<?xml version="1.0"?>'
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">'
        '<model id="m">'
        '<listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>'
    )
    math_ns = 'xmlns="http://www.w3.org/1998/Math/MathML"'

    def species(boundary: str = "false", substance_units: str = "true") -> str:
        return (
            "<listOfSpecies>"
            f'<species id="S" compartment="c" initialAmount="100" '
            f'hasOnlySubstanceUnits="{substance_units}" boundaryCondition="{boundary}" constant="false"/>'
            '<species id="P" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true" '
            'boundaryCondition="false" constant="false"/>'
            "</listOfSpecies>"
        )

    reaction = (
        '<listOfReactions><reaction id="R" reversible="false">'
        '<listOfReactants><speciesReference species="S" stoichiometry="1" constant="true"/></listOfReactants>'
        '<listOfProducts><speciesReference species="P" stoichiometry="1" constant="true"/></listOfProducts>'
        f"<kineticLaw><math {math_ns}><apply><times/><ci>k</ci><ci>S</ci></apply></math>"
        '<listOfLocalParameters><localParameter id="k" value="0.1"/></listOfLocalParameters>'
        "</kineticLaw></reaction></listOfReactions>"
    )
    tail = "</model></sbml>"

    # A boundary species is held fixed by SBML; this SSA would deplete it.
    with pytest.raises(ValueError, match="boundary or constant species"):
        ingest_stochastic_sbml(header + species(boundary="true") + reaction + tail)
    # Concentration semantics would misread every rate law that scales with volume.
    with pytest.raises(ValueError, match="concentration units"):
        ingest_stochastic_sbml(header + species(substance_units="false") + reaction + tail)
    # An initial assignment overrides the stated initial amount.
    assignment = (
        '<listOfInitialAssignments><initialAssignment symbol="S">'
        f"<math {math_ns}><cn>500</cn></math>"
        "</initialAssignment></listOfInitialAssignments>"
    )
    with pytest.raises(ValueError, match="initialAssignment"):
        ingest_stochastic_sbml(header + species() + assignment + reaction + tail)
    # An event is how a PK/PD model doses — the single most load-bearing element it has.
    event = (
        '<listOfEvents><event id="e" useValuesFromTriggerTime="true">'
        f'<trigger initialValue="false" persistent="true"><math {math_ns}><true/></math></trigger>'
        '<listOfEventAssignments><eventAssignment variable="S">'
        f"<math {math_ns}><cn>1000</cn></math>"
        "</eventAssignment></listOfEventAssignments></event></listOfEvents>"
    )
    with pytest.raises(ValueError, match="events"):
        ingest_stochastic_sbml(header + species() + reaction + event + tail)

    # The same network without any of them still ingests.
    names, reactions, initial = ingest_stochastic_sbml(header + species() + reaction + tail)
    assert names == ["S", "P"] and initial == [100, 0] and len(reactions) == 1


def test_a_reactant_stoichiometry_above_one_carries_its_factorial_into_the_propensity() -> None:
    """The artifact states a deterministic constant; the SSA needs the stochastic one.

    For `2A -> B` under the law `k·A²`, the mean-field decay is `dA/dt = -2k·A²`, while the SSA's
    propensity for a stoichiometry of two is `c·n(n-1)/2`. The two describe the same reaction only
    when `c = 2k`. Ingesting `k` unchanged ran the sampler at half the rate the law it had just
    verified prescribes — the file said one model and the ensemble reproduced another.
    """
    import statistics

    from reprolith.stochastic import ensemble_final_counts

    k, initial_a, duration = 0.001, 200, 1.0
    model = _dimerization_model(
        '<speciesReference species="X" stoichiometry="2" constant="true"/>',
        "<apply><times/><ci>k</ci><apply><power/><ci>X</ci><cn type=\"integer\">2</cn></apply></apply>",
    ).replace('value="0.01"', f'value="{k}"').replace('initialAmount="100"', f'initialAmount="{initial_a}"')
    names, reactions, initial = ingest_stochastic_sbml(model)
    assert reactions[0].rate == pytest.approx(2 * k)  # k · 2! for the two-X reactant

    ensemble = ensemble_final_counts(
        len(names), reactions, initial, duration=duration, trajectories=2000, seed=7
    )
    mean = statistics.fmean(counts[0] for counts in ensemble)
    stated = initial_a / (1 + 2 * k * initial_a * duration)  # the artifact's own law
    misread = initial_a / (1 + k * initial_a * duration)  # what ingesting k unchanged gave
    assert abs(mean - stated) < abs(mean - misread)
    assert mean == pytest.approx(stated, rel=0.02)


def test_a_species_declared_in_moles_is_refused() -> None:
    """The SSA counts molecules; 100 mol read as 100 molecules is a different system entirely."""
    model = _dimerization_model(
        '<speciesReference species="X" stoichiometry="2" constant="true"/>',
        "<apply><times/><ci>k</ci><apply><power/><ci>X</ci><cn type=\"integer\">2</cn></apply></apply>",
    ).replace('id="X" compartment="c"', 'id="X" substanceUnits="mole" compartment="c"', 1)
    with pytest.raises(ValueError, match="substance units"):
        ingest_stochastic_sbml(model)
