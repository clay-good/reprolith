"""Writing the claims file the author-facing check needs (roadmap #4, author side).

`archive-check --claims` makes the one check nothing in an archive can make on itself — does the
shipped experiment run the result the paper reports — and it needs a file the author writes by
hand. Nothing helped write one. `claims_template` does, and the property that matters more than
any single field is that it never writes a *value*: a template that guessed `reported` from the
model would hand the check the model's own output as the paper's claim, and the comparison would
pass by construction.

Pure standard library, so this runs in the dependency-free core gate — except the end-to-end
test, which hands the filled file to the check itself and so needs the `engine` extra to read
the model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import claims_template, unfilled_claims
from reprolith.cli import _load_claims

_WORKED = Path(__file__).parent.parent / "datasets" / "worked_examples"
_METFORMIN_MODEL = (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")
_METFORMIN_SEDML = (_WORKED / "Zake2021_metformin_human_single_PO.sedml").read_text(
    encoding="utf-8"
)

_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
      <species id="D" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="k" value="0.1" constant="true"/>
      <parameter id="derived" value="0" constant="false"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="derived">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>k</ci></math>
      </initialAssignment>
    </listOfInitialAssignments>
    <listOfReactions>
      <reaction id="J0" reversible="false">
        <listOfReactants><speciesReference species="C" stoichiometry="1" constant="true"/></listOfReactants>
        <listOfProducts><speciesReference species="D" stoichiometry="1" constant="true"/></listOfProducts>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""


def _document(curves: str, *, generators: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version4" level="1" version="4">
  <listOfModels>
    <model id="model" language="urn:sedml:language:sbml" source="m.xml"/>
  </listOfModels>
  <listOfSimulations>
    <uniformTimeCourse id="sim" initialTime="0" outputStartTime="0" outputEndTime="24"
                       numberOfSteps="240"/>
  </listOfSimulations>
  <listOfTasks><task id="task" modelReference="model" simulationReference="sim"/></listOfTasks>
  <listOfDataGenerators>
    <dataGenerator id="g_time" name="time">
      <listOfVariables>
        <variable id="v_time" symbol="urn:sedml:symbol:time" taskReference="task"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_time</ci></math>
    </dataGenerator>
    <dataGenerator id="g_C" name="C in plasma">
      <listOfVariables>
        <variable id="v_C" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='C']"
                  taskReference="task"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_C</ci></math>
    </dataGenerator>
    {generators}
  </listOfDataGenerators>
  <listOfOutputs>
    <plot2D id="fig1" name="Figure 1"><listOfCurves>{curves}</listOfCurves></plot2D>
  </listOfOutputs>
</sedML>
"""


_SIMPLE = _document('<curve id="c_C" logX="false" logY="false" xDataReference="g_time" '
                    'yDataReference="g_C"/>')


def test_a_plotted_curve_becomes_a_stub_naming_the_output_it_reads() -> None:
    """A plot is the document's own statement that a curve is a shown result, so it is a stub."""
    template = claims_template(_SBML, sedml=_SIMPLE)
    assert [c["claim_id"] for c in template["claims"]] == ["c_C"]
    stub = template["claims"][0]
    assert stub["species"] == "C"
    assert stub["quantity"] == "C in plasma"


@pytest.mark.parametrize(
    "sedml", [None, _SIMPLE, _METFORMIN_SEDML],
    ids=["no document", "one curve", "the 81-curve metformin document"],
)
def test_no_stub_ever_carries_a_reported_value(sedml: str | None) -> None:
    """The property the whole template rests on, checked over the real 81-curve document.

    A guessed `reported` is the check passing against the model's own output — the failure it
    exists to catch, moved one file upstream — so this holds for every stub of every input.
    """
    model = _METFORMIN_MODEL if sedml is _METFORMIN_SEDML else _SBML
    claims = claims_template(model, sedml=sedml)["claims"]
    assert claims or sedml is None
    assert all(c["reported"] is None and c["source_location"] == "" for c in claims)


