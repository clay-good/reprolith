"""The model's own inputs, checked against the paper that reports them.

Every certificate in this repository checks a model's *outputs* against numbers a paper prints.
Nothing had ever checked its *inputs*. The deposited metformin models declare ten tissue-plasma
partition coefficients, the paper prints all ten in its Table 3, and until this file nothing
compared the two — a deposition carrying a coefficient its own paper does not report would have
reproduced every claim in the corpus and said nothing.

The pairing of a table row to a parameter id is a curator's judgment, committed in
`datasets/pkpd_parameters.json` and never inferred: "Lungs" is `Ktp_Lung` and "Intestine" is
`Ktp_IntestineVascular`, and no rule would produce either.

Dependency-free — the check reads SBML text, not libSBML.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    check_claim_values,
    check_parameter_values,
    disagreeing_parameters,
    unsupported_claims,
)

_DATASETS = Path(__file__).parent.parent / "datasets"
_PARAMETERS = json.loads((_DATASETS / "pkpd_parameters.json").read_text(encoding="utf-8"))
_ENTRIES = _PARAMETERS["entries"]


def _model(accession: str) -> str:
    return (_DATASETS / "worked_examples" / _ENTRIES[accession]["model"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("accession", sorted(_ENTRIES))
def test_every_deposited_model_carries_the_coefficients_its_paper_prints(accession: str) -> None:
    entry = _ENTRIES[accession]
    checks = check_parameter_values(_model(accession), entry["parameters"])
    assert len(checks) == len(entry["parameters"])
    assert disagreeing_parameters(checks) == (), (
        "a deposited model does not carry a value its paper reports: "
        + "; ".join(c.detail for c in disagreeing_parameters(checks))
    )
    assert all(c.agrees for c in checks), (
        "a parameter was not compared at all, which this corpus has no case for yet: "
        + "; ".join(c.detail for c in checks if c.agrees is not True)
    )


@pytest.mark.parametrize("accession", sorted(_ENTRIES))
def test_every_reported_value_is_printed_in_the_table_it_cites(accession: str) -> None:
    """The other direction, and the one that caught a transcription error in the claims corpus: a
    value nobody checked against the paper is a value nobody checked."""
    tables = json.loads(
        (_DATASETS / "manuscripts" / "BIOMD0000001027_tables.json").read_text(encoding="utf-8")
    )["tables"]
    claims = [
        {"claim_id": row["parameter"], "reported": row["reported"],
         "source_location": row["source_location"]}
        for row in _ENTRIES[accession]["parameters"]
    ]
    checks = check_claim_values(claims, tables)
    assert unsupported_claims(checks) == (), (
        "a reported value is not printed in Table 3: "
        + "; ".join(c.detail for c in unsupported_claims(checks))
    )
    assert all(c.found is True for c in checks), "every row cites Table 3 and must be checked"


def test_a_wrong_value_is_caught() -> None:
    """The mutation this file exists to fail on. Without it the assertions above pass for a check
    that returns nothing at all."""
    rows = [dict(row) for row in _ENTRIES["BIOMD0000001027"]["parameters"]]
    rows[0]["reported"] = rows[0]["reported"] + 1.0
    bad = disagreeing_parameters(check_parameter_values(_model("BIOMD0000001027"), rows))
    assert len(bad) == 1
    assert "not" in bad[0].detail


def test_a_parameter_the_model_does_not_declare_is_a_disagreement_not_a_silence() -> None:
    rows = [{"parameter": "Ktp_Spleen", "reported": 1.0, "source_location": "Table 3"}]
    (check,) = check_parameter_values(_model("BIOMD0000001027"), rows)
    assert check.agrees is False
    assert check.carried is None
    assert "declares no parameter" in check.detail


def test_a_value_an_initial_assignment_overrides_is_not_compared() -> None:
    """The defect shape this repository has been caught by three times: an `initialAssignment`
    makes the `value` attribute inert, and comparing it against a paper would produce the most
    confident wrong answer available — agreement with a number that never reaches the integrator."""
    sbml = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
  <model id="m">
    <listOfParameters>
      <parameter id="k" value="0.7"/>
      <parameter id="j" value="0.7"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="k">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><cn>9</cn></math>
      </initialAssignment>
    </listOfInitialAssignments>
  </model>
</sbml>
"""
    rows = [
        {"parameter": "k", "reported": 0.7, "source_location": "Table 3"},
        {"parameter": "j", "reported": 0.7, "source_location": "Table 3"},
    ]
    inert, live = check_parameter_values(sbml, rows)
    assert inert.agrees is None and "not what runs" in inert.detail
    assert live.agrees is True
    # And never folded into the accusation.
    assert disagreeing_parameters((inert, live)) == ()


def test_agreement_is_at_the_precision_the_paper_printed_and_says_so() -> None:
    """The paper prints 0.7 and the model carries 0.73. Demanding equality would accuse a correct
    deposition of a mismatch its own source cannot support, so the limit travels with the answer."""
    (check,) = check_parameter_values(
        _model("BIOMD0000001027"),
        [{"parameter": "Ktp_Adipose", "reported": 0.7, "source_location": "Table 3"}],
    )
    assert check.agrees is True
    assert check.carried == 0.73
    assert "1 decimal place(s) the paper prints" in check.detail
