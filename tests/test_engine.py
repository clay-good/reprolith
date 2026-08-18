"""A trivial hand-built model runs under the pinned engine (bootstrap task 0.1).

These tests need the optional ``engine`` extra (python-copasi) and are skipped when it is not
installed, so the dependency-free required-checks gate stays green. Install with
``pip install -e ".[engine]"`` to run them.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import engine_pin, simulate  # noqa: E402

# A one-compartment first-order elimination model: dA/dt = -k*A, A(0)=100, k=0.5.
# Its exact solution is A(t) = 100 * exp(-0.5 t), so the engine has a known target.
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


def test_trivial_model_reproduces_its_known_output() -> None:
    times, values = simulate(ONE_COMPARTMENT_SBML, "A", duration=10.0, steps=10)
    assert times[0] == 0.0 and times[-1] == 10.0
    for t, v in zip(times, values):
        analytic = 100.0 * math.exp(-0.5 * t)
        assert abs(v - analytic) / analytic < 1e-4  # matches the exact solution


def test_simulation_is_deterministic() -> None:
    a = simulate(ONE_COMPARTMENT_SBML, "A", duration=10.0, steps=20)
    b = simulate(ONE_COMPARTMENT_SBML, "A", duration=10.0, steps=20)
    assert a == b  # same model + pin -> byte-identical series


def test_engine_pin_reports_the_pinned_engine() -> None:
    from reprolith.pins import algorithm_revision

    pin = engine_pin()
    assert pin.engine == "copasi"
    assert pin.version  # the concrete installed version travels with the pin
    assert pin.algorithm is not None and pin.algorithm.startswith("deterministic-lsoda")
    # An external solver carries its own version, but the judge that decides what its numbers mean
    # is this package: a class-default tolerance or a change to the verdict rule invalidates these
    # certificates too, and used to leave them looking fresh.
    assert f"judge rev {algorithm_revision('engine', 'certify', 'oracle', 'certificate')}" in pin.algorithm


def test_unknown_species_is_rejected() -> None:
    with pytest.raises(ValueError):
        simulate(ONE_COMPARTMENT_SBML, "NotThere", duration=1.0, steps=1)


def test_species_resolved_by_sbml_id_when_names_collide() -> None:
    # The Landberg2009 model names three distinct species "AR"; the ambiguous column title
    # would not identify one, but the SBML id (AR_Central) does.
    from pathlib import Path

    sbml = (Path(__file__).parent / "fixtures" / "BIOMD0000000948.xml").read_text(encoding="utf-8")
    times, values = simulate(sbml, "AR_Central", duration=48.0, steps=240)
    assert len(values) == 241
    assert max(values) > 0.0  # the plasma compartment rises after the dose