def test_a_model_alone_yields_no_claims_and_says_why() -> None:
    """A model states what can be read; only the document states what the paper showed."""
    template = claims_template(_SBML)
    assert template["claims"] == []
    assert any("never what your paper showed" in note for note in template["notes"])
    # It is not empty-handed: the two lists an author needs to write stubs by hand are there.
    assert {o["id"] for o in template["readable_outputs"]} == {"C", "D", "k", "derived"}


def test_a_curve_plotting_values_the_document_ships_is_not_a_claim() -> None:
    """Those are the paper's own recorded points, not a result the model owes."""
    generators = """
    <dataGenerator id="g_obs" name="observed C">
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>observedC</ci></math>
    </dataGenerator>"""
    sedml = _document(
        '<curve id="c_obs" logX="false" logY="false" xDataReference="g_time" '
        'yDataReference="g_obs"/>',
        generators=generators,
    ).replace(
        "<listOfModels>",
        """<listOfDataDescriptions>
    <dataDescription id="obs" source="observed.csv" format="urn:sedml:format:csv">
      <listOfDataSources><dataSource id="observedC"/></listOfDataSources>
    </dataDescription>
  </listOfDataDescriptions>
  <listOfModels>""",
    )
    template = claims_template(_SBML, sedml=sedml)
    assert template["claims"] == []
    assert any("not a result the model owes" in note for note in template["notes"])


def test_a_curve_over_two_elements_names_neither() -> None:
    """A ratio or a sum is an expression; a claim reads one output, so the author names it."""
    generators = """
    <dataGenerator id="g_ratio" name="C over D">
      <listOfVariables>
        <variable id="a" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='C']"
                  taskReference="task"/>
        <variable id="b" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='D']"
                  taskReference="task"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML">
        <apply><divide/><ci>a</ci><ci>b</ci></apply>
      </math>
    </dataGenerator>"""
    template = claims_template(_SBML, sedml=_document(
        '<curve id="c_ratio" logX="false" logY="false" xDataReference="g_time" '
        'yDataReference="g_ratio"/>',
        generators=generators,
    ))
    assert [c["species"] for c in template["claims"]] == [""]
    assert any("C, D" in note and "one output" in note for note in template["notes"])


def test_a_curve_plotting_a_reaction_leaves_the_output_blank() -> None:
    """A flux is not in the time series a claim reads, and a blank is what `unfilled` reports."""
    generators = """
    <dataGenerator id="g_flux" name="J0 flux">
      <listOfVariables>
        <variable id="v_J0"
                  target="/sbml:sbml/sbml:model/sbml:listOfReactions/sbml:reaction[@id='J0']"
                  taskReference="task"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_J0</ci></math>
    </dataGenerator>"""
    template = claims_template(_SBML, sedml=_document(
        '<curve id="c_flux" logX="false" logY="false" xDataReference="g_time" '
        'yDataReference="g_flux"/>',
        generators=generators,
    ))
    assert [c["species"] for c in template["claims"]] == [""]
    assert any("declares as a reaction" in note for note in template["notes"])
    assert unfilled_claims(template["claims"])


def test_a_parameter_the_models_own_math_determines_is_not_offered_as_settable() -> None:
    """An override on an initial-assignment parameter is refused downstream; never invite one."""
    template = claims_template(_SBML)
    assert [p["id"] for p in template["settable_parameters"]] == ["k"]
    assert template["model_determines"] == ["derived"]


def test_the_metformin_numbers_the_findings_note_quotes_are_the_ones_measured() -> None:
    """The real case the inert-attribute rule was written for, and the figures three docs print.

    `docs/findings-note.md` states 81 stubs from 81 curves, 35 curves plotting reaction fluxes,
    and 78 of the model's 94 parameters withheld as model-determined with the dose in the other
    16. A number in a document that nothing re-derives is a number that quietly goes stale.
    """
    template = claims_template(_METFORMIN_MODEL, sedml=_METFORMIN_SEDML)
    assert len(template["claims"]) == 81
    assert sum(1 for n in template["notes"] if "as a reaction" in n) == 35
    settable = {p["id"] for p in template["settable_parameters"]}
    assert len(settable) == 16
    assert len(template["model_determines"]) == 78
    assert "Metformin_Dose_in_Lumen_in_mg" in settable  # the dose a claim actually sets
    assert set(template["model_determines"]).isdisjoint(settable)


