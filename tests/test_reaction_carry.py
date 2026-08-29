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
    """The worst difference between the artifact and a model rebuilt from its dossier.

    Measured against each species' **own scale** — the largest value it reaches over the run —
    rather than against its end value. A species that has decayed to a residual makes an absolute
    difference of 1e-6 look like 2e-5, and the tolerance then tracks how much is left rather than
    how well the two models agree; `judge_scalar` says the same thing about a reported zero
    through its `zero_scale`. Dividing by the end value cost three rounds of CI to notice in the
    dosing-schedule tests, so it is not repeated here.
    """
    from reprolith.engine import simulate

    dossier = ingest_sbml(source, entry="x")
    assert dossier.reactions, "this model's reactions were not carried"
    rebuilt = build_model_sbml(dossier)
    worst = 0.0
    for name in dossier.state_variables:
        original = simulate(source, name, duration=duration, steps=steps)[1]
        after = simulate(rebuilt, name, duration=duration, steps=steps)[1]
        scale = max((abs(value) for value in original), default=0.0)
        if scale == 0.0:
            # A species that is zero throughout agrees exactly or not at all; there is no scale
            # to divide by, so the difference itself is the measure.
            worst = max(worst, abs(original[-1] - after[-1]))
            continue
        worst = max(worst, abs(original[-1] - after[-1]) / scale)
    return worst


