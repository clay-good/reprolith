"""A claim naming a model output the model does not have, reported as what it is.

`claims-check --model` already noticed — and filed it under **units**, as a check that could not be
made: *not checked: the model declares no species or parameter 'mLivver'*. True, and the smaller
half of the truth. A curator who mistypes a species name learns their unit was not compared. What
they need to learn is that nothing will ever read a number off an output the model does not declare,
so the claim cannot be reproduced at all.

It also passed the gate. `claims-check` returns non-zero for a value the cited table does not print
and for a claim in a unit the model does not read that output in, and deliberately not for an
unchecked claim — "an absence of evidence is not evidence of absence". A missing *unit* is an
absence of evidence; a missing *output* is not. The two had been folded together, so a typo sailed
through a pre-submission hook.

It is unambiguous, which is what makes it reportable: `claims-check` refuses a claims file holding
several papers unless `--accession` names one, so every claim it checks belongs to the entry whose
model was supplied.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith.cli import run
from reprolith.manuscript_values import claims_naming_unknown_outputs

_ROOT = Path(__file__).resolve().parents[1]
_MODEL = _ROOT / "datasets" / "worked_examples" / "Zake2021_Metformin_Mice_PO.xml"
_TABLES = _ROOT / "datasets" / "manuscripts" / "BIOMD0000001027_tables.json"


def _claims_file(tmp_path: Path, species: str) -> Path:
    path = tmp_path / "claims.json"
    path.write_text(
        json.dumps({"entries": {"X": {"claims": [{
            "claim_id": "c1", "quantity": "peak", "species": species, "reported": 216.6,
            "source_location": "Table 1, Liver row", "metric": "cmax",
            "reported_units": "nmol/mL",
        }]}}}),
        encoding="utf-8",
    )
    return path


def test_a_mistyped_output_fails_the_check(tmp_path: Path, capsys) -> None:
    exit_code = run([
        "claims-check", "--claims", str(_claims_file(tmp_path, "mLivver")),
        "--tables", str(_TABLES), "--model", str(_MODEL),
    ])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "OUTPUTS THIS MODEL DOES NOT DECLARE: 1" in out
    assert "cannot be reproduced" in out
    # An instruction, not the finding restated: it says where the model's own outputs are listed.
    assert "claims-template --model" in out
    # And the same absence is not also reported as a unit that could not be checked. Two accounts
    # of one fact is how a reader comes to think they are two facts.
    assert "the model declares no species or parameter 'mLivver'" not in out


def test_a_name_differing_only_in_case_is_named(tmp_path: Path, capsys) -> None:
    """The one correction that can be made with certainty, so it is made — and nothing else is.

    No edit distance, no "did you mean": talking a curator into a plausible wrong species is the
    failure the whole surrounding module is built to avoid, and a case slip is the single case
    where the right answer is not a guess.
    """
    run([
        "claims-check", "--claims", str(_claims_file(tmp_path, "mliver")),
        "--tables", str(_TABLES), "--model", str(_MODEL),
    ])
    out = capsys.readouterr().out
    assert "it declares 'mLiver', which differs only in case" in out


def test_a_correct_claim_and_an_unfilled_one_are_left_alone(tmp_path: Path, capsys) -> None:
    """A blank `species` is an unfinished file, not a wrong one — the distinction the unit check
    already drew and this must not undo, since a template stub and a candidate straight out of the
    table reader both arrive blank."""
    model = _MODEL.read_text(encoding="utf-8")
    assert claims_naming_unknown_outputs([{"claim_id": "c", "species": "mLiver"}], model) == ()
    assert claims_naming_unknown_outputs([{"claim_id": "c", "species": ""}], model) == ()

    assert run([
        "claims-check", "--claims", str(_claims_file(tmp_path, "mLiver")),
        "--tables", str(_TABLES), "--model", str(_MODEL),
    ]) == 0
    assert "OUTPUTS THIS MODEL DOES NOT DECLARE" not in capsys.readouterr().out


def test_a_parameter_is_a_legal_output_too(tmp_path: Path) -> None:
    """The unit check reads species *and* parameters, so this must not accuse a claim reading one."""
    model = _MODEL.read_text(encoding="utf-8")
    assert claims_naming_unknown_outputs([{"claim_id": "c", "species": "Ktp_Liver"}], model) == ()
