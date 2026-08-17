"""Adopt-and-verify reads a species' initial value in the convention the model states it in.

Needs only python-libsbml (the ``engine`` extra's build half), so this runs wherever ingestion
does — unlike tests/test_sbml.py, which also needs COPASI to run the model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed")

from reprolith import compare_sbml_to_dossier, ingest_sbml  # noqa: E402

_KINETIC = Path(__file__).resolve().parents[1] / "datasets" / "kinetic"


def _concentration_model(value: str, size: str = "1") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
 <model id="m">
  <listOfCompartments><compartment id="c" size="{size}" constant="true"/></listOfCompartments>
  <listOfSpecies>
   <species id="X" compartment="c" initialConcentration="{value}"
            hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
  </listOfSpecies>
  <listOfParameters><parameter id="k" value="0.5" constant="true"/></listOfParameters>
  <listOfRules>
   <rateRule variable="X"><math xmlns="http://www.w3.org/1998/Math/MathML">
     <apply><times/><apply><minus/><ci>k</ci></apply><ci>X</ci></apply></math></rateRule>
  </listOfRules>
 </model>
</sbml>"""


@pytest.mark.parametrize("path", sorted(_KINETIC.glob("*.xml")), ids=lambda p: p.name)
def test_a_shipped_model_does_not_disagree_with_its_own_ingested_dossier(path: Path) -> None:
    # Reading the unset initial *amount* of a concentration-stated model reported every species
    # as a mismatch against 0 — a check that cries wolf on the repo's own datasets is a check
    # nobody can act on.
    sbml = path.read_text(encoding="utf-8")
    dossier = ingest_sbml(sbml, entry=path.stem, source_label=path.name)
    assert compare_sbml_to_dossier(sbml, dossier) == []


def test_a_real_disagreement_on_a_concentration_model_is_still_reported() -> None:
    dossier = ingest_sbml(_concentration_model("4"), entry="10.1/x")
    mismatches = compare_sbml_to_dossier(_concentration_model("9"), dossier)
    assert any("initial condition X" in m and "4.0" in m and "9.0" in m for m in mismatches)


def test_a_concentration_is_compared_as_the_amount_it_stands_for() -> None:
    # The dossier holds amounts. 4 mM in a 2 L compartment is 8, not 4 — comparing the bare
    # concentration would report a mismatch that is only a change of units.
    dossier = ingest_sbml(_concentration_model("8"), entry="10.1/x")
    assert compare_sbml_to_dossier(_concentration_model("4", size="2"), dossier) == []
