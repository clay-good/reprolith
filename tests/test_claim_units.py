"""What a claim's number is a number *of*, checked against the model that produces it.

Every certificate in this repository compares a claim's reported value against a value the model
produces. Nothing established that the two are the same **quantity**. A paper's µg/mL against a
model's nmol/mL is a verdict about arithmetic and not about the model — and no check downstream can
see it, because the reconstruction runs the model's own numbers and reproduces the model's own
curve to within a fraction of a percent.

The unit a claim is read in is composed, not declared anywhere: a species' time course is read as a
concentration, so it is the substance unit over its compartment's own, and an area under the curve
carries the run's time as well. The paper's own table headers say the same thing — `Cmax, nmol/mL`
and `AUC24, nmol*h/mL` — which is why the metric is a term in the answer.

Dependency-free: this reads SBML text, not libSBML.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import check_claim_units, claim_units, claims_in_another_unit

_DATASETS = Path(__file__).parent.parent / "datasets"
_CLAIMS = json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))["entries"]


def _model(accession: str) -> str:
    return (_DATASETS / _CLAIMS[accession]["model_file"]).read_text(encoding="utf-8")


def test_every_committed_concentration_claim_is_in_the_unit_the_model_reads() -> None:
    """Seventy of the eighty committed claims read a peak concentration, and all seventy agree.

    That is the whole corpus's numeric comparison resting on something that was written only in
    prose until now — each claim's `source_location` said "the paper simulates 6.1 nmol/mL" and
    nothing read it.
    """
    checked = 0
    for accession, entry in _CLAIMS.items():
        peaks = [c for c in entry["claims"] if c.get("metric", "cmax") != "auc"]
        checks = check_claim_units(_model(accession), peaks)
        assert claims_in_another_unit(checks) == (), "; ".join(
            c.detail for c in claims_in_another_unit(checks)
        )
        assert all(c.agrees for c in checks), "; ".join(
            c.detail for c in checks if c.agrees is not True
        )
        checked += len(checks)
    assert checked == 70


def test_the_deposited_models_declare_a_time_unit_that_is_not_the_hour_they_run_in() -> None:
    """The finding, and it is about the deposit rather than about this repository.

    Each deposited model's `time` unitDefinition is `multiplier="3600" scale="2"`. SBML reads that
    as (multiplier × 10^scale) — **360000 seconds**, a hundred hours — and libSBML's own
    `convertToSI` agrees. The paper's tables are per hour, the recipe runs 0 to 24, and every AUC
    claim in this corpus is `nmol*h/mL`, so the model's declaration is a hundredfold away from the
    quantity it is actually run and reported in.

    Nothing in the pipeline reads `timeUnits`, so no certificate is wrong because of it. A
    reproducer rebuilding the model from its own declarations is: that is precisely the reader
    this check exists for, and the answer says how far off, not only that something differs.
    """
    for accession, entry in _CLAIMS.items():
        areas = [c for c in entry["claims"] if c.get("metric") == "auc"]
        if not areas:
            continue
        checks = check_claim_units(_model(accession), areas)
        assert len(claims_in_another_unit(checks)) == len(areas), accession
        for check in checks:
            assert check.stated == "nmol*h/mL"
            assert "3600*10^2 second" in check.declared
            assert "100 times as large" in check.detail
    # And the peak claims on the same models are unaffected: the time unit is not in that unit.
    assert claim_units(_model("BIOMD0000001027"), "mPlasmaVenous") == "10^-9 mole / 10^-3 litre"


def test_a_claim_that_states_no_unit_is_unchecked_and_never_agreement() -> None:
    """Opt-in, and the absence of a statement is not a statement."""
    (check,) = check_claim_units(
        _model("BIOMD0000001027"), [{"claim_id": "c", "species": "mPlasmaVenous"}]
    )
    assert check.agrees is None
    assert claims_in_another_unit((check,)) == ()
    assert "states no unit" in check.detail and "10^-9 mole / 10^-3 litre" in check.detail


def test_an_output_the_model_does_not_have_is_reported_not_raised() -> None:
    """A claim naming a species the model does not declare is a finding elsewhere; here it is a
    reason this check could not run, and it must not take the command down with it."""
    (check,) = check_claim_units(
        _model("BIOMD0000001027"),
        [{"claim_id": "c", "species": "nope", "reported_units": "nmol/mL"}],
    )
    assert check.agrees is None and "declares no species" in check.detail


def test_a_readings_clock_is_compared_against_the_models_own() -> None:
    """The same defect on the other input a figure claim has: its x axis.

    A reading is put on the run's sample grid by its x values. Read in minutes against a model
    running in hours, it covers the window numerically and lands every value in the wrong place —
    which the window check cannot see, because 0-120 does cover 0-24.
    """
    from reprolith import read_digitized_figure, time_unit_notes

    series = read_digitized_figure(json.dumps({
        "figure": "Figure 2A", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 30, "unit": "nmol/mL"},
        "series": [{"claim": "Cmax-plasma", "curve": "plasma",
                    "points": [[0, 0.0], [1, 27.2], [24, 2.0]]}],
    }))

    # Against the deposit, whose declared time unit is a hundred hours.
    (note,) = time_unit_notes(series, _model("BIOMD0000001027"), carrier="your model")
    assert "x axis in h" in note and "3600*10^2 second" in note and "100 times" in note

    # Against a model whose clock is the hour the figure is read in, nothing is said.
    hourly = """<?xml version="1.0"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m" timeUnits="time"><listOfUnitDefinitions>
    <unitDefinition id="time"><listOfUnits>
      <unit kind="second" exponent="1" scale="0" multiplier="3600"/>
    </listOfUnits></unitDefinition>
  </listOfUnitDefinitions></model>
