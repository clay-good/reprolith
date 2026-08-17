"""The inline deterministic linter (bootstrap task 6.2).

These tests run the pinned engine, so they need the optional ``engine`` extra (python-copasi)
and the whole module skips when it is absent. The dependency-free classification primitive
(``verdict_for``) is covered in test_oracle.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import Verdict, lint_curve  # noqa: E402

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
