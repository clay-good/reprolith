"""The scope statement is always present and can never be emptied."""

from __future__ import annotations

import pytest
from reprolith import (
    EnginePin,
    PaperIdentity,
    Scope,
    build_certificate,
)


def test_certificate_always_has_scope() -> None:
    cert = build_certificate(
        paper=PaperIdentity(title="anything"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[],
    )
    content = cert.content()
    assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
    assert content["scope"]["human"].strip()


def test_empty_scope_is_rejected() -> None:
    with pytest.raises(ValueError):
        Scope(machine="", human="")


def test_scope_travels_in_content() -> None:
    # Whatever else is in the certificate, the scope statement is part of the
    # hashed content — it cannot be dropped in serialization.
    cert = build_certificate(
        paper=PaperIdentity(title="anything"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[],
    )
    assert "scope" in cert.content()
