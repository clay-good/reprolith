"""The inline deterministic linter (bootstrap task 6.2).

These tests run the pinned engine, so they need the optional ``engine`` extra (python-copasi)
and the whole module skips when it is absent. The dependency-free classification primitive
(``verdict_for``) is covered in test_oracle.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import Tolerance, ToleranceSource, Verdict, lint_curve  # noqa: E402

ONE_COMPARTMENT_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="onecomp">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialAmount="100" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.5" constant="true"/></listOfParameters>
    <listOfRules>
      <rateRule variable="A">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>A</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>"""

# The claim's reference curve, sampled at the same 11 points (t = 0..10) the linter uses.
_TRUE_CURVE = tuple(100.0 * math.exp(-0.5 * t) for t in range(11))


def test_matching_model_lints_as_reproduced() -> None:
    result = lint_curve(ONE_COMPARTMENT_SBML, "A", reference=_TRUE_CURVE, duration=10.0, steps=10)
    assert result.verdict is Verdict.REPRODUCED
    # The verdict is never bare: it carries method, discrepancy, tolerance, and scope.
    assert result.to_dict()["scope"]["machine"] == "reproducible-not-correct-not-clinical"
    assert "normalized distance" in result.discrepancy


def test_wrong_reference_lints_as_failed() -> None:
    # A claim with the wrong baseline: the same decay shifted up by 40 concentration units,
    # a constant ~40% of the curve's range off everywhere.
    wrong = tuple(100.0 * math.exp(-0.5 * t) + 40.0 for t in range(11))
    result = lint_curve(ONE_COMPARTMENT_SBML, "A", reference=wrong, duration=10.0, steps=10)
    assert result.verdict is Verdict.FAILED


def test_same_submission_yields_same_verdict() -> None:
    a = lint_curve(ONE_COMPARTMENT_SBML, "A", reference=_TRUE_CURVE, duration=10.0, steps=10)
    b = lint_curve(ONE_COMPARTMENT_SBML, "A", reference=_TRUE_CURVE, duration=10.0, steps=10)
    assert a == b  # a deterministic gate an agent can rely on


def test_mismatched_reference_length_is_rejected() -> None:
    with pytest.raises(ValueError):
        lint_curve(ONE_COMPARTMENT_SBML, "A", reference=(1.0, 2.0), duration=10.0, steps=10)


def test_a_reported_level_that_is_not_boolean_is_refused_not_coerced() -> None:
    # Truthiness would read the JSON string "0" as ON, rewriting a state that is not a fixed
    # point into one that is and linting it green.
    import pytest
    from reprolith.linter import lint_steady_state

    rules = {"A": "B", "B": "A", "C": "A"}
    assert lint_steady_state(rules, {"A": 0, "B": 0, "C": 1}).verdict is Verdict.FAILED
    for bad in ({"A": "0", "B": "0", "C": "1"}, {"A": 0.4, "B": 0, "C": 0}, {"A": -3, "B": 0, "C": 0}):
        with pytest.raises(ValueError, match="integer 0 or 1"):
            lint_steady_state(rules, bad)


def test_a_non_finite_input_abstains_rather_than_reporting_the_paper_wrong() -> None:
    from reprolith.linter import lint_estimation

    nan = float("nan")
    assert lint_estimation(reported=1.0, recovered=nan).verdict is Verdict.NOT_EVALUABLE
    assert lint_estimation(reported=1.0, recovered=1.02).verdict is Verdict.REPRODUCED



def test_the_linter_refuses_the_tolerance_the_judge_refuses() -> None:
    """Same question, same answer: an agent cannot gate on a verdict the certificate would refuse.

    The widest documented pair (the digitized-figure population default) is a `class-default`
    tolerance, so `Tolerance` alone accepts it for any comparison. The judge checks the method too;
    the linter checked nothing, and passed a 24% relative error as reproduced.
    """
    from reprolith.linter import lint_estimation

    widest = Tolerance(0.25, 0.50, ToleranceSource.CLASS_DEFAULT)
    with pytest.raises(ValueError, match="is not the class default"):
        lint_estimation(reported=1.0, recovered=1.24, tolerance=widest)