</sbml>
"""
    assert time_unit_notes(series, hourly) == ()

    # And a model that states no time unit is an absence, not a disagreement.
    silent = '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" ' \
             'level="3" version="2"><model id="m"/></sbml>'
    assert time_unit_notes(series, silent) == ()


def test_a_readings_y_axis_is_compared_against_the_output_the_curve_reads() -> None:
    """The axis a curator is likelier to get wrong, and the one no other check can see.

    This paper's own document plots every tissue twice — once in mg on one panel and once in nmol
    on another — so a reading of one panel paired with the other's curve is a file that is
    internally perfect, correctly paired with a curve the document really plots, covering the run,
    and off by six orders of magnitude. The unit is the model's for *that element*, and which
    element a curve reads is what the document says.
    """
    from reprolith import read_digitized_figure, value_unit_notes

    worked = Path(__file__).parent.parent / "datasets" / "worked_examples"
    sedml = (worked / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8")
    model = (worked / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")

    def reading(claim: str, unit: str) -> tuple:
        return read_digitized_figure(json.dumps({
            "figure": "Figure 3A", "digitizer": "WebPlotDigitizer 4.7",
            "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
            "y_axis": {"minimum": 0, "maximum": 30, "unit": unit},
            "series": [{"claim": claim, "curve": "venous plasma",
                        "points": [[0, 0.0], [1, 20.0], [24, 2.0]]}],
        }))

    # p2's venous plasma curve reads the nmol species, and that unit is composed and agrees.
    assert value_unit_notes(reading("p2_curve_17_task2", "nmol/mL"), sedml, model) == ()
    # p1's plots the model's `mg…` *parameter* for the same tissue, and this model declares no unit
    # on it — so nothing is said. An absence, not agreement, and the reason is worth being exact
    # about: the check reads parameters as well as species, and it is this model that is silent.
    assert claim_units(model, "mgVenousPlasma") == "unstated"
    assert value_unit_notes(reading("p1_curve_23_task2", "mg/mL"), sedml, model) == ()

    (note,) = value_unit_notes(
        reading("p2_curve_17_task2", "mg/mL"), sedml, model, carrier="your model"
    )
    assert "y axis in mg/mL" in note and "'mPlasmaVenous'" in note
    assert "10^-9 mole / 10^-3 litre" in note

    # A claim id the document does not plot says nothing here: that is the pairing check's finding,
    # and answering it twice in two vocabularies helps nobody.
    assert value_unit_notes(reading("not_a_curve", "mg/mL"), sedml, model) == ()


def test_a_curve_plotting_a_parameter_is_read_in_that_parameters_own_unit() -> None:
    """A time course carries parameters as well as species, and either can be what a curve plots.

    A parameter is read as its value rather than as a concentration, so nothing is composed: the
    unit is the one the parameter declares. Leaving them out meant such a curve was passed over in
    silence, which reads exactly like agreement.
    """
    from reprolith import claim_units, read_digitized_figure, value_unit_notes

    model = """<?xml version="1.0"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m" timeUnits="time">
    <listOfUnitDefinitions>
      <unitDefinition id="time"><listOfUnits>
        <unit kind="second" exponent="1" scale="0" multiplier="3600"/>
      </listOfUnits></unitDefinition>
      <unitDefinition id="mass"><listOfUnits>
        <unit kind="gram" exponent="1" scale="-3" multiplier="1"/>
      </listOfUnits></unitDefinition>
    </listOfUnitDefinitions>
    <listOfParameters><parameter id="mgLiver" value="0" units="mass" constant="false"/>
    </listOfParameters>
  </model>