def test_a_ten_reaction_cascade_rebuilds_as_itself() -> None:
    """Kholodenko's MAPK cascade: the model the `reaction network` gap was written about."""
    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    source = (_KINETIC / "BIOMD0000000010.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(source, entry="BIOMD0000000010")
    assert len(dossier.reactions) == 10
    assert not [g for g in dossier.gaps if g.element == "reaction network"]
    # 7.5e-15 on the machine this was written on. The bound is set by what it must catch — a
    # dropped reaction, a mistranslated rate law, a stoichiometry read from the wrong column, all
    # of which move a trajectory by percent — not by that measurement, because COPASI's own
    # cross-call noise is build-dependent and reaches 1.7e-7 on one of CI's interpreters. A
    # tolerance fitted to one machine is a threshold with no basis.
    assert _round_trip(source, duration=100.0, steps=50) < 1e-4


def test_a_model_whose_reactions_and_rules_both_matter_rebuilds_too() -> None:
    """The repressilator: twelve reactions *and* nine assignment rules, carried together.

    The residual is integration, not a difference in the model. Measured: 1.4e-9 at t=0.01, 1.2e-7
    at t=1, 1.1e-6 at t=50 — it grows with the run, which is what integration error does and what a
    changed rate law does not. CVODE takes slightly different steps through two files whose
    element order differs, and this is a stiff oscillator. The MAPK cascade, which is not
    oscillatory, comes back at 7.5e-15 over a hundred time units.

    Both ends are asserted so that a real change in the math cannot hide inside a tolerance chosen
    for the long run — but each bound is set an order or more above the *largest* noise seen
    anywhere, not fitted to the number measured here. A changed rate law moves these by percent.
    """
    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    source = (_KINETIC / "BIOMD0000000012.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(source, entry="BIOMD0000000012")
    assert len(dossier.reactions) == 12
    assert len([e for e in dossier.equations]) == 9  # the rules are carried as before
    assert _round_trip(source, duration=0.01, steps=2) < 1e-4
    assert _round_trip(source, duration=50.0, steps=50) < 1e-3


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
    # Above the engine's own cross-call noise on every build, and far below the failure this
    # catches: hoisting the local `k` runs the reaction five hundred times too fast.
    assert after == pytest.approx(original, rel=1e-5)
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


def _reaction_dossier(**overrides: object):
    """A minimal hand-authored reaction dossier — the path a reviewer correction reaches."""
    from reprolith import Dossier, DossierReaction, Parameter

    fields: dict[str, object] = {
        "entry": "x",
        "state_variables": ("A", "B"),
        "initial_conditions": (
            Parameter(name="A", value=1.0, unit="mole", source_location="s"),
            Parameter(name="B", value=0.0, unit="mole", source_location="s"),
        ),
        "reactions": (
            DossierReaction(
                id="J0", rate_expression="k * A", source_location="s",
                reactants=(("A", 1.0),), products=(("B", 1.0),),
                local_parameters=(
                    Parameter(name="k", value=1.0, unit="per_second", source_location="s"),
                ),
            ),
        ),
        "compartments": (Parameter(name="c1", value=1.0, unit="litre", source_location="s"),),
    }
    fields.update(overrides)
    return Dossier(**fields)  # type: ignore[arg-type]


def test_a_second_compartment_is_refused_on_the_way_out_too() -> None:
    """Ingestion refuses to carry one; this is the way out, which a hand-authored dossier reaches.

    Emitting the first and dropping the rest built a model that ran, validated, and was not the
    one the dossier described — every species in the second compartment silently relocated.
    """
    from reprolith import Parameter

    dossier = _reaction_dossier(compartments=(
        Parameter(name="c1", value=1.0, unit="litre", source_location="s"),
        Parameter(name="c2", value=1.0, unit="litre", source_location="s"),
    ))
    with pytest.raises(ValueError, match="2 compartments"):
        build_model_sbml(dossier)


def test_a_compartment_of_another_size_is_refused_on_the_way_out_too() -> None:
    """A rebuild gives it size 1, so every concentration a rate law reads moves with the volume."""
    from reprolith import Parameter

    dossier = _reaction_dossier(compartments=(
        Parameter(name="c1", value=5.0, unit="litre", source_location="s"),
    ))
    with pytest.raises(ValueError, match="size 5"):
        build_model_sbml(dossier)


def test_the_adopted_model_sweep_can_see_a_reaction_model_missing_a_state() -> None:
    """Opening the sweep to carried networks without this made it report on what it never read.

    It used to return early for any model with reactions, justified by the `reaction network` gap
    standing in for the dynamics. A carried network has no such gap, so the sweep should run — but
    its `needed` set came from *rules*, and MAPK has none, so it would have reported "no
    disagreement" over a model it had not looked at. What a reaction network needs is what its
    laws read and what its participants are.
    """
    import dataclasses

    from reprolith import compare_sbml_to_dossier

    source = (_KINETIC / "BIOMD0000000010.xml").read_text(encoding="utf-8")
    dossier = ingest_sbml(source, entry="BIOMD0000000010")
    assert compare_sbml_to_dossier(source, dossier) == []

    lost = dossier.initial_conditions[0].name
    broken = dataclasses.replace(
        dossier,
        initial_conditions=dossier.initial_conditions[1:],
        state_variables=tuple(v for v in dossier.state_variables if v != lost),
    )
    reported = compare_sbml_to_dossier(source, broken)
    assert any(line.startswith(f"{lost}: ") for line in reported), reported


_UNSTATED_STOICHIOMETRY = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialAmount="10" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
      <species id="B" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="k" value="1" constant="true"/>
      <parameter id="s" value="3" constant="false"/>
    </listOfParameters>
    <listOfReactions>
      <reaction id="J0" reversible="false">
        <listOfReactants>
          <speciesReference id="sr" species="A" constant="false"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="B" stoichiometry="1" constant="true"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><times/><ci>k</ci><ci>A</ci></apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
    <listOfRules>
      <assignmentRule variable="sr">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>s</ci></math>
      </assignmentRule>
    </listOfRules>
  </model>
</sbml>
"""

_FAST = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialAmount="10"/>
      <species id="B" compartment="c" initialAmount="0"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="1"/></listOfParameters>
    <listOfReactions>
      <reaction id="J0" reversible="false" fast="true">
        <listOfReactants><speciesReference species="A" stoichiometry="1"/></listOfReactants>
        <listOfProducts><speciesReference species="B" stoichiometry="1"/></listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><times/><ci>k</ci><ci>A</ci></apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""


def test_a_stoichiometry_the_model_computes_is_not_carried_as_a_number() -> None:
    """It arrived as NaN, which the dossier recorded as if it were a measurement.

    A species reference whose stoichiometry a rule sets has no stated one — the same inert
    attribute as a parameter under an assignment, one element type over — and libSBML hands back
    NaN for it rather than failing.
    """
    dossier = ingest_sbml(_UNSTATED_STOICHIOMETRY, entry="x")
    assert dossier.reactions == ()
    (gap,) = [g for g in dossier.gaps if g.element == "reaction network"]
    assert "states no stoichiometry for A" in gap.detail


def test_a_fast_reaction_is_not_carried_as_an_ordinary_one() -> None:
    """It is solved at pseudo-equilibrium, not integrated; a rebuild would integrate it."""
    dossier = ingest_sbml(_FAST, entry="x")
    assert dossier.reactions == ()
    (gap,) = [g for g in dossier.gaps if g.element == "reaction network"]
    assert "marked fast" in gap.detail
