"""Archive vs manuscript (spec: paper-ingestion; roadmap #4's remaining half).

``archive_mismatches`` asks whether an archive's two files agree with each other.
``manuscript_mismatches`` asks whether the experiment they describe runs the result the *paper*
reports — the disagreement neither file can see, because neither one contains the manuscript.

The load-bearing case is real and shipped: BIOMD0000001028's SED-ML scans the metformin dose over
389.2, 778.4 and 1167.6 mg, and the paper's 1000 mg claim is 779.9 mg of free base. Everything
validates; nothing in the document runs the arm the paper reports.

Pure standard library, so it runs in the dependency-free core gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import Claim, manuscript_mismatches

_DATASETS = Path(__file__).parent.parent / "datasets"
_WORKED = _DATASETS / "worked_examples"

_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="m">
    <listOfParameters>
      <parameter id="dose" value="500" constant="true"/>
      <parameter id="k" value="0.5" constant="true"/>
    </listOfParameters>
    <listOfSpecies>
      <species id="C" compartment="c" initialConcentration="0"/>
    </listOfSpecies>
  </model>
</sbml>
"""

_SPECIES_TARGET = "/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='C']"
_DOSE_TARGET = "/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='dose']"


def _sedml(*, observes: str = _SPECIES_TARGET, changes: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version4" level="1" version="4">
  <listOfModels>
    <model id="model" language="urn:sedml:language:sbml" source="m.xml">
      <listOfChanges>{changes}</listOfChanges>
    </model>
  </listOfModels>
  <listOfSimulations>
    <uniformTimeCourse id="sim" initialTime="0" outputStartTime="0" outputEndTime="24"
                       numberOfSteps="240"/>
  </listOfSimulations>
  <listOfTasks>
    <task id="task" modelReference="model" simulationReference="sim"/>
  </listOfTasks>
  <listOfDataGenerators>
    <dataGenerator id="g_C" name="C">
      <listOfVariables>
        <variable id="v_C" target="{observes}" taskReference="task"/>
      </listOfVariables>
    </dataGenerator>
  </listOfDataGenerators>
</sedML>
"""


def _claim(**overrides: object) -> Claim:
    record = {
        "claim_id": "peak",
        "quantity": "peak concentration",
        "species": "C",
        "reported": 6.2,
        "source_location": "Table 1",
        **overrides,
    }
    return Claim.from_record(record)


def test_an_archive_that_runs_the_claim_reports_nothing() -> None:
    assert manuscript_mismatches(_sedml(), _SBML, [_claim()]) == []


def test_a_claim_reading_an_output_the_model_does_not_have_is_reported() -> None:
    (message,) = manuscript_mismatches(_sedml(), _SBML, [_claim(species="plasma")])
    assert "'plasma'" in message and "model does not declare" in message


def test_a_claim_reading_an_output_the_experiment_never_records_is_reported() -> None:
    """The model has it; the document records no column it could be read from."""
    other = "/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='k']"
    (message,) = manuscript_mismatches(_sedml(observes=other), _SBML, [_claim()])
    assert "'C'" in message and "never records" in message


def test_an_unreadable_observation_target_suppresses_the_never_records_report() -> None:
    """Failing to read a target is not evidence the document does not record the quantity."""
    by_name = "/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@name='C']"
    assert manuscript_mismatches(_sedml(observes=by_name), _SBML, [_claim()]) == []


def test_a_claim_setting_a_parameter_the_model_does_not_declare_is_reported() -> None:
    claim = _claim(parameter_overrides={"Dose": 1000.0})
    (message,) = manuscript_mismatches(_sedml(), _SBML, [claim])
    assert "'Dose'" in message and "model does not declare" in message


def test_a_value_the_model_itself_states_is_not_a_mismatch() -> None:
    claim = _claim(parameter_overrides={"dose": 500.0})
    assert manuscript_mismatches(_sedml(), _SBML, [claim]) == []


def test_a_value_the_experiment_sets_is_not_a_mismatch() -> None:
    change = f'<changeAttribute target="{_DOSE_TARGET}/@value" newValue="1000"/>'
    claim = _claim(parameter_overrides={"dose": 1000.0})
    assert manuscript_mismatches(_sedml(changes=change), _SBML, [claim]) == []


def test_a_value_neither_the_model_nor_the_experiment_runs_is_reported() -> None:
    change = f'<changeAttribute target="{_DOSE_TARGET}/@value" newValue="1000"/>'
    claim = _claim(parameter_overrides={"dose": 779.9})
    (message,) = manuscript_mismatches(_sedml(changes=change), _SBML, [claim])
    assert "779.9" in message
    assert "the model states 500 and the experiment runs it at 1000" in message


def test_a_change_to_another_attribute_does_not_count_as_running_the_value() -> None:
    """Renaming a parameter leaves its value where it was."""
    change = f'<changeAttribute target="{_DOSE_TARGET}/@name" newValue="1000"/>'
    claim = _claim(parameter_overrides={"dose": 1000.0})
    (message,) = manuscript_mismatches(_sedml(changes=change), _SBML, [claim])
    assert "the model states 500" in message and "experiment runs it at" not in message


def test_a_change_whose_value_is_unreadable_suppresses_the_report() -> None:
    change = f'<computeChange target="{_DOSE_TARGET}/@value"/>'
    claim = _claim(parameter_overrides={"dose": 779.9})
    assert manuscript_mismatches(_sedml(changes=change), _SBML, [claim]) == []


def test_an_id_two_model_elements_carry_offers_no_value_to_compare() -> None:
    """A bare manuscript name cannot pick between two elements, so nothing is asserted."""
    doubled = _SBML.replace(
        '<parameter id="k" value="0.5" constant="true"/>',
        '<parameter id="k" value="0.5" constant="true"/>\n'
        '      <parameter id="dose" value="250" constant="true"/>',
    )
    claim = _claim(parameter_overrides={"dose": 779.9})
    assert manuscript_mismatches(_sedml(), doubled, [claim]) == []


def test_unparseable_input_raises() -> None:
    with pytest.raises(ValueError):
        manuscript_mismatches("not xml", _SBML, [_claim()])
    with pytest.raises(ValueError):
        manuscript_mismatches(_sedml(), "not xml", [_claim()])


def test_the_shipped_metformin_archive_does_not_run_the_dose_the_paper_reports() -> None:
    """The real document, the real model, and the real manuscript-extracted claims.

    The 500 mg claim runs at the model's own value and reads a species the document records, so it
    is silent. The 1000 mg claim is 779.9 mg of free base, and the document's scan runs 389.2,
    778.4 and 1167.6 — near misses, which is exactly why adopting it verbatim would look fine.
    """
    sedml = (_WORKED / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8")
    sbml = (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")
    entry = json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))
    claims = [Claim.from_record(c) for c in entry["entries"]["BIOMD0000001028"]["claims"]]

    messages = manuscript_mismatches(sedml, sbml, claims)

    # Three of the entry's four claims run at a dose this document never reaches, and it reports
    # all three. Two of them state that dose in a *schedule* rather than in `parameter_overrides`
    # — a claim that runs after a prior administration — and reading the top-level field alone
    # this check saw nothing for either, and said nothing about the two whose dose is hardest for
    # a reader to find.
    # Every claim whose dose this document never reaches, and it reports each of them. The
    # scheduled ones state that dose in a *schedule* rather than in `parameter_overrides` — a
    # claim that runs after a prior administration — and reading the top-level field alone this
    # check saw nothing for them, and said nothing about the doses hardest for a reader to find.
    joined = " | ".join(messages)
    # Every claim that runs at a dose this document never reaches, whether that dose is stated as
    # an override or in a schedule's last segment. Derived from the claims, because the entry has
    # grown from two of them to thirty-three.
    expected = {}
    for claim in claims:
        values = claim.schedule[-1][1] if claim.schedule else claim.parameter_overrides
        for _, value in values:
            expected[claim.claim_id] = f"{value:g}"
    assert expected, "no claim sets a dose; this check would pass vacuously"
    assert len(messages) == len(expected), (len(messages), len(expected))
    for claim_id, dose in expected.items():
        assert f"'{claim_id}'" in joined and dose in joined, claim_id
    assert "389.2, 778.4, 1167.6" in joined


def test_a_value_the_model_computes_is_not_read_off_its_inert_attribute() -> None:
    """SBML makes `value` inert for a parameter an initial assignment sets. Reading it as what the
    model runs is a number that is not a check — and can silence a real mismatch by coincidence."""
    assigned = _SBML.replace(
        "  </model>",
        "    <listOfInitialAssignments>\n"
        '      <initialAssignment symbol="dose">\n'
        '        <math xmlns="http://www.w3.org/1998/Math/MathML"><cn>750</cn></math>\n'
        "      </initialAssignment>\n"
        "    </listOfInitialAssignments>\n"
        "  </model>",
    )
    claim = _claim(parameter_overrides={"dose": 779.9})
    assert manuscript_mismatches(_sedml(), assigned, [claim]) == []
    # The same claim against the same model without the assignment is still reported, so the
    # suppression is the assignment's doing and not a hole in the check.
    assert manuscript_mismatches(_sedml(), _SBML, [claim])

    # And the case that makes the suppression load-bearing rather than a duplicate of the "no
    # stated value" one: a document that *does* set the parameter. Its change is overridden at run
    # time by the assignment, so "the archive runs it at 1000" is not true about the run either —
    # naming a value the model does not use is the defect, whichever side supplies the number.
    # (Found by mutation: with this branch removed, the first assertion above still passed.)
    change = f'<changeAttribute target="{_DOSE_TARGET}/@value" newValue="1000"/>'
    assert manuscript_mismatches(_sedml(changes=change), assigned, [claim]) == []
