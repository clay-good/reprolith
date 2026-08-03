"""Canonical encoding is stable regardless of key insertion order."""

from __future__ import annotations

from reprolith.canonical import canonical_bytes, canonical_json, content_hash


def test_key_order_does_not_change_bytes() -> None:
    a = {"b": 1, "a": 2, "c": [3, 2, 1]}
    b = {"c": [3, 2, 1], "a": 2, "b": 1}
    assert canonical_bytes(a) == canonical_bytes(b)
    assert content_hash(a) == content_hash(b)


def test_list_order_is_preserved() -> None:
    # Sequences are meaningful data; their order must survive canonicalization.
    assert canonical_json([1, 2, 3]) != canonical_json([3, 2, 1])


def test_hash_is_hex_sha256() -> None:
    digest = content_hash({"x": 1})
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)
