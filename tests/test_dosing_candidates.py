"""The doses a paper's text states, proposed with their sentences and decided by nobody here.

A dossier's dosing protocol is the element a deposited model routinely does not carry: the file
holds a default dose and the doses the paper's results were produced at are in its prose. The
metformin worked example found them by reading. Task 2.1 of the bootstrap change names that as not
built.

Every sentence under test is one a surveyed paper prints (PMC8026019 unless a test says
otherwise), because what this reader is worth is what it does on text nobody wrote for it. They
hold it in both directions: the doses a human extracted are found, and an amount that is not a
dose — what was excreted, what a concentration is measured in — is not volunteered.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import propose_dosing_from_prose
from reprolith.cli import run


def _read(text: str) -> list[dict]:
    return propose_dosing_from_prose(text)["candidates"]


def _amounts(text: str) -> list[tuple]:
    return [
        (c["amount"] if c["amount"] is not None else tuple(c["amount_range"]), c["amount_units"])
        for c in _read(text)
    ]


def test_a_list_under_one_dose_word_is_every_dose_in_it() -> None:
    """Reading only the number beside "dose of" keeps the first and drops the two listed with it."""
    sentence = (
        "The simulations were made for a single PO dose of 500mg, 1000mg, and 1500mg metformin "
        "hydrochloride, which corresponds to 389.2mg, 778.4m,g, and 1167.6mg metformin (see "
        "section 4.3)."
    )
    assert _amounts(sentence) == [(500.0, "mg"), (1000.0, "mg"), (1500.0, "mg")]
    (first, *_rest) = _read(sentence)
    assert first["route"] == "oral"
    assert first["schedule_words"] == ["single"]
    assert first["attribution"] == "simulated"
    assert first["source_location"] == sentence
    # Never proposed: the free-base amounts sit in the same sentence, and which of the two the
    # model's input takes is the question a certificate here still rests on.
    assert first["parameter"] == ""


def test_bare_numbers_before_a_unit_take_it() -> None:
    # PMC8646028 and PMC8397660.
    assert _amounts(
        "Next, simulations of the biliary excretion rate of ICG after bolus administrations of "
        "0.5, 1.0, and 2.0 mg/kg ICG were performed."
    ) == [(0.5, "mg/kg"), (1.0, "mg/kg"), (2.0, "mg/kg")]
    assert _amounts(
        "Figure 7 shows a bar plot comparison of toxicity and recovery across schedules for two "
        "doses (4 or 6 mg)."
    ) == [(4.0, "mg"), (6.0, "mg")]


def test_a_range_is_one_range_and_not_its_upper_end() -> None:
    # PMC3910012, and the therapeutic range from the metformin paper.
    assert _amounts(
        "We used this model to simulate the brain CB1 occupancy in hypothetical patients at doses "
        "of 0.1–40 mg."
    ) == [((0.1, 40.0), "mg")]
    (therapy,) = _read(
        "The doses of metformin hydrochloride used in therapy range from 500 mg up to 3000 mg per "
        "day [9]."
    )
    assert therapy["amount"] is None
    assert therapy["amount_range"] == [500.0, 3000.0]
    assert therapy["schedule_words"] == ["per day"]


def test_a_range_across_two_units_is_not_given_one() -> None:
    """PMC9637881 prints "2 mg–3 mg/kg". Calling that 2–3 mg/kg is a reading."""
    assert _amounts("The used DXM dose (2 mg–3 mg/kg) varies between studies.") == [
        (2.0, "mg"), (3.0, "mg/kg"),
    ]


def test_an_amount_that_left_the_body_is_not_a_dose() -> None:
    """The one false candidate in sixty-seven when this was first run on the paper."""
    sentence = (
        "After a 500mg dose, 50.7% of it (197.1mg) is excreted in the urine, after a 1000mg dose, "
        "46.3% of the dose (362mg) is excreted, but after a 1500mg dose 44.1% (517mg) is excreted "
        "in the urine."
    )
    assert _amounts(sentence) == [(500.0, "mg"), (1000.0, "mg"), (1500.0, "mg")]


def test_a_concentration_is_not_an_amount() -> None:
    assert _amounts(
        "The kidney tissues get a maximum concentration of 840 nmol/mL for a 500mg dose."
    ) == [(500.0, "mg")]


def test_a_mass_with_no_dose_word_beside_it_is_not_proposed() -> None:
    # PMC3910013: a curve label, and a concentration scale.
    assert _read("The antibody accumulates in sufficient amount (Figure 4f, 500 mg curve).") == []
    assert _read("Free sIL-6Rα is of the order of 100 ng/ml in circulation.") == []


def test_a_limit_says_which_side_it_bounds() -> None:
    """PMC4026633 and PMC8646028. The model was not run *at* either amount."""
    (above,) = _read("Higher efficacy is predicted with doses >250 mg resulting in FEV1 increases.")
    assert (above["amount"], above["bound"]) == (250.0, "above")
    (exceeds,) = _read("A dose-dependency can only be observed if the ICG dose exceeds 100 mg.")
    assert (exceeds["amount"], exceeds["bound"]) == (100.0, "above")
    (plain,) = _read("PK profiles at 100 mg drug dose are shown.")
    assert plain["bound"] == ""


def test_the_route_is_blank_when_the_sentence_names_two() -> None:
    (both,) = _read(
        "The data in the Wilcock study were collected from two separate experiments following "
        "peroral and intravenous doses of 50mg/kg in mice."
    )
    assert both["route"] == ""
    (one,) = _read(
        "Venous plasma (A) and stomach (D) following a single intravenous 50 mg/kg dose in mice."
    )
    assert one["route"] == "intravenous"


def test_scheduling_words_are_quoted_and_nothing_is_assembled_from_them() -> None:
    sentence = (
        "The human model was validated against four separate datasets with different PO doses– "
        "250mg dose dataset from Chung [36] with one 375mg pre-dose 12 hours before the main dose."
    )
    candidates = _read(sentence)
    assert [c["amount"] for c in candidates] == [250.0, 375.0]
    assert candidates[0]["schedule_words"] == ["pre-dose", "12 hours before"]
    assert not any("schedule" == key for key in candidates[0])


def test_a_repeated_figure_legend_is_one_statement() -> None:
    legend = "Concentrations were simulated following a 2 mg oral estradiol."
    assert len(_read(" ".join([legend] * 4))) == 1


def test_a_thousands_separator_is_not_a_list() -> None:
    # PMC4026633.
    assert _amounts("Zileuton 1,200 mg twice daily is a more effective bronchodilator.") == [
        (1200.0, "mg"),
    ]


def test_a_figure_number_and_a_year_are_not_lent_a_unit() -> None:
    """Both stand where a list of doses would, and neither is one."""
    assert _amounts("As shown in Figure 2, 4 mg doses reduce the count.") == [(4.0, "mg")]
    assert _amounts("In the trial reported in 2019, 10 mg doses were given.") == [(10.0, "mg")]
    assert _read("The curve in Fig. 2g dose-response panels is steeper.") == []
    # A real list still is one, whatever its size.
    assert _amounts("Patients received doses of 1000, 2000 mg.") == [(1000.0, "mg"), (2000.0, "mg")]


def test_text_that_states_no_dose_yields_a_note_and_no_candidate() -> None:
    """Task 2.3's rule on this path: a missing dose is a gap, not a value."""
    result = propose_dosing_from_prose("The model has nine compartments. Clearance is hepatic.")
    assert result["candidates"] == []
    assert "a gap to record, not a value to supply" in result["notes"][0]


