"""Which recorded assumptions each committed claim rests on, held to what the model and the claim say.

`rests_on_assumptions` is what lets claim selection see that thirty areas and thirty times to peak
rest on one reading of a deposit's clock. It is curated data, and curated data drifts — so each id
is checked against something that is not the curator: the unit the *model* reads the claim's
output in, the dose override the claim *runs*, and the qualification flag the certificate already
publishes. Pure policy, no engine — these run in the core CI job.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from reprolith import claim_selection_report, claim_units, dossier_from_dict
from reprolith.manuscript_values import model_time_unit

_DATASETS = Path(__file__).resolve().parents[1] / "datasets"
_ENTRIES = json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))["entries"]
_CLOCK = "time-unit-of-the-deposit"
_SALT = "dose-salt-form"
_DOSE = "Metformin_Dose_in_Lumen_in_mg"


def _claims():
    for accession, entry in _ENTRIES.items():
        for claim in entry["claims"]:
            yield accession, entry, claim, frozenset(claim.get("rests_on_assumptions", ()))


def test_the_corpus_records_what_its_claims_rest_on() -> None:
    # The premise, so every check below cannot pass over an empty field.
    linked = [claim["claim_id"] for _, _, claim, rests_on in _claims() if rests_on]
    assert len(linked) == 143, len(linked)


def test_every_assumption_a_claim_rests_on_is_one_its_entry_records() -> None:
    for accession, entry, claim, rests_on in _claims():
        recorded = {a["id"] for a in entry.get("assumptions", ())}
        assert rests_on <= recorded, (accession, claim["claim_id"], rests_on - recorded)


def test_a_claim_rests_on_an_assumption_exactly_when_its_verdict_is_qualified() -> None:
    # The certificate's flag and the selector's overlap are two readings of one fact; if they
    # disagree, one of them is publishing something the other does not believe.
    for accession, _, claim, rests_on in _claims():
        assert bool(rests_on) is bool(claim.get("assumption_qualified")), (
            accession, claim["claim_id"],
        )


def test_the_clock_is_rested_on_exactly_where_the_model_reads_the_output_by_it() -> None:
    """Held to the model rather than the metric label: the assumption is about the deposit's time
    unit, so a claim rests on it exactly when the unit the model reads its output in carries that
    clock — an area as a factor, a time to peak as the whole of it, a peak height not at all."""
    timed = 0
    for accession, entry, claim, rests_on in _claims():
        model = (_DATASETS / entry["model_file"]).read_text(encoding="utf-8")
        reads_the_clock = model_time_unit(model) in claim_units(
            model, claim["species"], claim["metric"]
        )
        assert (_CLOCK in rests_on) is reads_the_clock, (accession, claim["claim_id"])
        timed += reads_the_clock
    assert timed == 100, timed


def test_the_salt_form_is_rested_on_exactly_where_the_claim_converts_a_dose() -> None:
    for accession, entry, claim, rests_on in _claims():
        if _SALT not in {a["id"] for a in entry.get("assumptions", ())}:
            assert _SALT not in rests_on
            continue
        segments = [claim, *claim.get("schedule", ())]
        converts = any(_DOSE in (s.get("parameter_overrides") or {}) for s in segments)
        assert (_SALT in rests_on) is converts, (accession, claim["claim_id"])


def test_the_committed_dossiers_carry_what_the_claims_file_records() -> None:
    # The selector reads the dossier, not the claims file; a join that dropped the field would
    # leave every check above true and the selection blind to all of it.
    for accession, entry in _ENTRIES.items():
        stored = json.loads(
            (_DATASETS / "milestone" / "dossiers" / f"{accession}.json").read_text("utf-8")
        )
        assert {c["id"]: frozenset(c.get("rests_on_assumptions", ())) for c in stored["claims"]} == {
            c["claim_id"]: frozenset(c.get("rests_on_assumptions", ())) for c in entry["claims"]
        }, accession


def _dossier(accession: str):
    path = _DATASETS / "milestone" / "dossiers" / f"{accession}.json"
    return dossier_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _timed(chosen: list[str]) -> int:
    return sum(1 for claim_id in chosen if not claim_id.startswith("Cmax"))


@pytest.mark.parametrize("accession", ["BIOMD0000001027", "BIOMD0000001028", "BIOMD0000001029"])
def test_a_budget_is_no_longer_spent_on_one_reading_of_the_clock(accession: str) -> None:
    """Measured on the corpus: blind to the assumption, three claims' budget went to three areas —
    an area and a peak of one tissue have the same model footprint, and ids break the tie
    alphabetically — so a budgeted certificate rested entirely on the reading of the clock that
    qualifies every one of them. Seeing it, the set takes one and spends the rest on peaks."""
    dossier = _dossier(accession)
    blind = replace(
        dossier,
        claims=tuple(replace(c, rests_on_assumptions=frozenset()) for c in dossier.claims),
    )
    before = claim_selection_report(blind, budget=3)["selection"]["chosen"]
    after = claim_selection_report(dossier, budget=3)["selection"]["chosen"]
    assert (_timed(before), _timed(after)) == (3, 1), (before, after)
