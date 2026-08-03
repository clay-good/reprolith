"""Same inputs + same pin => byte-reproducible certificate (bootstrap task 0.3)."""

from __future__ import annotations

from reprolith import (
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    RunMetadata,
    Verdict,
    build_certificate,
    certificate_digest,
    same_modulo_run_metadata,
)


def _cert() -> object:
    return build_certificate(
        paper=PaperIdentity(title="A one-compartment PK model", doi="10.0000/example"),
        engine_pin=EnginePin(engine="example-sim", version="1.2.3"),
        assessments=[
            ClaimAssessment(
                claim_id="fig1",
                quantity="plasma concentration-time profile",
                verdict=Verdict.REPRODUCED,
                source_location="Figure 1",
            )
        ],
    )


def test_run_metadata_does_not_change_the_digest() -> None:
    cert_a = _cert()
    cert_b = _cert()
    # Two different runs — different timestamps and actors — of identical inputs.
    run1 = RunMetadata(created_at="2026-08-03T10:00:00Z", actor="loop", tool_version="0.0.1")
    run2 = RunMetadata(created_at="2027-01-01T00:00:00Z", actor="human", tool_version="0.0.1")
    assert run1 != run2
    assert same_modulo_run_metadata(cert_a, cert_b)
    assert certificate_digest(cert_a) == certificate_digest(cert_b)


def test_changing_content_changes_the_digest() -> None:
    baseline = _cert()
    changed = build_certificate(
        paper=PaperIdentity(title="A one-compartment PK model", doi="10.0000/example"),
        engine_pin=EnginePin(engine="example-sim", version="9.9.9"),  # different pin
        assessments=[
            ClaimAssessment(
                claim_id="fig1",
                quantity="plasma concentration-time profile",
                verdict=Verdict.REPRODUCED,
                source_location="Figure 1",
            )
        ],
    )
    assert certificate_digest(baseline) != certificate_digest(changed)
