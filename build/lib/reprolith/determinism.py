"""The determinism harness (bootstrap task 0.3).

The guarantee: given the same inputs and the same pinned engine, a certificate is
byte-reproducible. Two runs differ only in run metadata (a timestamp, an actor), and
must still be recognized as the same certificate. The digest below is taken over the
certificate's deterministic *content* only, so it ignores exactly that difference.
"""

from __future__ import annotations

from .canonical import content_hash
from .model import Certificate


def certificate_digest(cert: Certificate) -> str:
    """Return the stable content digest of a certificate.

    Independent of run metadata: same inputs and pin -> same digest, always.
    """
    return content_hash(cert.content())


def same_modulo_run_metadata(a: Certificate, b: Certificate) -> bool:
    """True when two certificates are identical apart from their run metadata."""
    return certificate_digest(a) == certificate_digest(b)
