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

    A non-finite float (``NaN``, ``Infinity``) is refused rather than encoded: Python's
    default would emit the bare tokens ``NaN``/``Infinity``, which are not valid JSON, so a
    certificate or dossier carrying one would be an artifact no standards-compliant reader
    could parse — the opposite of the portable, independently-checkable result the encoding
    exists to guarantee. Refusing surfaces the bad value at its source instead.
    """
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except ValueError as exc:
        raise ValueError(
            "cannot canonicalize a non-finite number (NaN or infinity); a certificate or dossier "
            "must serialize to valid JSON, so the value is rejected rather than emitted as an "
            "unparseable token"
        ) from exc


def canonical_bytes(obj: Any) -> bytes:
    """Return the UTF-8 bytes of the canonical JSON encoding of ``obj``."""
    return canonical_json(obj).encode("utf-8")


def content_hash(obj: Any) -> str:
    """Return the SHA-256 hex digest of the canonical encoding of ``obj``."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
