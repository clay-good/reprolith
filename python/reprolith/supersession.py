"""Versioning and supersession of certificates (bootstrap task 5.5).

As engines and tolerances evolve, an entry is re-certified. A new certificate links to the
one it supersedes (by content digest), states what changed, and never overwrites the prior
record (spec: ``reproduction-certificate`` — "Versioning and supersession"). The prior
certificate stays retrievable so the history is auditable.

Linking is stored on the certificate itself (``Certificate.supersedes``); this module adds
the two things that link enables: a plain description of what changed between two
certifications, and a ledger that keeps every issued certificate retrievable and can walk a
supersession chain back to its root.
"""

from __future__ import annotations

from .determinism import certificate_digest
from .model import Certificate


def describe_changes(prior: Certificate, new: Certificate) -> tuple[str, ...]:
    """State what changed from ``prior`` to ``new``, in plain language.

    Reports the engine-pin differences that motivate a re-certification and whether the
    overall verdict moved. An empty tuple means the two certifications differ in nothing
    this description tracks (they may still differ elsewhere, e.g. run metadata).
    """
    changes: list[str] = []
    old, cur = prior.engine_pin, new.engine_pin
    if old.engine != cur.engine:
        changes.append(f"engine: {old.engine} -> {cur.engine}")
    if old.version != cur.version:
        changes.append(f"engine version: {old.version} -> {cur.version}")
    if old.algorithm != cur.algorithm:
        changes.append(f"algorithm: {old.algorithm} -> {cur.algorithm}")
    if prior.overall is not new.overall:
        changes.append(f"overall verdict: {prior.overall.value} -> {new.overall.value}")
    return tuple(changes)


class CertificateLedger:
    """A retrievable, append-only store of issued certificates keyed by content digest.

    Issuing a superseding certificate never displaces the one it replaces: both remain in
    the ledger, and :meth:`chain` reconstructs the full lineage newest-first.
    """

    def __init__(self) -> None:
        self._by_digest: dict[str, Certificate] = {}

    def __len__(self) -> int:
        return len(self._by_digest)

    def issue(self, cert: Certificate) -> str:
        """Record ``cert`` and return its content digest (its stable identity)."""
        digest = certificate_digest(cert)
        self._by_digest[digest] = cert
        return digest

    def get(self, digest: str) -> Certificate | None:
        """Retrieve a previously issued certificate by its content digest."""
        return self._by_digest.get(digest)

    def items(self) -> tuple[tuple[str, Certificate], ...]:
        """Every issued (digest, certificate) pair — a read-only snapshot."""
        return tuple(self._by_digest.items())

    def chain(self, cert: Certificate) -> tuple[Certificate, ...]:
        """The supersession lineage of ``cert``, newest first, back to the root.

        Walks ``supersedes`` links through the ledger. Stops at the first predecessor not
        present (a truncated history is reported as what is retained, not an error).
        """
        lineage: list[Certificate] = [cert]
        current = cert
        while current.supersedes is not None:
            prior = self._by_digest.get(current.supersedes)
            if prior is None:
                break
            lineage.append(prior)
            current = prior
        return tuple(lineage)


__all__ = ["CertificateLedger", "describe_changes"]
