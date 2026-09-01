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


def test_the_check_says_which_parameters_the_paper_never_reported() -> None:
    """A floor that counts only what it was handed cannot see what it was not.

    `check_parameter_values` answers "does the model carry what the paper says?" for every
    parameter the paper reports, and says nothing about the rest. The rest is the number this
    project exists to surface: a parameter the paper omits is a value a reproducer rebuilding from
    the paper has to take from the author's file, or guess.

    Only *settable* parameters count. One an `initialAssignment` or a rule determines does not run
    at the number in its `value` attribute, so a paper omits nothing by leaving it out — asking for
    it would be asking an author to publish an inert attribute.
    """
    from reprolith import parameters_the_paper_does_not_state

    model = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfParameters>
      <parameter id="Ktp_Liver" value="5.5" constant="true"/>
      <parameter id="Body_Weight" value="70" constant="true"/>
      <parameter id="Cardiac_Output" value="6.5" constant="true"/>
      <parameter id="QLiver" value="1799" constant="true"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="QLiver">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>Cardiac_Output</ci></math>
      </initialAssignment>
    </listOfInitialAssignments>
  </model>
</sbml>
"""
    reported = [{"parameter": "Ktp_Liver", "reported": 5.5, "source_location": "Table 3"}]
    # QLiver is left out: an initialAssignment makes its value attribute inert, so the paper is
    # not omitting a value by not printing one that never reaches the integrator.
    assert parameters_the_paper_does_not_state(model, reported) == (
        "Body_Weight", "Cardiac_Output",
    )

    # A paper reporting all of them leaves nothing to name.
    every = [{"parameter": name, "reported": 1.0, "source_location": "Table 3"}
             for name in ("Ktp_Liver", "Body_Weight", "Cardiac_Output")]
    assert parameters_the_paper_does_not_state(model, every) == ()


def test_the_shipped_metformin_model_has_six_values_its_paper_does_not_print() -> None:
    """Measured on the corpus rather than asserted in prose, and they are not trivia: the body
    weight, the cardiac output and the dose the whole salt-form assumption is about."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import parameters_the_paper_does_not_state

    repo = Path(__file__).resolve().parents[1]
    model = (repo / "datasets" / "worked_examples"
             / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")
    reported = json.loads(
        (repo / "datasets" / "pkpd_parameters.json").read_text(encoding="utf-8")
    )["entries"]["BIOMD0000001028"]["parameters"]

    unstated = parameters_the_paper_does_not_state(model, reported)
    assert unstated == (
        "Body_Weight", "Cardiac_Output", "Intestine_Coefficient", "Kidney_Coefficient",
        "Metformin_Dose_in_Lumen_in_mg", "Qgfr",
    )
    assert len(reported) == 10  # ten of the sixteen settable parameters are reported


def test_how_much_of_this_paper_s_own_inputs_it_publishes() -> None:
    """The first measurement here about a paper's *inputs* rather than its outputs.

    Every certificate in this repository checks outputs. This counts, across all four models the
    metformin paper deposited, how many of their settable parameters the paper pairs with a printed
    value: **40 of 62**, so 22 are values a reproducer rebuilding from the paper alone would have
    to take from the deposit or guess. The same handful recurs in every model — the body weight,
    the cardiac output, the glomerular filtration flow, the dose.

    Stated as a fact about *this paper*, which is what four models by one group can support. It is
    not a survey, and nothing here should be read as a rate for the literature.

    The pairing is the curator's, as it is everywhere else: "reported" means a curator paired the
    parameter with a value they found printed, not that a rule decided the paper reports it.
    """
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import parameters_the_paper_does_not_state
    from reprolith.manuscript_values import _declared_parameters

    repo = Path(__file__).resolve().parents[1]
    entries = json.loads(
        (repo / "datasets" / "pkpd_parameters.json").read_text(encoding="utf-8")
    )["entries"]
    assert len(entries) == 4, "the four models the metformin paper deposited"

    paired = settable = 0
    for entry in entries.values():
        sbml = (repo / "datasets" / "worked_examples" / entry["model"]).read_text(encoding="utf-8")
        declared, determined = _declared_parameters(sbml)
        settable += sum(1 for name in declared if name not in determined)
        paired += len(entry["parameters"])
        # Every model leaves some unstated, so the finding is not one deposit's oddity.
        assert parameters_the_paper_does_not_state(sbml, entry["parameters"])

    assert (paired, settable) == (40, 62)


_VOLUMES_AND_INITIAL_CONDITIONS = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfCompartments>
      <compartment id="Liver" size="1.51" constant="true"/>
      <compartment id="Kidney" size="0.154" constant="true"/>
      <compartment id="Muscle" size="27.0" constant="false"/>
    </listOfCompartments>
    <listOfSpecies>
      <species id="mLiver" compartment="Liver" initialAmount="0" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
      <species id="cPlasma" compartment="Kidney" initialConcentration="6.1"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="Ktp_Liver" value="5.5" constant="true"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="Muscle">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>Ktp_Liver</ci></math>
      </initialAssignment>
    </listOfInitialAssignments>
  </model>
</sbml>
"""


def test_a_published_tissue_volume_is_checked_against_the_compartment_that_carries_it() -> None:
    """A PBPK paper's parameter table prints tissue volumes, and those are not parameters.

    The check read only `listOfParameters`, so a curator pairing their published liver volume with
    the compartment that holds it was answered `MISMATCH: the model declares no parameter 'Liver'`
    — against a model carrying the very number the paper prints. That is the worst answer an
    author-facing check can give: confident, wrong, and about a correct deposition. Initial
    conditions are the same shape, and a species declares its own in either of two attributes.
    """
    checks = {
        c.parameter: c
        for c in check_parameter_values(
            _VOLUMES_AND_INITIAL_CONDITIONS,
            [
                {"parameter": "Liver", "reported": 1.5, "source_location": "Table 2"},
                {"parameter": "Kidney", "reported": 0.3, "source_location": "Table 2"},
                {"parameter": "mLiver", "reported": 0.0, "source_location": "Methods"},
                {"parameter": "cPlasma", "reported": 6.1, "source_location": "Methods"},
            ],
        )
    }
    assert checks["Liver"].agrees is True
    assert checks["Liver"].carried == 1.51
    assert "the compartment carries 1.51" in checks["Liver"].detail
    # And it still disagrees when it should: 0.154 is 0.2 at one printed place, not 0.3.
    assert checks["Kidney"].agrees is False
    assert checks["mLiver"].agrees is True
    # initialConcentration, not initialAmount — whichever the species declares is its value.
    assert checks["cPlasma"].agrees is True
    assert checks["cPlasma"].carried == 6.1


def test_a_volume_the_models_own_math_sets_is_not_compared_against_the_paper() -> None:
    """The inert-attribute discipline, one level up from parameters.

    Sixteen of the twenty compartments in each deposited metformin model are scaled from the body
    weight by an `initialAssignment`, so the number in their `size` attribute is not what runs.
    Comparing one against a paper is the most confident wrong answer available — agreement with a
    number that never reaches the integrator — and it is refused by name, as `not compared` rather
    than as a mismatch.
    """
    (check,) = check_parameter_values(
        _VOLUMES_AND_INITIAL_CONDITIONS,
        [{"parameter": "Muscle", "reported": 27.0, "source_location": "Table 2"}],
    )
    assert check.agrees is None
    assert disagreeing_parameters((check,)) == ()
    assert "initialAssignment" in check.detail and "size attribute" in check.detail


def test_the_omission_report_names_volumes_and_initial_conditions_by_their_own_kind() -> None:
    """The parameter floor could not see the two lists it never read.

    A tissue volume is a compartment and an initial condition is a species, and a paper that prints
    neither leaves a reproducer taking both from the deposit or guessing. Grouped by kind, because
    naming a compartment in a list called "parameters" would answer about the wrong thing — and
    because the parameter count this repository publishes has to stay a count of parameters.
    """
    from reprolith import parameters_the_paper_does_not_state, quantities_the_paper_does_not_state

    reported = [{"parameter": "Ktp_Liver", "reported": 5.5, "source_location": "Table 3"}]
    assert quantities_the_paper_does_not_state(_VOLUMES_AND_INITIAL_CONDITIONS, reported) == {
        "compartment": ("Kidney", "Liver"),  # Muscle is set by an initialAssignment
        "species": ("cPlasma", "mLiver"),
    }
    # The parameter slice is unchanged, and is still the number the docs quote.
    assert parameters_the_paper_does_not_state(_VOLUMES_AND_INITIAL_CONDITIONS, reported) == ()

    # A kind with nothing unstated is left out rather than reported empty.
    everything = reported + [
        {"parameter": name, "reported": 1.0, "source_location": "Table 2"}
        for name in ("Liver", "Kidney", "mLiver", "cPlasma")
    ]
    assert quantities_the_paper_does_not_state(_VOLUMES_AND_INITIAL_CONDITIONS, everything) == {}


def test_how_much_the_parameter_floor_was_not_counting_on_the_corpus() -> None:
    """Measured on the four deposited metformin models, not asserted in prose.

    The parameter count is 40 of 62 settable parameters paired with a printed value. Those models
    carry 96 further settable values the count never looked at: 16 compartment sizes and 80 species
    initial conditions, none of them paired with anything the paper prints.

    The compartments are the finding, and it runs the other way from the guess: each model declares
    twenty, and sixteen of them are scaled from the body weight by an `initialAssignment`, so the
    paper omits nothing by not printing them. What is left settable in every model is four — the
    lumen and excreta compartments — which is why this is reported and never gated.
    """
    repo = Path(__file__).resolve().parents[1]
    entries = json.loads(
        (repo / "datasets" / "pkpd_parameters.json").read_text(encoding="utf-8")
    )["entries"]

    from reprolith import quantities_the_paper_does_not_state

    totals: dict[str, int] = {}
    for entry in entries.values():
        sbml = (repo / "datasets" / "worked_examples" / entry["model"]).read_text(encoding="utf-8")
        for kind, names in quantities_the_paper_does_not_state(sbml, entry["parameters"]).items():
            totals[kind] = totals.get(kind, 0) + len(names)

    assert totals == {"compartment": 16, "parameter": 22, "species": 80}


def test_the_template_writes_a_row_per_settable_value_and_never_a_number() -> None:
    """Typing out a deposit's ids is not judgment; pairing them with a paper's rows is.

    `params-check` refuses to guess which table row names which id, and that refusal left an author
    hand-writing a file with one entry per value in a model that has scores. The template writes
    the mechanical half.

    What it must never do is fill in `reported`. A template carrying the model's own value would
    hand the check the model's number as the paper's, and the comparison would agree by
    construction — the exact failure the check exists to catch, moved one file upstream.
    """
    from reprolith import parameters_template

    template = parameters_template(_VOLUMES_AND_INITIAL_CONDITIONS)
    assert [(row["parameter"], row["kind"]) for row in template["parameters"]] == [
        ("Kidney", "compartment"),
        ("Liver", "compartment"),
        ("Ktp_Liver", "parameter"),
        ("cPlasma", "species"),
        ("mLiver", "species"),
    ]
    assert all(row["reported"] is None and row["source_location"] == ""
               for row in template["parameters"])
    # No row carries the model's value under any key, however it is spelled.
    assert not any(
        isinstance(value, (int, float)) for row in template["parameters"] for value in row.values()
    )

    # Muscle is set by an initialAssignment: listed, never offered as a row, because pairing one is
    # refused downstream as `not compared` and a template should not invite that.
    assert template["determined_by_the_model"] == {"compartment": ["Muscle"]}
    assert "Muscle" not in {row["parameter"] for row in template["parameters"]}


def test_an_unfilled_template_is_reported_as_unfilled_and_never_as_agreement() -> None:
    """The round trip, on the shape the check actually receives."""
    from reprolith import parameters_template

    checks = check_parameter_values(
        _VOLUMES_AND_INITIAL_CONDITIONS,
        parameters_template(_VOLUMES_AND_INITIAL_CONDITIONS)["parameters"],
    )
    assert len(checks) == 5
    assert all(c.agrees is None and "unfilled" in c.detail for c in checks)
    assert disagreeing_parameters(checks) == ()


def test_the_template_covers_exactly_what_the_omission_report_would_name() -> None:
    """Two answers to one question, on the corpus: the rows an author is asked to fill in are the
    values the check would otherwise report as unstated, and neither list is the other's superset.
    """
    from reprolith import parameters_template, quantities_the_paper_does_not_state

    repo = Path(__file__).resolve().parents[1]
    entries = json.loads(
        (repo / "datasets" / "pkpd_parameters.json").read_text(encoding="utf-8")
    )["entries"]
    for entry in entries.values():
        sbml = (repo / "datasets" / "worked_examples" / entry["model"]).read_text(encoding="utf-8")
        rows = {row["parameter"] for row in parameters_template(sbml)["parameters"]}
        unstated = {
            name
            for names in quantities_the_paper_does_not_state(sbml, entry["parameters"]).values()
            for name in names
        }
        paired = {record["parameter"] for record in entry["parameters"]}
        assert rows == unstated | paired