def test_the_linter_judges_an_envelope_by_its_worst_point_too() -> None:
    """The envelope worst-point rule reaches the linter in the same commit as the judge."""
    import math

    from reprolith.linter import lint_distribution

    reference = [math.exp(-(((i - 40) / 20) ** 2)) for i in range(201)]
    predicted = [v * 2 if i == 40 else v for i, v in enumerate(reference)]
    result = lint_distribution(
        [{"percentile": 50.0, "curve": reference}], [{"percentile": 50.0, "curve": predicted}]
    )
    assert result.verdict is Verdict.FAILED
    assert "worst point" in result.discrepancy


def test_lint_diffusion_states_the_protocol_its_verdict_rests_on() -> None:
    """The inline spatial check published a bare verdict with neither grid nor boundary.

    `certify_spatial` argues at length that the discretization *is* the run and that this class's
    boundary condition is one a reader cannot see anywhere else; the linter — the same judgment,
    served to an agent over MCP — said neither, while `lint_stochastic` states its sampling.
    """
    from reprolith import lint_diffusion

    result = lint_diffusion(
        initial=(1.0, 0.0, 0.0, 0.0), reference=(0.6, 0.28, 0.09, 0.03),
        diffusivity=1.0, dx=1.0, dt=0.2, steps=2,
    )
    assert result.protocol is not None
    assert "zero-flux (Neumann) boundaries" in result.protocol
    assert "D=1.0" in result.protocol and "dx=1.0" in result.protocol and "2 steps" in result.protocol


_UNIT_MODEL = ONE_COMPARTMENT_SBML.replace(
    '<compartment id="c" size="1" constant="true"/>',
    '<compartment id="c" size="1" units="volume" constant="true"/>',
).replace(
    '<listOfCompartments>',
    '<listOfUnitDefinitions>'
    '<unitDefinition id="volume"><listOfUnits>'
    '<unit kind="litre" exponent="1" scale="-3" multiplier="1"/></listOfUnits></unitDefinition>'
    '<unitDefinition id="substance"><listOfUnits>'
    '<unit kind="mole" exponent="1" scale="-9" multiplier="1"/></listOfUnits></unitDefinition>'
    '</listOfUnitDefinitions><listOfCompartments>',
).replace('initialAmount="100"', 'initialAmount="100" substanceUnits="substance"')


def test_a_reference_in_another_unit_abstains_rather_than_being_compared() -> None:
    """The agent-facing surface, held to the rule the author-facing one follows.

    An agent gates its work on this verdict immediately, and a reference in µg/mL against a model
    reading nmol/mL produces a distance that is arithmetic — not a statement about the model, and
    not something anything downstream can see.
    """
    from reprolith import claim_units

    assert claim_units(_UNIT_MODEL, "A") == "10^-9 mole / 10^-3 litre"

    same = lint_curve(_UNIT_MODEL, "A", reference=_TRUE_CURVE, duration=10.0, steps=10,
                      reference_units="nmol/mL")
    assert same.verdict is Verdict.REPRODUCED

    other = lint_curve(_UNIT_MODEL, "A", reference=_TRUE_CURVE, duration=10.0, steps=10,
                       reference_units="mg/mL")
    assert other.verdict is Verdict.NOT_EVALUABLE
    assert "not the same quantity" in other.discrepancy

    # Opt-in on both sides: no unit stated, nothing checked and nothing claimed — and a unit this
    # cannot read is not evidence that the two differ, so it is not an abstention either.
    assert lint_curve(_UNIT_MODEL, "A", reference=_TRUE_CURVE, duration=10.0,
                      steps=10).verdict is Verdict.REPRODUCED
    assert lint_curve(_UNIT_MODEL, "A", reference=_TRUE_CURVE, duration=10.0, steps=10,
                      reference_units="arbitrary units").verdict is Verdict.REPRODUCED
