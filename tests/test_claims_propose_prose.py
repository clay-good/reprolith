"""The prose reader, on the surface a curator can actually reach.

`propose_claims_from_prose` was written, tested, measured — and then left as a Python function.
The measurement it was written for was about this repository's *corpus*: across ten open-access
papers, text reaches no paper the tables miss, so prose does not widen what Reprolith can seed.
That is a fact about which papers become reachable, and it was read as a fact about the reader's
worth. Per *paper* the commit that built it says the opposite in its own words — prose "broadens
what can be read from a paper already reachable" — and an author whose Cmax is in a sentence rather
than a table had no way to run it that did not begin with `import reprolith`.

So `claims-propose` reads both halves of a paper now. What the merge deliberately does not do is
de-duplicate: a value printed in a table and restated in a sentence is proposed twice, cited to
each, because which of the two a claim should cite is the same judgment this whole module refuses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith.claim_candidates import (
    merge_proposals,
    propose_claims,
    propose_claims_from_prose,
)
from reprolith.cli import run

_ROOT = Path(__file__).resolve().parents[1]
_TABLES = _ROOT / "datasets" / "manuscripts" / "BIOMD0000001027_tables.json"
_MODEL = _ROOT / "datasets" / "worked_examples" / "Zake2021_metformin_human_single_PO.xml"

_PROSE = (
    "Metformin pharmacokinetics were simulated after a single 1000 mg oral dose.\n"
    "Concentrations in plasma reach a maximum of 6.1 nmol/mL at 3 h after dosing.\n"
    "See reference 36 for the original data set of 12 subjects.\n"
)


def _prose_file(tmp_path: Path) -> Path:
    path = tmp_path / "paper.txt"
    path.write_text(_PROSE, encoding="utf-8")
    return path


def _tables() -> dict:
    return json.loads(_TABLES.read_text(encoding="utf-8"))["tables"]


def test_a_paper_read_both_ways_loses_no_candidate_and_says_the_split() -> None:
    """Nothing is dropped, and the file says which reading each half came from.

    A curator handed one file cannot see that 169 of its rows are cells and 2 are sentences unless
    it says so, and the two need reading differently — a cell carries a column heading, a sentence
    may be quoting somebody else's experiment.
    """
    from_tables = propose_claims(_tables())
    from_prose = propose_claims_from_prose(_PROSE)
    merged = merge_proposals(from_tables, from_prose)

    assert len(merged["candidates"]) == len(from_tables["candidates"]) + len(
        from_prose["candidates"]
    )
    assert merged["tables_read"] == from_tables["tables_read"]
    split = [note for note in merged["notes"] if "came from the tables" in note]
    assert len(split) == 1, merged["notes"]
    assert f"{len(from_tables['candidates'])} candidate(s) came from the tables" in split[0]


def test_a_value_in_both_a_table_and_a_sentence_is_proposed_twice() -> None:
    """De-duplication would choose the curator's citation for them.

    The metformin paper prints 6.1 nmol/mL in Table 1 and restates it in the text. The two source
    locations are not interchangeable — one is a cell, one is a sentence with an attribution — and
    which one a claim should cite is a judgment about the paper.
    """
    restated = {"Table 9": {"rows": [
        ["Tissue", "Cmax, nmol/mL"],
        ["Plasma", "6.1"],
    ]}}
    merged = merge_proposals(propose_claims(restated), propose_claims_from_prose(_PROSE))
    at_61 = [c for c in merged["candidates"] if c["reported"] == 6.1]
    assert len(at_61) == 2, at_61
    assert {"Table 9" in c["source_location"] for c in at_61} == {True, False}


def test_a_prose_only_file_does_not_end_with_a_paragraph_about_columns() -> None:
    """The tables reader's closing note describes a reading a prose-only file does not contain.

    It reads "a table prints measured values, fitted values, percentage differences and doses side
    by side". True of the reading it was written for, and a file with no table in it that ends on
    that sentence is telling the curator about somebody else's file.
    """
    merged = merge_proposals(None, propose_claims_from_prose(_PROSE))
    assert not any("a table prints measured values" in note for note in merged["notes"])
    assert any("prose is noisier than a table" in note for note in merged["notes"])


def test_a_prose_only_file_is_not_sent_to_a_check_that_can_only_shrug() -> None:
    """`claims-check` compares a value against the table the claim cites; a sentence cites none.

    The tables file's closing instruction sends the curator to that comparison, which is the right
    next step for a cell and a row of `not checked` for a sentence. What the same command *can*
    answer about a prose candidate is whether the model declares the output they named and reads it
    in the unit their paper stated, so the prose-only description names `--model`.
    """
    merged = merge_proposals(None, propose_claims_from_prose(_PROSE))
    assert "--model" in merged["description"]
    assert "cites no table" in merged["description"]
    assert "--model" not in merge_proposals(propose_claims(_tables()), None)["description"]


def test_the_two_readings_write_one_shape() -> None:
    """A consumer of this file sees the same keys whichever halves were read.

    `tables_read` is empty rather than absent on a prose-only file, for the reason `claims-check`
    emits an empty `unknown_outputs` with no model: a key that appears and disappears is a shape a
    reader has to branch on.
    """
    both = merge_proposals(propose_claims(_tables()), propose_claims_from_prose(_PROSE))
    prose_only = merge_proposals(None, propose_claims_from_prose(_PROSE))
    tables_only = merge_proposals(propose_claims(_tables()), None)
    assert set(both) == set(prose_only) == set(tables_only)
    assert prose_only["tables_read"] == []


def test_merging_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one reading"):
        merge_proposals(None, None)


def test_the_command_reads_a_papers_text(tmp_path, capsys) -> None:
    assert run(["claims-propose", "--prose", str(_prose_file(tmp_path))]) == 0
    payload = json.loads(capsys.readouterr().out)
    peak = [c for c in payload["candidates"] if c["reported"] == 6.1]
    assert len(peak) == 1 and peak[0]["metric"] == "cmax"
    # The whole sentence, because "the measured value" and "the simulated value" are what tell a
    # curator which half of a sentence is the model's.
    assert peak[0]["source_location"].startswith("Concentrations in plasma")
    # A number with no unit beside it is a citation far more often than a result.
    assert not [c for c in payload["candidates"] if c["reported"] == 36]


def test_the_command_with_neither_reading_names_both_flags(tmp_path, capsys) -> None:
    """`--tables` stopped being required, and an argparse "the following arguments are required"
    would name only the one that is still spelled first."""
    assert run(["claims-propose"]) == 1
    err = capsys.readouterr().err
    assert "--tables" in err and "--prose" in err


def test_an_unreadable_text_file_is_a_message_and_not_a_traceback(tmp_path, capsys) -> None:
    assert run(["claims-propose", "--prose", str(tmp_path / "absent.txt")]) == 1
    assert "cannot read the text" in capsys.readouterr().err


def test_a_model_with_prose_says_why_nothing_carries_a_suggestion(tmp_path, capsys) -> None:
    """The silent asymmetry this would otherwise have.

    `--model` puts `species_suggested` on a table row whose label is the model's own word. A
    sentence has no label, so the prose half carries none — and a curator seeing suggestions on one
    half and none on the other reads it as "no output matches" rather than "nothing was asked".
    """
    out = tmp_path / "candidates.json"
    assert run([
        "claims-propose", "--prose", str(_prose_file(tmp_path)), "--model", str(_MODEL),
        "--out", str(out),
    ]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert not any(c.get("species_suggested") for c in payload["candidates"])
    assert any("a sentence has no label" in note for note in payload["notes"])


def test_the_summary_line_names_the_text_it_read(tmp_path, capsys) -> None:
    """`--out` reported "N candidate(s) from <the tables>", which for a prose-only run was a
    trailing empty list — the one line that says what was read, saying nothing."""
    out = tmp_path / "candidates.json"
    assert run([
        "claims-propose", "--prose", str(_prose_file(tmp_path)), "--out", str(out),
    ]) == 0
    assert "candidate(s) from the text of paper.txt" in capsys.readouterr().out


def test_a_prose_candidate_reaches_the_check_the_file_names(tmp_path, capsys) -> None:
    """The end the whole bracket exists for: what this writes is a file `claims-check` reads.

    Its values come back unchecked — a sentence cites no table — and the run is clean rather than a
    refusal, which is the distinction between "not checked" and "wrong" this surface is built on.
    """
    candidates = tmp_path / "candidates.json"
    assert run([
        "claims-propose", "--prose", str(_prose_file(tmp_path)), "--accession", "ACC1",
        "--out", str(candidates),
    ]) == 0
    capsys.readouterr()
    assert run([
        "claims-check", "--claims", str(candidates), "--tables", str(_TABLES),
        "--accession", "ACC1",
    ]) == 0
    assert "cites no table" in capsys.readouterr().out