</sbml>
"""
    assert claim_units(model, "mgLiver") == "10^-3 gram"
    # An area under that curve carries the run's clock, exactly as a species' does.
    assert claim_units(model, "mgLiver", "auc") == "10^-3 gram * 3600*second"

    sedml = """<?xml version="1.0"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version3" level="1" version="3">
  <listOfDataGenerators>
    <dataGenerator id="g"><listOfVariables>
      <variable id="v" target="/sbml:sbml/sbml:model/sbml:listOfParameters/sbml:parameter[@id='mgLiver']" taskReference="t"/>
    </listOfVariables></dataGenerator>
  </listOfDataGenerators>
  <listOfOutputs><plot2D id="p1"><listOfCurves>
    <curve id="c1" logX="false" logY="false" xDataReference="g" yDataReference="g"/>
  </listOfCurves></plot2D></listOfOutputs>
</sedML>
"""
    reading = read_digitized_figure(json.dumps({
        "figure": "Figure 1", "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0, "maximum": 500, "unit": "g"},
        "series": [{"claim": "c1", "curve": "liver", "points": [[0, 0.0], [1, 300.0], [24, 20.0]]}],
    }))
    (note,) = value_unit_notes(reading, sedml, model, carrier="your model")
    assert "y axis in g" in note and "'mgLiver'" in note and "10^-3 gram" in note


def test_a_report_only_asserts_a_disagreement_it_can_establish() -> None:
    """The failure this repository has already shipped once: a check that cries wolf.

    `_units_differ` answers the question a *refusal* asks — unreadable means not compared, which is
    the safe direction there. A *report* is the opposite: a line saying two files disagree has to
    establish it, and a unit this module cannot parse is not evidence of anything.

    `nM` is why it matters. Molar is the one unit here written as a whole quantity rather than a
    product, and a curve read in µM against a model reading `10^-9 mole / 10^-3 litre` is the same
    quantity — a note there would be a false accusation against a correct file.
    """
    from reprolith.manuscript_values import (
        _canonical_composite,
        _units_differ,
        _units_known_to_differ,
    )

    assert _canonical_composite("µM") == (1e-6, ("mole",), ("litre",))
    assert _canonical_composite("M") == (1.0, ("mole",), ("litre",))
    assert not _units_known_to_differ("µM", "10^-9 mole / 10^-3 litre")
    assert _units_known_to_differ("nM", "10^-9 mole / 10^-3 litre")  # a thousandfold, still caught

    # Unreadable on either side: the refusal says "do not compare", the report says nothing.
    assert _units_differ("arbitrary units", "10^-9 mole")
    assert not _units_known_to_differ("arbitrary units", "10^-9 mole")


def test_a_unit_this_cannot_read_is_not_checked_rather_than_accused() -> None:
    """The same rule as the figure reports, in the check that has a verdict and an exit code.

    "ANOTHER UNIT" is an accusation, and an axis labelled "arbitrary units" or a percent is not
    evidence that the claim and the model disagree. It joins the claims that stated nothing —
    reported, not failed — while the real thousandfold pairs stay findings.
    """
    def check(unit: str):
        (one,) = check_claim_units(
            _model("BIOMD0000001027"),
            [{"claim_id": "c", "species": "mPlasmaVenous", "reported_units": unit}],
        )
        return one

    assert check("nmol/mL").agrees is True
    # Molar, spelled as a whole quantity, is the same thing this model reads.
    assert check("µM").agrees is True
    assert check("mg/mL").agrees is False
    unreadable = check("arbitrary units")
    assert unreadable.agrees is None and "not a unit this can read" in unreadable.detail
    assert claims_in_another_unit((unreadable,)) == ()


def test_a_claim_labelled_with_a_unit_its_own_table_does_not_print_is_caught() -> None:
    """The third side of the triangle, and the one nothing else can see.

    `check_claim_values` asks whether the paper prints that number. `check_claim_units` asks
    whether the model reads that output in that unit. A curator who reads a value out of a µmol
    column and labels it nmol passes both: the number is printed, and the model's unit is whatever
    it is. Only the paper's own heading says what its numbers are in.
    """
    from reprolith.manuscript_values import check_claim_units_in_tables

    tables = {"Table 6": {"caption": "x", "rows": [
        ["Tissue", "Cmax, nmol/mL", "AUC24, nmol*h/mL"],
        ["Plasma", "6.1", "51.7"],
    ]}}

    def check(units: str, metric: str = "cmax"):
        (one,) = check_claim_units_in_tables([{
            "claim_id": "c", "reported": 6.1, "metric": metric,
            "reported_units": units, "source_location": "Table 6, plasma row",
        }], tables)
        return one

    assert check("nmol/mL").agrees is True
    assert check("nmol*h/mL", metric="auc").agrees is True
    mislabelled = check("µmol/mL")
    assert mislabelled.agrees is False and "prints nmol/mL" in mislabelled.detail
    # The metric decides which column is compared: an area is not judged against a peak's heading.
    assert check("nmol/mL", metric="auc").agrees is False

    # A unit this cannot read is not a disagreement, here as everywhere else.
    assert check("arbitrary units").agrees is None
    # And a table with no column stating that metric is not guessed at.
    (nothing,) = check_claim_units_in_tables([{
        "claim_id": "c", "reported": 1.0, "metric": "final", "reported_units": "nmol/mL",
        "source_location": "Table 6, plasma row",
    }], tables)
    assert nothing.agrees is None and "no single final column" in nothing.detail


def test_every_committed_claim_is_in_the_unit_its_cited_table_prints() -> None:
    """On the corpus, from the paper's side rather than the model's."""
    from reprolith.manuscript_values import check_claim_units_in_tables

    repo = Path(__file__).resolve().parents[1]
    checked = 0
    for accession, entry in _CLAIMS.items():
        path = repo / "datasets" / "manuscripts" / f"{accession}_tables.json"
        if not path.exists():
            continue
        tables = json.loads(path.read_text(encoding="utf-8"))["tables"]
        results = check_claim_units_in_tables(entry["claims"], tables)
        assert all(c.agrees is True for c in results), [
            c.detail for c in results if c.agrees is not True
        ]
        checked += len(results)
    assert checked == 80, checked


def test_a_count_based_class_is_passed_over_rather_than_accused() -> None:
    """What this composes is how a *time course* is read, and not every class reads one.

    The unit here is substance over volume because the ODE engine asks for concentration data. A
    class whose engine reports copy numbers reads the same species as an amount, and a curator
    stating one of those is not describing what this composes. Nothing here can parse "molecules",
    so every check that uses it stays silent — which is the right answer, and it is the safe
    direction of the same rule that keeps an unreadable unit from becoming a disagreement.
    """
    from reprolith.manuscript_values import _units_known_to_differ

    for stated in ("molecules", "copies", "copy number", "counts"):
        assert not _units_known_to_differ(stated, "10^-9 mole / 10^-3 litre"), stated
    (check,) = check_claim_units(
        _model("BIOMD0000001027"),
        [{"claim_id": "c", "species": "mPlasmaVenous", "reported_units": "molecules"}],
    )
    assert check.agrees is None and claims_in_another_unit((check,)) == ()


def test_a_row_that_states_no_metric_is_not_judged_against_a_column_it_never_named() -> None:
    """An absent field and an empty one are different facts, and collapsing them invented a verdict.

    A claims record that *omits* `metric` means the claims file's documented default, a peak. A
    candidate whose `metric` is present and empty means the table reader found none stated — a
    "Tmax, h" column, whose heading names no metric it knows. Defaulting the second to a peak
    compared that candidate against the Cmax column's unit and reported ANOTHER UNIT: an
    accusation manufactured out of a missing field, on an unedited proposal.
    """
    from reprolith.manuscript_values import check_claim_units_in_tables

    tables = {"Table 1": {"caption": "x", "rows": [
        ["Tissue", "Cmax. nmol/mL", "Tmax. h"],
        ["Plasma", "27.2", "1.3"],
    ]}}
    rows = [
        {"claim_id": "peak", "reported": 27.2, "metric": "cmax", "reported_units": "nmol/mL",
         "source_location": "Table 1, Plasma row"},
        {"claim_id": "time", "reported": 1.3, "metric": "", "reported_units": "h",
         "source_location": "Table 1, Plasma row"},
        {"claim_id": "default", "reported": 27.2, "reported_units": "nmol/mL",
         "source_location": "Table 1, Plasma row"},
    ]
    by_id = {c.claim_id: c for c in check_claim_units_in_tables(rows, tables)}
    assert by_id["peak"].agrees is True
    assert by_id["time"].agrees is None and "states no metric" in by_id["time"].detail
    # The key omitted entirely still means the documented default.
    assert by_id["default"].agrees is True

    # The model side reads the same rule: an unstated metric is not a peak by assumption.
    (unstated,) = check_claim_units(
        _model("BIOMD0000001027"),
        [{"claim_id": "time", "species": "mPlasmaVenous", "metric": "", "reported_units": "h"}],
    )
    assert unstated.agrees is None and "states no metric" in unstated.detail
