"""Claim parsing from the claims dataset (pure; the engine-backed run is in test_worked_example)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import Claim, ReferenceKind, load_claims_dataset
from reprolith.engine import NonFiniteSimulation, require_finite

_CLAIMS = Path(__file__).parent.parent / "datasets" / "pkpd_claims.json"


def test_require_finite_passes_finite_and_rejects_inf_nan() -> None:
    # A diverging/too-stiff model yields inf/nan; require_finite signals that so the entry can
    # be recorded as blocked rather than pass garbage numbers downstream.
    assert require_finite((1.0, 2.0, 3.0), "A") == (1.0, 2.0, 3.0)
    with pytest.raises(NonFiniteSimulation):
        require_finite((1.0, float("inf")), "A")
    with pytest.raises(NonFiniteSimulation):
        require_finite((1.0, float("nan")), "A")


def test_load_claims_dataset_reads_the_shipped_dataset() -> None:
    data = load_claims_dataset(_CLAIMS)
    assert "BIOMD0000001028" in data["entries"]  # metformin, the one verified entry
    assert data["entries"]["BIOMD0000001028"]["claims"]


def test_claim_from_record_parses_overrides_and_flags() -> None:
    record = {
        "claim_id": "Cmax-1000mg", "quantity": "plasma Cmax", "species": "mPlasmaVenous",
        "reported": 11.2, "source_location": "Chung dataset", "metric": "cmax",
        "parameter_overrides": {"Metformin_Dose_in_Lumen_in_mg": 779.9},
        "assumption_qualified": True,
    }
    claim = Claim.from_record(record)
    assert claim.reported == 11.2
    assert claim.parameter_overrides == (("Metformin_Dose_in_Lumen_in_mg", 779.9),)
    assert claim.assumption_qualified
    assert claim.reference_kind is ReferenceKind.NUMERIC


def test_claim_from_record_defaults() -> None:
    claim = Claim.from_record({
        "claim_id": "c", "quantity": "AUC", "species": "C_p", "reported": 100.0,
        "source_location": "Table 2",
    })
    assert claim.metric == "cmax"  # default
    assert claim.parameter_overrides == ()
    assert not claim.assumption_qualified


def test_claims_dataset_records_parse() -> None:
    data = json.loads(_CLAIMS.read_text())
    for entry in data["entries"].values():
        assert entry["model_file"] and entry["paper"]["doi"]
        claims = [Claim.from_record(r) for r in entry["claims"]]
        assert claims and all(c.source_location for c in claims)  # every claim cites its source
