"""Canonical serialization and content hashing.

Determinism is a product property of Reprolith: given the same inputs and the same
pinned engine, a certificate must be byte-reproducible. That guarantee rests on a
single, boring function — a canonical JSON encoding with a stable key order and no
formatting variance — plus a content hash over it. Everything that must be
deterministic is compared through here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize ``obj`` to a canonical JSON string.

    Keys are sorted, separators are fixed, and non-ASCII is preserved verbatim, so
    two structurally equal values always produce identical text regardless of the
    order in which their keys were inserted.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """Return the UTF-8 bytes of the canonical JSON encoding of ``obj``."""
    return canonical_json(obj).encode("utf-8")


def content_hash(obj: Any) -> str:
    """Return the SHA-256 hex digest of the canonical encoding of ``obj``."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