def test_the_survey_records_how_far_this_reaches() -> None:
    """Nine papers in ten state a dose in their text; two in ten state a result there.

    The committed survey is what the documentation's sentence rests on, and the metformin paper's
    row is the check against a human: its distinct amounts are the seven the worked example and
    its claims were extracted with by hand, plus the two ranges the paper gives.
    """
    survey = json.loads(
        (Path(__file__).parent.parent / "datasets" / "manuscripts" / "table_survey.json")
        .read_text(encoding="utf-8")
    )
    papers = survey["papers"]
    assert sum(1 for paper in papers.values() if paper["dosing"]["candidates"]) == 9
    assert sum(1 for paper in papers.values() if paper["prose"]["naming_a_quantity"]) == 2
    assert len(papers) == 10
    assert papers["PMC8026019"]["dosing"]["distinct_amounts"] == 9


def test_the_command_writes_the_candidates_and_says_how_many(tmp_path, capsys) -> None:
    text = tmp_path / "paper.txt"
    text.write_text(
        "A single PO dose of 500mg was simulated. The model has nine compartments.",
        encoding="utf-8",
    )
    out = tmp_path / "dosing.json"
    assert run(["dosing-propose", "--prose", str(text), "--out", str(out), "--accession", "A1"]) == 0
    printed = capsys.readouterr().out
    assert "1 candidate from the text of paper.txt" in printed
    (candidate,) = json.loads(out.read_text(encoding="utf-8"))["entries"]["A1"]["candidates"]
    assert (candidate["amount"], candidate["amount_units"], candidate["route"]) == (
        500.0, "mg", "oral",
    )
    assert run(["dosing-propose", "--prose", str(tmp_path / "nope.txt")]) == 1
    assert "cannot read the text" in capsys.readouterr().err
