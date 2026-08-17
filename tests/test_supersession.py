"""Certificate versioning and supersession (bootstrap task 5.5)."""

from __future__ import annotations

from reprolith import (
    CertificateLedger,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    Verdict,
    build_certificate,
    certificate_digest,
    describe_changes,
)


def _cert(version: str, verdict: Verdict = Verdict.REPRODUCED, supersedes=None):
    return build_certificate(
        paper=PaperIdentity(title="One-compartment PK model", doi="10.1/x"),
        engine_pin=EnginePin(engine="biosimulators/copasi", version=version),
        assessments=[
            ClaimAssessment(claim_id="c1", quantity="AUC", verdict=verdict, source_location="Fig 1")
        ],
        supersedes=supersedes,
    )


def test_recertifying_links_to_and_preserves_the_prior() -> None:
    prior = _cert("4.42")
    ledger = CertificateLedger()
    prior_digest = ledger.issue(prior)

    # Re-verify under a new engine version.
    new = _cert("4.43", supersedes=prior)
    new_digest = ledger.issue(new)

    # The new certificate links to the prior by its content digest...
    assert new.supersedes == prior_digest
    assert new_digest != prior_digest
    # ...and the prior remains retrievable, unmodified, after the new one is issued.
    assert ledger.get(prior_digest) is prior
    assert prior.supersedes is None  # the prior itself was not mutated
    assert len(ledger) == 2


def test_chain_reconstructs_the_full_lineage_newest_first() -> None:
    ledger = CertificateLedger()
    v1 = _cert("4.42")
    ledger.issue(v1)
    v2 = _cert("4.43", supersedes=v1)
    ledger.issue(v2)
    v3 = _cert("4.44", supersedes=v2)
    ledger.issue(v3)

    chain = ledger.chain(v3)
    assert chain == (v3, v2, v1)


def test_first_certification_has_no_predecessor() -> None:
    v1 = _cert("4.42")
    assert v1.supersedes is None
    assert CertificateLedger().chain(v1) == (v1,)


def test_describe_changes_states_what_changed() -> None:
    prior = _cert("4.42", verdict=Verdict.FAILED)
    new = _cert("4.43", verdict=Verdict.REPRODUCED, supersedes=prior)
    changes = describe_changes(prior, new)
    assert "engine version: 4.42 -> 4.43" in changes
    assert "overall verdict: not-reproduced -> reproduced" in changes


def test_ledger_round_trips_with_its_supersession_chain() -> None:
    import json

    ledger = CertificateLedger()
    v1 = _cert("4.42")
    ledger.issue(v1)
    v2 = _cert("4.43", supersedes=v1)
    ledger.issue(v2)

    reloaded = CertificateLedger.from_dict(json.loads(json.dumps(ledger.to_dict())))
    assert len(reloaded) == 2
    # Every certificate is retrievable by its digest, and the chain still resolves.
    got_v2 = reloaded.get(certificate_digest(v2))
    assert got_v2 is not None
    chain = reloaded.chain(got_v2)
    assert [certificate_digest(c) for c in chain] == [certificate_digest(v2), certificate_digest(v1)]


def test_same_pin_recertification_is_deterministic() -> None:
    # Two re-certifications of the same content superseding the same prior are
    # byte-identical: the supersession link does not introduce nondeterminism.
    prior = _cert("4.42")
    a = _cert("4.43", supersedes=prior)
    b = _cert("4.43", supersedes=prior)
    assert certificate_digest(a) == certificate_digest(b)


def test_a_lineage_walk_terminates_even_on_an_injected_cycle() -> None:
    """A cycle cannot arise through issue(), but this walk is the kind that hangs if one does."""
    from dataclasses import replace

    ledger = CertificateLedger()
    cert = _cert("4.46")
    ledger.issue(cert)
    looping = replace(cert, supersedes=certificate_digest(cert))
    ledger._by_digest[certificate_digest(cert)] = looping  # inject past issue()
    assert len(ledger.chain(looping)) <= 2
