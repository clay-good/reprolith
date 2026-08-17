"""Claim parsing from the claims dataset (pure; the engine-backed run is in test_worked_example)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import Claim, ReferenceKind, load_claims_dataset
from reprolith.certify import _metric
from reprolith.engine import NonFiniteSimulation, require_finite

_CLAIMS = Path(__file__).parent.parent / "datasets" / "pkpd_claims.json"

# An estimation claim must state how its estimate was recovered: this glue does not run the re-fit,
# so the objective, optimizer, starting values, and dataset are the only evidence one happened.
_PROTOCOL = (
    "maximum likelihood, Nelder-Mead from the paper's Table 2 initial estimates, "
    "over the shipped plasma dataset"
)


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


def test_metric_derives_cmax_auc_and_final() -> None:
    times = (0.0, 1.0, 2.0, 3.0)
    values = (0.0, 4.0, 2.0, 1.0)
    assert _metric(times, values, "cmax") == 4.0
    assert _metric(times, values, "final") == 1.0
    # trapezoidal area: (0+4)/2 + (4+2)/2 + (2+1)/2 = 2 + 3 + 1.5 = 6.5
    assert _metric(times, values, "auc") == pytest.approx(6.5)
    with pytest.raises(ValueError):
        _metric(times, values, "nonsense")


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
    data = json.loads(_CLAIMS.read_text(encoding="utf-8"))
    for entry in data["entries"].values():
        assert entry["model_file"] and entry["paper"]["doi"]
        claims = [Claim.from_record(r) for r in entry["claims"]]
        assert claims and all(c.source_location for c in claims)  # every claim cites its source


def test_certify_estimation_records_a_distinct_estimation_verdict() -> None:
    from reprolith import (
        Attribution,
        EnginePin,
        EstimationClaim,
        FailureMode,
        Fault,
        OverallVerdict,
        PaperIdentity,
        ReproductionLevel,
        Verdict,
        certify_estimation,
    )

    cert = certify_estimation(
        paper=PaperIdentity(title="A data-shipping PK paper", doi="10.9/est"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        claims=[
            EstimationClaim(
                claim_id="cl", quantity="CL/F estimate", reported=3.20, recovered=3.30,
                source_location="Table 3",
                protocol=_PROTOCOL,
            ),
            EstimationClaim(
                claim_id="vc", quantity="Vc estimate", reported=10.0, recovered=18.0,
                source_location="Table 3",
                protocol=_PROTOCOL,
                shortfall=Attribution(
                    mode=FailureMode.LOCAL_OPTIMUM, implicated="central volume",
                    fault=Fault.RECONSTRUCTION,
                ),
            ),
        ],
    )
    assert all(a.level is ReproductionLevel.ESTIMATION for a in cert.assessments)
    verdicts = {a.claim_id: a.verdict for a in cert.assessments}
    assert verdicts["cl"] is Verdict.REPRODUCED  # ~3% inside the 10% estimation default
    assert verdicts["vc"] is Verdict.FAILED
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert all(a.protocol == _PROTOCOL for a in cert.assessments)


def test_an_estimation_claim_that_states_no_protocol_is_refused() -> None:
    """A re-fit nobody can repeat is not evidence, and `recovered == reported` proves nothing."""
    from reprolith import EstimationClaim

    with pytest.raises(ValueError, match="states no protocol"):
        EstimationClaim(
            claim_id="cl", quantity="CL/F estimate", reported=3.2, recovered=3.2,
            source_location="Table 3", protocol="",
        )
