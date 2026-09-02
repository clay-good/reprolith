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


def test_a_reworded_scope_is_refused_at_construction() -> None:
    """Not emptiable was never the whole invariant, and the other half had no test.

    A scope reworded to "clinically validated" is worse than a missing one, and it travels through
    every read surface — the badge, the registry, the human render, the query. The load path
    already refused a stored certificate that reworded it; construction refuses one too, and
    `scripts/mutation_check.py` found that refusal surviving its own deletion with the whole suite
    still green, which is the definition of an unheld guard.
    """
    from reprolith.scope import SCOPE_HUMAN, SCOPE_MACHINE

    with pytest.raises(ValueError, match="cannot be reworded"):
        Scope(machine="clinically-validated", human=SCOPE_HUMAN)
    with pytest.raises(ValueError, match="cannot be reworded"):
        Scope(machine=SCOPE_MACHINE, human="This model is clinically validated.")
    # A near-miss is still a rewording: the text is fixed, not merely non-empty.
    with pytest.raises(ValueError, match="cannot be reworded"):
        Scope(machine=SCOPE_MACHINE, human=SCOPE_HUMAN.replace("no claim", "little claim"))
    # And the exact pair is what a certificate carries, so the default still constructs.
    assert Scope().to_dict() == {"machine": SCOPE_MACHINE, "human": SCOPE_HUMAN}


def test_scope_travels_in_content() -> None:
    # Whatever else is in the certificate, the scope statement is part of the
    # hashed content — it cannot be dropped in serialization.
    cert = build_certificate(
        paper=PaperIdentity(title="anything"),
        engine_pin=EnginePin(engine="e", version="1"),
        assessments=[],
    )
    assert "scope" in cert.content()
