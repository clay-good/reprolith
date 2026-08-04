"""Claim parsing from the claims dataset (pure; the engine-backed run is in test_worked_example)."""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import Claim, ReferenceKind

_CLAIMS = Path(__file__).parent.parent / "datasets" / "pkpd_claims.json"


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