def test_a_model_no_time_course_describes_is_withheld_by_name() -> None:
    """A logical model advances in update steps; a claims file describes a time-course result."""
    qual = (Path(__file__).parent / "fixtures" / "toggle_qual.xml").read_text(encoding="utf-8")
    template = claims_template(qual, sedml=_SIMPLE)
    assert template["claims"] == []
    assert any("'qual'" in line for line in template["withheld"])


def test_unfilled_claims_names_every_blank_and_nothing_else() -> None:
    filled = {
        "claim_id": "Cmax", "quantity": "peak", "species": "C",
        "reported": 6.2, "source_location": "Table 4",
    }
    assert unfilled_claims([filled]) == ()
    blanks = unfilled_claims([{"claim_id": "Cmax", "species": "", "reported": None}])
    assert len(blanks) == 3
    assert all(line.startswith("Cmax: ") for line in blanks)


def test_the_loader_refuses_an_unfilled_template_by_naming_its_blanks(tmp_path: Path) -> None:
    """It used to arrive as a TypeError on float(None) from inside the record parser."""
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(claims_template(_SBML, sedml=_SIMPLE)), encoding="utf-8")
    with pytest.raises(ValueError) as refused:
        _load_claims(path, None)
    assert "'reported' is blank" in str(refused.value)


def test_a_filled_template_loads_and_reaches_the_check_it_was_written_for(tmp_path: Path) -> None:
    """The whole point, end to end: template out, one claim filled, the real mismatch found."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith.presubmission import pair_report

    template = claims_template(
        _METFORMIN_MODEL, sedml=_METFORMIN_SEDML, accession="BIOMD0000001028"
    )
    body = template["entries"]["BIOMD0000001028"]
    # What an author does with an 81-stub template: delete the curves the paper does not report,
    # keep the one it does. A stub left blank is refused, which the description says.
    stub = next(c for c in body["claims"] if c["species"] == "mPlasmaVenous")
    body["claims"] = [stub]
    stub.update({
        "reported": 11.2,
        "source_location": "Table 4",
        "parameter_overrides": {"Metformin_Dose_in_Lumen_in_mg": 779.9},
    })
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(template), encoding="utf-8")

    claims = _load_claims(path, "BIOMD0000001028")
    report = pair_report(
        _METFORMIN_SEDML, _METFORMIN_MODEL, claims=claims,
        model_filename="Zake2021_Metformin_Human_single_PO_dose.xml",
    )
    assert any("779.9" in item["issue"] for item in report["fix_list"]), report["fix_list"]


def test_the_accession_form_is_the_shape_a_multi_paper_claims_file_uses() -> None:
    template = claims_template(_SBML, sedml=_SIMPLE, accession="ACC1")
    assert set(template["entries"]) == {"ACC1"}
    assert template["entries"]["ACC1"]["claims"][0]["claim_id"] == "c_C"


def test_the_stub_carries_the_unit_field_blank_and_does_not_require_it() -> None:
    """One vocabulary across the three things that produce a claim record.

    The table proposer reads the unit off the column heading, the prose proposer off the sentence,
    and this writes the blank — all of them under the name `claims-check --model` reads. A curator
    who never fills it in loses only the unit check; refusing their file for a check they did not
    ask for would be the same defect this module avoids everywhere else.
    """
    from reprolith import claims_template, unfilled_claims

    template = claims_template(_METFORMIN_MODEL, sedml=_METFORMIN_SEDML)
    stubs = template["claims"]
    assert stubs, "this document plots nothing; the check would pass vacuously"
    assert all(stub["reported_units"] == "" for stub in stubs)
    # Blank, and not one of the blanks that make a file unusable.
    blanks = unfilled_claims(stubs)
    assert blanks, "an unfilled template should report its blanks"
    assert not any("reported_units" in blank for blank in blanks)
