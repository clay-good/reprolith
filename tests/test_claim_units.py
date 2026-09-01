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
