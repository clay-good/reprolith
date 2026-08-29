"""Two claims that do not reproduce, and the measurements behind each cause.

Until now every committed claim reproduced, so the engine's failure path had never been exercised
on real published data. The twice-daily metformin entry has six that do not — red blood cells and
brain, at three doses each — and they fail for two entirely different reasons, both established by
measurement rather than asserted.

**Red blood cells: the artifact runs less of the protocol than the paper states.** The deposited
model is named "eight PO administrations with 12h interval" and carries four dose events. Which
tissues that reaches depends on their half-lives: plasma is at steady state by the third dose, so
the missing four move it 0.05%; red blood cells have a 21.7-hour half-life and come out 15% low.
Supplying the four missing doses brings them to 1.1% of the paper.

**Brain: a cell of the paper's table contradicts its own row.** Table 7 gives Brain an AUC24 and a
Cmean that are 0.80 of plasma's — the same ratio Table 6 gives for a single dose, and the ratio the
model produces — and a Cmax exactly equal to plasma's.

Needs the `engine` extra.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")

from reprolith.engine import simulate  # noqa: E402
from reprolith.sbml import _libsbml  # noqa: E402

_ROOT = Path(__file__).parent.parent
_MODEL = (
    _ROOT / "datasets" / "worked_examples" / "Zake2021_Metformin_Human_multiple_PO_dose.xml"
).read_text(encoding="utf-8")
_TABLE7 = json.loads(
    (_ROOT / "datasets" / "manuscripts" / "BIOMD0000001029_tables.json").read_text(encoding="utf-8")
)["tables"]["Table 7"]
_TABLE6 = json.loads(
    (_ROOT / "datasets" / "manuscripts" / "BIOMD0000001028_tables.json").read_text(encoding="utf-8")
)["tables"]["Table 6"]


def _number(text: str) -> float:
    return float(text.replace(" ", "").replace(" ", "").replace(" ", ""))


def _cell(table: dict, tissue: str, dose: str, column: str) -> float:
    header = table["rows"][0]
    tissue_at, dose_at, column_at = (
        header.index("Tissue"), header.index("Dose, mg"), header.index(column)
    )
    for row in table["rows"][1:]:
        if row[tissue_at] == tissue and row[dose_at] == dose:
            return _number(row[column_at])
    raise AssertionError(f"no {tissue} row at {dose} mg")


def _with_eight_doses() -> str:
    """The deposited model plus the four administrations its own name says it has."""
    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(_MODEL)
    model = document.getModel()
    assert model.getNumEvents() == 4, "the deposited model no longer carries four dose events"
    template = model.getEvent(model.getNumEvents() - 1)
    for hour in (48, 60, 72, 84):
        event = model.createEvent()
        event.setId(f"Dose_{hour}h")
        event.setUseValuesFromTriggerTime(True)
        trigger = event.createTrigger()
        trigger.setInitialValue(True)
        trigger.setPersistent(True)
        trigger.setMath(libsbml.parseL3Formula(f"time > {hour}"))
        for index in range(template.getNumEventAssignments()):
            source = template.getEventAssignment(index)
            assignment = event.createEventAssignment()
            assignment.setVariable(source.getVariable())
            assignment.setMath(source.getMath().deepCopy())
    return str(libsbml.writeSBMLToString(document))


def test_the_missing_doses_are_what_the_red_blood_cell_claim_misses_by() -> None:
    """The attribution, measured: supply them and the claim reproduces."""
    reported = _cell(_TABLE7, "Red blood cells", "500", "Cmax, nmol/mL")
    as_deposited = max(simulate(_MODEL, "mRBC", duration=48.0, steps=960)[1])
    with_all_eight = max(simulate(_with_eight_doses(), "mRBC", duration=108.0, steps=2160)[1])

    assert abs(as_deposited - reported) / reported > 0.15  # what the certificate reports
    assert abs(with_all_eight - reported) / reported < 0.02  # what the paper's protocol gives


def test_the_same_missing_doses_barely_move_plasma() -> None:
    """Which is why this is a cause per claim and not a property of the model.

    Plasma's half-life is 3.9 hours and it is at steady state by the third dose; red blood cells'
    is 21.7 and they are still accumulating. The same defect in the same file is 0.05% for one
    tissue and 15% for another, so "the model is missing four doses" is not by itself a verdict
    about any claim.
    """
    reported = _cell(_TABLE7, "Plasma", "500", "Cmax, nmol/mL")
    as_deposited = max(simulate(_MODEL, "mPlasmaVenous", duration=48.0, steps=960)[1])
    with_all_eight = max(simulate(_with_eight_doses(), "mPlasmaVenous", duration=108.0, steps=2160)[1])

    assert abs(as_deposited - reported) / reported < 0.02
    assert abs(with_all_eight - as_deposited) / as_deposited < 0.01
    assert _cell(_TABLE7, "Red blood cells", "500", "T1/2, h") > 20.0
    assert _cell(_TABLE7, "Plasma", "500", "T1/2, h") < 5.0


def test_the_brain_cmax_contradicts_its_own_row() -> None:
    """The evidence for calling this the paper's error rather than the model's.

    Every quantity in Table 7's Brain row is 0.80 of plasma's except Cmax, which is exactly equal
    — and 0.80 is the ratio Table 6 gives for a single dose and the ratio the model produces. A
    Cmax equal to plasma's cannot sit above an AUC and a Cmean that are four fifths of it.
    """
    ratios = {
        column: (
            _cell(_TABLE7, "Brain", "500", column) / _cell(_TABLE7, "Plasma", "500", column)
        )
        for column in ("AUC24, nmol*h/mL", "Cmean, nmol/mL", "Cmax, nmol/mL")
    }
    assert ratios["AUC24, nmol*h/mL"] == pytest.approx(0.80, abs=0.01)
    assert ratios["Cmean, nmol/mL"] == pytest.approx(0.80, abs=0.01)
    assert ratios["Cmax, nmol/mL"] == pytest.approx(1.00, abs=0.001)

    single_dose = (
        _cell(_TABLE6, "Brain", "500", "Cmax, nmol/mL")
        / _cell(_TABLE6, "Plasma", "500", "Cmax, nmol/mL")
    )
    assert single_dose == pytest.approx(0.80, abs=0.01)

    brain = max(simulate(_MODEL, "mBrain", duration=48.0, steps=960)[1])
    plasma = max(simulate(_MODEL, "mPlasmaVenous", duration=48.0, steps=960)[1])
    assert brain / plasma == pytest.approx(0.80, abs=0.01)


def test_the_certificate_publishes_both_causes() -> None:
    """Six failures, two causes, each naming the element it implicates."""
    certificate = json.loads(
        (_ROOT / "datasets" / "milestone" / "certificates" / "BIOMD0000001029.json").read_text(
            encoding="utf-8"
        )
    )
    failed = [a for a in certificate["assessments"] if a["verdict"] == "failed"]
    assert len(failed) == 6
    causes = {a["root_cause"] for a in failed}
    assert causes == {
        "artifact-runs-less-of-the-protocol-than-the-paper-states",
        "apparent-manuscript-error",
    }
    # And the entry is still partially reproduced: twenty-four of its thirty claims do reproduce.
    assert certificate["overall"] == "partially-reproduced"
    assert sum(1 for a in certificate["assessments"] if a["verdict"] == "reproduced") == 24
    # Each failure attributes a fault, and the two point in opposite directions.
    faults = {a["root_cause"]: a["fault_hypothesis"] for a in failed}
    assert faults["apparent-manuscript-error"] == "manuscript"
    assert faults["artifact-runs-less-of-the-protocol-than-the-paper-states"] == "reconstruction"
