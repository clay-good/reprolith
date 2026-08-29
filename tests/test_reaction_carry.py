"""Carrying a reaction network through the dossier (bootstrap task 2.1).

The largest thing ingestion read past. A reaction-based model's laws of motion live in its
reactions, and the dossier recorded none of them: a ten-reaction cascade produced eight state
variables, no equations, and a `reaction network` gap saying so. A model rebuilt from that dossier
did not move.

They are carried in the form the artifact states them — a stoichiometry and a rate law — rather
than derived into ODEs, because the derivation is a semantic choice (concentration or amount,
which compartment divides what) the artifact did not make. The proof is a round trip: ingest,
rebuild, run both under the same engine, compare.

Needs the `engine` extra for the round trips; the refusal tests need only libSBML.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

from reprolith import build_model_sbml, ingest_sbml  # noqa: E402

_KINETIC = Path(__file__).parent.parent / "datasets" / "kinetic"
_WORKED = Path(__file__).parent.parent / "datasets" / "worked_examples"


def _round_trip(source: str, *, duration: float, steps: int) -> float:
    """The worst relative difference between the artifact and a model rebuilt from its dossier."""
    from reprolith.engine import simulate

    dossier = ingest_sbml(source, entry="x")
    assert dossier.reactions, "this model's reactions were not carried"
    rebuilt = build_model_sbml(dossier)
    worst = 0.0
    for name in dossier.state_variables:
        original = simulate(source, name, duration=duration, steps=steps)[1][-1]
        after = simulate(rebuilt, name, duration=duration, steps=steps)[1][-1]
        worst = max(worst, abs(original - after) / max(1e-9, abs(original)))
    return worst


def test_a_ten_reaction_cascade_rebuilds_as_itself() -> None:
    """Kholodenko's MAPK cascade: the model the `reaction network` gap was written about."""
    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    source = (_KINETIC / "BIOMD0000000010.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(source, entry="BIOMD0000000010")
    assert len(dossier.reactions) == 10
    assert not [g for g in dossier.gaps if g.element == "reaction network"]
    assert _round_trip(source, duration=100.0, steps=50) < 1e-12  # measured 7.5e-15


def test_a_model_whose_reactions_and_rules_both_matter_rebuilds_too() -> None:
    """The repressilator: twelve reactions *and* nine assignment rules, carried together.

    The residual is integration, not a difference in the model. Measured: 1.4e-9 at t=0.01, 1.2e-7
    at t=1, 1.1e-6 at t=50 — it grows with the run, which is what integration error does and what a
    changed rate law does not. CVODE takes slightly different steps through two files whose
    element order differs, and this is a stiff oscillator. Asserted at both ends, so a real change
    in the math cannot hide inside a tolerance chosen for the long run. The MAPK cascade, which is
    not oscillatory, comes back at 7.5e-15 over a hundred time units.
    """
    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    source = (_KINETIC / "BIOMD0000000012.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(source, entry="BIOMD0000000012")
    assert len(dossier.reactions) == 12
    assert len([e for e in dossier.equations]) == 9  # the rules are carried as before
    assert _round_trip(source, duration=0.01, steps=2) < 1e-8
    assert _round_trip(source, duration=50.0, steps=50) < 1e-5


def test_a_local_parameter_stays_local_when_it_shadows_a_global() -> None:
    """SBML lets a kinetic law's own parameter shadow a global; hoisting one changes the model.

    `k` is 1000 globally and 2 inside the reaction, so a rebuild that lost the distinction runs
    five hundred times too fast — and every file involved stays valid.
    """
    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    from reprolith.engine import simulate

    source = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="shadow">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialAmount="10" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
      <species id="B" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="1000" constant="true"/></listOfParameters>
    <listOfReactions>
      <reaction id="J0" reversible="false">
        <listOfReactants>
          <speciesReference species="A" stoichiometry="1" constant="true"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="B" stoichiometry="1" constant="true"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><times/><ci>k</ci><ci>A</ci></apply>
          </math>
          <listOfLocalParameters><localParameter id="k" value="2"/></listOfLocalParameters>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""
    dossier = ingest_sbml(source, entry="shadow")
    (reaction,) = dossier.reactions
    assert [(p.name, p.value) for p in reaction.local_parameters] == [("k", 2.0)]
    assert [p.name for p in dossier.parameters] == ["k"]  # the global is still the global

    rebuilt = build_model_sbml(dossier)
    original = simulate(source, "B", duration=1.0, steps=10)[1][-1]
    after = simulate(rebuilt, "B", duration=1.0, steps=10)[1][-1]
    assert after == pytest.approx(original, rel=1e-9)
    # And it is the local 2 that ran: 10 * (1 - e^-2), not a species exhausted instantly.
    assert after == pytest.approx(10.0 * (1.0 - pow(2.718281828459045, -2.0)), rel=1e-4)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("kinetic/BIOMD0000000021.xml", "2 compartments"),
        ("kinetic/BIOMD0000000051.xml", "2 compartments"),
        ("worked_examples/Zake2021_metformin_human_single_PO.xml", "21 compartments"),
    ],
)
def test_a_network_a_rebuild_would_not_reproduce_is_refused_by_name(
    path: str, expected: str
) -> None:
    """Not carried is a different fact from not present, so the gap says which and why."""
    source = (Path(__file__).parent.parent / "datasets" / path).read_text(encoding="utf-8")
    dossier = ingest_sbml(source, entry="x")
    assert dossier.reactions == ()
    (gap,) = [g for g in dossier.gaps if g.element == "reaction network"]
    assert expected in gap.detail
    assert gap.load_bearing and gap.carried_by_artifact


def test_a_compartment_that_is_not_unit_sized_is_refused_by_its_size() -> None:
    """Every concentration in every rate law would be out by that volume."""
    source = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="big">
    <listOfCompartments><compartment id="c" size="5" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialAmount="10" hasOnlySubstanceUnits="false"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfReactions>
      <reaction id="J0" reversible="false">
        <listOfReactants>
          <speciesReference species="A" stoichiometry="1" constant="true"/>
        </listOfReactants>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>A</ci></math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""
    dossier = ingest_sbml(source, entry="big")
    assert dossier.reactions == ()
    (gap,) = [g for g in dossier.gaps if g.element == "reaction network"]
    assert "size 5.0" in gap.detail


def test_a_reaction_free_dossier_carries_no_reactions_and_no_gap_about_them() -> None:
    """The check must not read "carried nothing" as "this model has no reactions"."""
    source = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.1" constant="true"/></listOfParameters>
    <listOfRules>
      <rateRule variable="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>C</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""
    dossier = ingest_sbml(source, entry="m")
    assert dossier.reactions == () and dossier.compartments == ()
    assert not [g for g in dossier.gaps if g.element == "reaction network"]
    # And its dictionary is unchanged, so no dossier written before this keeps a different digest.
    assert "reactions" not in dossier.to_dict()
